import os
import base64
import logging
import json
import asyncio
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.schema import NodeWithScore

# Import GCS storage handler
from gcs_storage import get_gcs_handler, GCSStorageHandler

from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web-voice-agent")

app = FastAPI()

# Mount static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Base directory for user data (for local fallback)
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))

# Check if GCS is enabled
USE_GCS = os.environ.get("USE_GCS", "false").lower() == "true"

# Initialize GCS handler if enabled
gcs_handler = None
if USE_GCS:
    try:
        gcs_handler = get_gcs_handler()
        logger.info("Google Cloud Storage initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Google Cloud Storage: {str(e)}")
        logger.warning("Falling back to local storage")

# OpenAI client for TTS and STT
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Active user sessions
active_sessions = {}

class Message(BaseModel):
    role: str
    content: str

class AgentConfig(BaseModel):
    """Configuration for the voice agent"""
    system_prompt: str
    voice: str = "alloy"
    model: str = "gpt-4o-mini"
    agent_name: Optional[str] = None
    language: str = "en"

async def load_user_config(user_id: str) -> Dict:
    """
    Load user configuration from storage
    
    Args:
        user_id: The user ID
        
    Returns:
        The user configuration as a dictionary
    """
    config = {}
    
    # Try loading from GCS first
    if USE_GCS and gcs_handler:
        try:
            # Create temp file for downloaded config
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Download config from GCS
            gcs_path = f"users/{user_id}/config/agent_config.json"
            success = gcs_handler.download_file(gcs_path, temp_path)
            
            if success:
                with open(temp_path, "r") as f:
                    config = json.load(f)
                logger.info(f"Loaded config from GCS for user {user_id}")
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
            if config:
                return config
                
        except Exception as e:
            logger.error(f"Error loading config from GCS: {str(e)}")
            logger.warning("Falling back to local config storage")
    
    # Try loading from local storage as fallback
    local_config_path = BASE_STORAGE_DIR / user_id / "config" / "agent_config.json"
    if os.path.exists(local_config_path):
        try:
            with open(local_config_path, "r") as f:
                config = json.load(f)
            logger.info(f"Loaded config locally from {local_config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading local config: {str(e)}")
    
    # Return default config if none found
    default_config = {
        "system_prompt": "You are a helpful AI assistant.",
        "voice": "alloy",
        "model": "gpt-4o-mini",
        "agent_name": None,
        "language": "en"
    }
    
    logger.info(f"Using default config for user {user_id}")
    return default_config

async def load_index_from_storage_path(storage_path: str) -> Optional[VectorStoreIndex]:
    """
    Load index from a storage path (local or GCS)
    
    Args:
        storage_path: The storage path (can be local or GCS)
        
    Returns:
        The loaded index or None if not found
    """
    try:
        # Check if path is a GCS path
        if storage_path.startswith("gcs://") and USE_GCS and gcs_handler:
            # Extract user_id and path components
            parts = storage_path.replace("gcs://", "").split("/")
            user_id = parts[0]
            collection_path = "/".join(parts[1:])
            
            # Create temp directory for index
            import tempfile
            temp_dir = tempfile.mkdtemp()
            
            # List all files in the collection
            gcs_prefix = f"users/{user_id}/{collection_path}"
            gcs_files = gcs_handler.list_files(user_id, collection_path)
            
            # Download each file to the temp directory
            for gcs_path in gcs_files:
                file_name = os.path.basename(gcs_path)
                local_path = os.path.join(temp_dir, file_name)
                success = gcs_handler.download_file(gcs_path, local_path)
                if not success:
                    logger.warning(f"Failed to download {gcs_path}")
            
            # Load index from temp directory
            storage_context = StorageContext.from_defaults(persist_dir=temp_dir)
            index = load_index_from_storage(storage_context)
            
            logger.info(f"Loaded index from GCS: {storage_path}")
            return index
            
        else:
            # Load from local path
            storage_context = StorageContext.from_defaults(persist_dir=storage_path)
            index = load_index_from_storage(storage_context)
            
            logger.info(f"Loaded index from local path: {storage_path}")
            return index
            
    except Exception as e:
        logger.error(f"Error loading index from {storage_path}: {str(e)}")
        return None

async def get_answer(index: VectorStoreIndex, query: str, config: Dict) -> Dict:
    """
    Query the index and get an answer
    
    Args:
        index: The vector store index to query
        query: The user's query
        config: Agent configuration
        
    Returns:
        Dictionary with response text and optional source nodes
    """
    try:
        # Create query engine
        query_engine = index.as_query_engine()
        
        # Execute query
        response = query_engine.query(query)
        
        # Get the response text
        answer = response.response
        
        # Collect source nodes if available
        source_nodes = []
        if hasattr(response, "source_nodes"):
            for node in response.source_nodes:
                if isinstance(node, NodeWithScore):
                    source_nodes.append({
                        "text": node.node.get_text(),
                        "score": float(node.score) if node.score else 0.0,
                        "metadata": node.node.metadata
                    })
        
        return {
            "answer": answer,
            "source_nodes": source_nodes
        }
    except Exception as e:
        logger.error(f"Error querying index: {str(e)}")
        return {
            "answer": f"I'm sorry, but I encountered an error when trying to answer your question. Error: {str(e)}",
            "source_nodes": []
        }

@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Voice Agent Interface</title>
        <style>
            body {
                font-family: 'Arial', sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                line-height: 1.6;
            }
            h1 {
                color: #2c3e50;
                text-align: center;
            }
            .container {
                background: #f9f9f9;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .controls {
                margin: 20px 0;
                display: flex;
                flex-direction: column;
            }
            button {
                padding: 10px;
                margin: 5px 0;
                border: none;
                border-radius: 4px;
                background: #3498db;
                color: white;
                cursor: pointer;
                font-size: 16px;
            }
            button:hover {
                background: #2980b9;
            }
            button:disabled {
                background: #95a5a6;
                cursor: not-allowed;
            }
            #messages {
                margin-top: 20px;
                border-top: 1px solid #ddd;
                padding-top: 20px;
                height: 400px;
                overflow-y: auto;
            }
            .message {
                margin-bottom: 10px;
                padding: 10px;
                border-radius: 4px;
            }
            .user {
                background: #e8f4f8;
                text-align: right;
            }
            .bot {
                background: #f0f0f0;
                text-align: left;
            }
            #status {
                text-align: center;
                font-style: italic;
                color: #7f8c8d;
            }
            #userIdInput {
                padding: 8px;
                margin: 5px 0;
                width: 100%;
                box-sizing: border-box;
            }
        </style>
    </head>
    <body>
        <h1>Voice Agent Interface</h1>
        <div class="container">
            <div class="controls">
                <input type="text" id="userIdInput" placeholder="Enter your user ID" value="default-user">
                <button id="connectBtn">Connect to Agent</button>
                <button id="startBtn" disabled>Start Recording</button>
                <button id="stopBtn" disabled>Stop Recording</button>
                <button id="disconnectBtn" disabled>Disconnect</button>
            </div>
            <div id="status">Not connected</div>
            <div id="messages"></div>
        </div>
        
        <script>
            let socket;
            let mediaRecorder;
            let audioChunks = [];
            let isRecording = false;
            
            // DOM elements
            const connectBtn = document.getElementById('connectBtn');
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            const disconnectBtn = document.getElementById('disconnectBtn');
            const status = document.getElementById('status');
            const messages = document.getElementById('messages');
            const userIdInput = document.getElementById('userIdInput');
            
            // Connect to WebSocket
            connectBtn.addEventListener('click', async () => {
                if (!userIdInput.value) {
                    alert('Please enter a user ID');
                    return;
                }
                
                const userId = userIdInput.value;
                socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/${userId}`);
                
                socket.onopen = () => {
                    status.textContent = 'Connected to agent';
                    connectBtn.disabled = true;
                    startBtn.disabled = false;
                    disconnectBtn.disabled = false;
                };
                
                socket.onclose = () => {
                    status.textContent = 'Disconnected';
                    connectBtn.disabled = false;
                    startBtn.disabled = true;
                    stopBtn.disabled = true;
                    disconnectBtn.disabled = true;
                    if (isRecording) {
                        stopRecording();
                    }
                };
                
                socket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'text_response') {
                        // Display text response
                        addMessage('bot', data.text);
                    } else if (data.type === 'audio_response') {
                        // Play audio response
                        const audioData = atob(data.audio);
                        const audioBlob = blobFromBase64(data.audio, 'audio/mp3');
                        const audioUrl = URL.createObjectURL(audioBlob);
                        const audio = new Audio(audioUrl);
                        audio.play();
                    }
                };
            });
            
            // Start recording
            startBtn.addEventListener('click', async () => {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    
                    mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        audioChunks = [];
                        
                        // Convert to base64
                        const reader = new FileReader();
                        reader.readAsDataURL(audioBlob);
                        reader.onloadend = () => {
                            const base64data = reader.result.split(',')[1];
                            
                            // Send to server
                            socket.send(JSON.stringify({
                                type: 'audio_message',
                                audio: base64data
                            }));
                            
                            status.textContent = 'Processing audio...';
                        };
                    };
                    
                    mediaRecorder.start();
                    isRecording = true;
                    status.textContent = 'Recording...';
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                    
                } catch (error) {
                    console.error('Error accessing microphone:', error);
                    status.textContent = `Error: ${error.message}`;
                }
            });
            
            // Stop recording
            stopBtn.addEventListener('click', () => {
                stopRecording();
            });
            
            // Disconnect
            disconnectBtn.addEventListener('click', () => {
                if (socket) {
                    socket.close();
                }
            });
            
            function stopRecording() {
                if (mediaRecorder && isRecording) {
                    mediaRecorder.stop();
                    isRecording = false;
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                    status.textContent = 'Sending audio...';
                    
                    // Stop all audio tracks
                    mediaRecorder.stream.getTracks().forEach(track => track.stop());
                }
            }
            
            function addMessage(role, content) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.textContent = content;
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function blobFromBase64(base64, contentType) {
                const byteCharacters = atob(base64);
                const byteArrays = [];
                
                for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                    const slice = byteCharacters.slice(offset, offset + 512);
                    const byteNumbers = new Array(slice.length);
                    
                    for (let i = 0; i < slice.length; i++) {
                        byteNumbers[i] = slice.charCodeAt(i);
                    }
                    
                    const byteArray = new Uint8Array(byteNumbers);
                    byteArrays.push(byteArray);
                }
                
                return new Blob(byteArrays, { type: contentType });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    
    try:
        # Load user configuration
        config = await load_user_config(user_id)
        
        # Get the list of available collections for this user
        index_paths = []
        try:
            # Try listing collections from the document upload API
            import httpx
            document_api_url = os.environ.get("DOCUMENT_API_URL", "http://localhost:8000")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{document_api_url}/collections/{user_id}")
                collections = response.json().get("collections", [])
                for collection in collections:
                    index_paths.append(collection["path"])
        except Exception as e:
            logger.warning(f"Failed to fetch collections from API: {str(e)}")
            
            # Fallback to checking local storage
            if not index_paths:
                index_dir = BASE_STORAGE_DIR / user_id / "knowledge-storage"
                if os.path.exists(index_dir / "docstore.json"):
                    index_paths.append(str(index_dir))
                
                # Check for named collections
                if os.path.exists(index_dir):
                    for item in os.listdir(index_dir):
                        item_path = index_dir / item
                        if item_path.is_dir() and os.path.exists(item_path / "docstore.json"):
                            index_paths.append(str(item_path))
        
        # Load indices
        indices = []
        for path in index_paths:
            index = await load_index_from_storage_path(path)
            if index:
                indices.append(index)
                logger.info(f"Loaded index from {path}")
            else:
                logger.warning(f"Failed to load index from {path}")
                
        if not indices:
            await websocket.send_text(json.dumps({
                "type": "text_response",
                "text": "No knowledge base found. Please upload documents first."
            }))
            return
            
        # Use the first index for now (could implement more sophisticated selection later)
        index = indices[0]
            
        # Prepare conversation history
        conversation_history = []
        if config.get("system_prompt"):
            conversation_history.append({"role": "system", "content": config["system_prompt"]})
        
        # Send welcome message
        welcome_message = "Hello! I'm your knowledge assistant. How can I help you today?"
        if config.get("agent_name"):
            welcome_message = f"Hello! I'm {config['agent_name']}. How can I help you today?"
            
        # Add an audio welcome message
        await send_tts_response(websocket, welcome_message, voice=config.get("voice", "alloy"))
        
        # Process messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "text_message":
                # Handle text message
                query = message["text"]
                await process_user_message(websocket, user_id, query, index, config, conversation_history)
            
            elif message["type"] == "audio_message":
                # Handle audio message
                audio_data = base64.b64decode(message["audio"])
                
                # Convert audio to file-like object
                audio_bytes = BytesIO(audio_data)
                audio_bytes.name = "audio.webm"  # Set a name for the file
                
                # Use Whisper API for speech-to-text
                try:
                    transcript = await transcribe_audio(audio_bytes)
                    
                    # Process the transcript as user message
                    if transcript:
                        await process_user_message(websocket, user_id, transcript, index, config, conversation_history)
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "text_response",
                            "text": "I couldn't understand what you said. Could you please try again?"
                        }))
                        
                except Exception as e:
                    logger.error(f"Error transcribing audio: {str(e)}")
                    await websocket.send_text(json.dumps({
                        "type": "text_response",
                        "text": f"Sorry, there was a problem processing your audio: {str(e)}"
                    }))
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "text_response",
            "text": f"Sorry, an error occurred: {str(e)}"
        }))
    finally:
        await websocket.close()

async def process_user_message(
    websocket: WebSocket,
    user_id: str,
    query: str,
    index: VectorStoreIndex,
    config: Dict,
    conversation_history: List[Dict]
):
    """Process a user message and send a response"""
    try:
        # Add the user message to history
        conversation_history.append({"role": "user", "content": query})
        
        # Query the index
        result = await get_answer(index, query, config)
        
        # Get the answer
        answer = result.get("answer", "I'm not sure how to respond to that.")
        
        # Add the assistant's response to history
        conversation_history.append({"role": "assistant", "content": answer})
        
        # Limit history size
        if len(conversation_history) > 10:
            # Keep system message if it exists, plus last 9 messages
            if conversation_history[0]["role"] == "system":
                conversation_history = [conversation_history[0]] + conversation_history[-9:]
            else:
                conversation_history = conversation_history[-10:]
        
        # Send text response
        await websocket.send_text(json.dumps({
            "type": "text_response",
            "text": answer
        }))
        
        # Send audio response
        await send_tts_response(websocket, answer, voice=config.get("voice", "alloy"))
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "text_response",
            "text": f"Sorry, an error occurred while processing your message: {str(e)}"
        }))

async def transcribe_audio(audio_file: BytesIO) -> str:
    """
    Transcribe audio using OpenAI's Whisper API
    
    Args:
        audio_file: Audio file as BytesIO
        
    Returns:
        Transcribed text
    """
    try:
        # Reset file pointer to start
        audio_file.seek(0)
        
        # Call Whisper API
        response = openai_client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1"
        )
        
        # Extract transcription text
        return response.text
    
    except Exception as e:
        logger.error(f"Error in transcription: {str(e)}")
        raise

async def send_tts_response(websocket: WebSocket, text: str, voice: str = "alloy"):
    """
    Convert text to speech and send as audio response
    
    Args:
        websocket: WebSocket connection
        text: Text to convert
        voice: TTS voice to use
    """
    try:
        # Call OpenAI TTS API
        response = openai_client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        # Get the audio data
        audio_data = BytesIO()
        for chunk in response.iter_bytes(chunk_size=4096):
            audio_data.write(chunk)
        
        # Convert to base64
        audio_data.seek(0)
        base64_audio = base64.b64encode(audio_data.read()).decode("utf-8")
        
        # Send audio response
        await websocket.send_text(json.dumps({
            "type": "audio_response",
            "audio": base64_audio
        }))
        
    except Exception as e:
        logger.error(f"Error in text-to-speech: {str(e)}")
        # Send error as text response instead
        await websocket.send_text(json.dumps({
            "type": "text_response",
            "text": f"(Error generating audio: {str(e)})"
        }))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"Starting voice agent on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port) 