import logging
import os
import asyncio
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    RoomInputOptions,
    RoomOutputOptions,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.plugins import deepgram, openai, silero, cartesia
from livekit.agents.voice import MetricsCollectedEvent
from livekit.agents.llm import function_tool

from llama_index.core import (
    StorageContext,
    load_index_from_storage,
)

# Load environment variables
load_dotenv()

logger = logging.getLogger("user-agent")

# Base directory for all user data
BASE_STORAGE_DIR = Path("./user_data")

# Global variables to store user information
GLOBAL_USER_ID = os.environ.get("USER_AGENT_USER_ID")
GLOBAL_COLLECTION_NAME = os.environ.get("USER_AGENT_COLLECTION")
GLOBAL_PHONE_NUMBER = os.environ.get("USER_AGENT_PHONE")

# Global query engine - just like in main.py
global_query_engine = None

@dataclass
class UserData:
    user_id: Optional[str] = None
    collection_name: Optional[str] = None
    config: Dict[str, Any] = None
    index = None

def get_user_paths(user_id: str) -> Dict[str, Path]:
    """Get all paths for a specific user"""
    user_dir = BASE_STORAGE_DIR / user_id
    
    return {
        "base": user_dir,
        "index": user_dir / "knowledge-storage",
        "config": user_dir / "config" / "agent_config.json"
    }

def load_user_config(user_id: str) -> Dict[str, Any]:
    """Load user configuration from JSON file"""
    paths = get_user_paths(user_id)
    config_file = paths["config"]
    
    # Default configuration
    default_config = {
        "system_prompt": (
            "You are a helpful AI assistant. Provide accurate and concise information. "
            "Answer questions based on your knowledge base."
        ),
        "voice": "alloy",
        "model": "gpt-4o-mini",
        "agent_name": "Assistant"
    }
    
    if not config_file.exists():
        logger.warning(f"Config file not found for user {user_id}, using defaults")
        return default_config
    
    try:
        with open(config_file, "r") as f:
            user_config = json.load(f)
            # Ensure we have all the required fields with defaults if missing
            for key, default_value in default_config.items():
                if key not in user_config or user_config[key] is None:
                    user_config[key] = default_value
                    logger.info(f"Missing {key} in config, using default: {default_value}")
            return user_config
    except Exception as e:
        logger.error(f"Error loading config for user {user_id}: {str(e)}")
        return default_config

def load_user_index(user_id: str, collection_name: Optional[str] = None):
    """Load the index for a specific user and collection"""
    paths = get_user_paths(user_id)
    index_dir = paths["index"]
    
    if collection_name:
        index_dir = index_dir / collection_name
    
    if not index_dir.exists():
        raise ValueError(f"Index directory not found: {index_dir}")
    
    try:
        storage_context = StorageContext.from_defaults(persist_dir=index_dir)
        return load_index_from_storage(storage_context)
    except Exception as e:
        logger.error(f"Error loading index for user {user_id}: {str(e)}")
        raise ValueError(f"Failed to load index for user {user_id}")

async def create_sip_participant(room_name: str, phone_number: str):
    """Create a SIP participant for outbound calling"""
    # Get LiveKit credentials from environment
    LIVEKIT_URL = os.getenv('LIVEKIT_URL')
    LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
    LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
    SIP_TRUNK_ID = os.getenv('SIP_TRUNK_ID')
    
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, SIP_TRUNK_ID]):
        raise ValueError("Missing required environment variables for SIP call")

    logger.info(f"Initiating outbound call to {phone_number}")
    
    livekit_api = api.LiveKitAPI(
        LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    )

    await livekit_api.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            sip_trunk_id=SIP_TRUNK_ID,
            sip_call_to=phone_number,
            room_name=room_name,
            participant_identity=f"sip_{phone_number}",
            participant_name="Call Recipient",
            play_ringtone=1
        )
    )
    await livekit_api.aclose()
    
    logger.info(f"SIP participant created for {phone_number} in room {room_name}")

class SimpleAgent(Agent):
    """A simple agent that responds to user queries using document search"""
    
    def __init__(self, user_config: Dict[str, Any]) -> None:
        # Get system prompt from user config
        system_prompt = user_config.get("system_prompt", 
            "You are a helpful assistant. You help users find information in their documents.")
        
        agent_name = user_config.get("agent_name", "Assistant")
        
        # Enhanced system prompt with identity awareness and improved instructions
        enhanced_prompt = (
            f"{system_prompt}\n\n"
            f"Your name is {agent_name}. "
            "You are speaking with customers of the document owner, not the document owner themselves. "
            "The documents you have access to belong to the business or service provider, but you are "
            "speaking with their customers or clients who are seeking information. "
            "When asked about document content, use the query_documents function and cite the specific information found. "
            "Be concise, clear, and helpful. When you reference document information, make sure to explain it in a way that's easy to understand. "
            "Always answer using complete, grammatically correct sentences. Prioritize information from the documents when answering questions.\n\n"
            "IMPORTANT: NEVER use asterisks (*), hash symbols (#), or any other markdown formatting in your responses. "
            "Do not use any special characters or formatting that would cause issues in text-to-speech systems.\n\n"
            "Remember that you represent the document owner's business or service when speaking with their customers. "
            "Provide accurate information from the documents in a professional and helpful manner."
        )
        
        logger.info(f"Using system prompt: {enhanced_prompt}")
        
        # Initialize with user's system prompt
        super().__init__(
            instructions=enhanced_prompt,
            llm=openai.LLM(
                model=user_config.get("model", "gpt-4o-mini"),
                temperature=0.7,
            ),
        )
        logger.info(f"SimpleAgent initialized with identity: {agent_name} (speaking with customers)")
    
    async def on_enter(self):
        logger.info("Agent entering conversation, generating greeting")
        self.session.generate_reply()
    
    # Override the generate_reply method to filter all responses
    async def generate_reply(self, ctx):
        # Call the original method to generate a reply
        result = await super().generate_reply(ctx)
        
        # Filter the result to remove problematic characters from ALL responses
        if hasattr(result, 'content') and result.content:
            # Replace markdown formatting
            filtered_content = result.content
            
            # Remove all problematic characters
            problematic_chars = ['*', '#', '_', '`', '~', '|', '<', '>', '[', ']']
            for char in problematic_chars:
                filtered_content = filtered_content.replace(char, '')
            
            # Update the content
            result.content = filtered_content
            logger.info(f"Filtered agent response to remove problematic characters")
        
        return result
    
    @function_tool
    async def query_documents(self, context: RunContext[UserData], query: str) -> str:
        """Search the user's personal documents for information.
        
        Args:
            query: The question to search for in the user's documents
        """
        global global_query_engine
        
        try:
            # Log the query for debugging
            logger.info(f"Document query request: {query}")
            
            # Use global query engine if available, otherwise create one
            if global_query_engine is None:
                logger.info("Global query engine not initialized, creating new one")
                
                user_data = context.userdata
                logger.info(f"User data index: {user_data.index is not None}")
                
                if not user_data.index:
                    logger.error("No index available in user data")
                    return "I don't have access to your documents at the moment."
                
                try:
                    global_query_engine = user_data.index.as_query_engine(use_async=True)
                    logger.info("Created new global query engine successfully")
                except Exception as e:
                    logger.error(f"Failed to create query engine: {str(e)}")
                    return f"I encountered an error accessing your documents: {str(e)}"
            
            # Execute the query with robust error handling
            try:
                logger.info(f"Executing RAG query: {query}")
                res = await global_query_engine.aquery(query)
                logger.info(f"RAG query successful, result length: {len(str(res))}")
                raw_result = str(res)
            except Exception as e:
                logger.error(f"RAG query failed: {str(e)}")
                return f"I tried to search your documents, but encountered an error: {str(e)}"
            
            # If we get an empty result, inform the user
            if not raw_result.strip():
                logger.warning("Empty RAG result")
                return "I searched your documents but couldn't find relevant information for your query."
            
            # Most aggressive cleaning possible - strip ALL potentially problematic characters
            try:
                # Strip ALL problematic characters completely
                import re
                
                # Remove all markdown and special characters
                problematic_chars = ['*', '#', '_', '`', '~', '|', '<', '>', '[', ']', '(', ')', '{', '}', '+', '-', '=', '$', '^', '&']
                clean_text = raw_result
                for char in problematic_chars:
                    clean_text = clean_text.replace(char, '')
                
                # Remove URLs and email addresses
                clean_text = re.sub(r'https?://\S+', '', clean_text)
                clean_text = re.sub(r'\S+@\S+', '', clean_text)
                
                # Clean up whitespace
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                
                # Add prefix
                final_text = f"Here's what I found in your documents: {clean_text}"
                logger.info(f"Aggressively cleaned document result: {final_text[:100]}...")
                return final_text
            except Exception as e:
                logger.error(f"Error in cleaning result: {str(e)}")
                # Extreme fallback - only alphanumeric and basic punctuation
                clean_fallback = ''.join(c for c in raw_result if c.isalnum() or c in ' .,;:?!')
                return f"From your documents: {clean_fallback}"
            
        except Exception as e:
            logger.error(f"General error in query_documents: {str(e)}")
            return f"I encountered an error with the document search system: {str(e)}"

def prewarm(proc):
    """Initialize components during prewarm"""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Prewarm completed - VAD loaded")

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the user agent"""
    # Use global variables
    global GLOBAL_USER_ID, GLOBAL_COLLECTION_NAME, GLOBAL_PHONE_NUMBER, global_query_engine
    
    # Log the values to help debugging
    logger.info(f"User ID: {GLOBAL_USER_ID}")
    logger.info(f"Collection: {GLOBAL_COLLECTION_NAME}")
    logger.info(f"Phone: {GLOBAL_PHONE_NUMBER}")
    
    # Verify we have a user ID
    if not GLOBAL_USER_ID:
        logger.error("No user ID provided")
        return
    
    try:
        # Connect to room
        await ctx.connect()
        logger.info(f"Connected to room: {ctx.room.name}")
        
        # Load user configuration
        config = load_user_config(GLOBAL_USER_ID)
        logger.info(f"Loaded user config: {config}")
        
        # Load user index with better error handling
        try:
            index = load_user_index(GLOBAL_USER_ID, GLOBAL_COLLECTION_NAME)
            logger.info(f"Loaded index for user {GLOBAL_USER_ID}")
        except Exception as e:
            logger.error(f"Failed to load index: {str(e)}")
            index = None
        
        # Create user data
        userdata = UserData(
            user_id=GLOBAL_USER_ID,
            collection_name=GLOBAL_COLLECTION_NAME,
            config=config
        )
        userdata.index = index
        
        # Initialize global query engine with error handling
        if index:
            try:
                global_query_engine = index.as_query_engine(use_async=True)
                logger.info("Initialized global query engine successfully")
            except Exception as e:
                logger.error(f"Failed to initialize global query engine: {str(e)}")
                global_query_engine = None
        else:
            logger.warning("No index loaded, global query engine not initialized")
            global_query_engine = None
        
        # If phone number is provided, initiate an outbound call
        if GLOBAL_PHONE_NUMBER:
            await create_sip_participant(ctx.room.name, GLOBAL_PHONE_NUMBER)
        
        # Get VAD from context
        vad = ctx.proc.userdata.get("vad")
        if not vad:
            logger.info("Loading new VAD instance")
            vad = silero.VAD.load()
        
        # Log metrics
        usage_collector = metrics.UsageCollector()
        
        # EXACTLY like main.py
        logger.info("Creating agent session exactly like main.py")
        session = AgentSession[UserData](
            vad=vad,
            llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
            stt=deepgram.STT(model="nova-2-general"),
            tts=cartesia.TTS(),  # Standard TTS with no modifications
            userdata=userdata
        )
        
        # Add metrics collection
        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)
            logger.info(f"Metrics collected: {ev.metrics}")
        
        # Add verbose logging
        @session.on("speech_started")
        def on_speech_started():
            logger.info("SPEECH STARTED: User is speaking")
        
        @session.on("speech_stopped")
        def on_speech_stopped():
            logger.info("SPEECH STOPPED: User stopped speaking")
        
        @session.on("transcription")
        def on_transcription(text):
            logger.info(f"TRANSCRIPTION: {text}")
        
        @session.on("agent_speaking")
        def on_agent_speaking():
            logger.info("AGENT SPEAKING: TTS output started")
        
        @session.on("agent_done_speaking")
        def on_agent_done_speaking():
            logger.info("AGENT DONE SPEAKING: TTS output finished")
        
        # Add shutdown callback
        async def log_usage():
            summary = usage_collector.get_summary()
            logger.info(f"Usage summary: {summary}")
        
        ctx.add_shutdown_callback(log_usage)
        
        # Start session
        logger.info("Starting agent session")
        await session.start(
            agent=SimpleAgent(config),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
            room_output_options=RoomOutputOptions(transcription_enabled=True),
        )
        logger.info("Agent session started successfully")
        
    except Exception as e:
        logger.error(f"Error in agent entrypoint: {str(e)}")
        raise

if __name__ == "__main__":
    # Initialize the default logging configuration
    logging.basicConfig(level=logging.INFO)
    
    # Import json here to avoid circular import issues
    import json
    
    # Run the app with the LiveKit CLI
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm)) 