import logging
import os
import asyncio
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
    
    def __init__(self) -> None:
        # Super simple initialization exactly like in main.py
        super().__init__(
            instructions=(
                "You are a helpful assistant. Begin with a friendly greeting. "
                "You help users find information in their documents."
            ),
            llm=openai.LLM(
                model="gpt-4o-mini",
                temperature=0.7,
            ),
        )
        logger.info("SimpleAgent initialized")
    
    async def on_enter(self):
        logger.info("Agent entering conversation, generating greeting")
        self.session.generate_reply()
    
    @function_tool
    async def query_documents(self, context: RunContext[UserData], query: str) -> str:
        """Search the user's personal documents for information.
        
        Args:
            query: The question to search for in the user's documents
        """
        try:
            user_data = context.userdata
            if not hasattr(user_data, 'index') or user_data.index is None:
                logger.error("No index available")
                return "I don't have access to your documents at the moment."
            
            logger.info(f"Querying documents with: {query}")
            query_engine = user_data.index.as_query_engine(use_async=True)
            result = await query_engine.aquery(query)
            logger.info(f"Document query result: {result}")
            
            # Clean up the response to remove markdown formatting
            response_text = str(result)
            # Remove markdown asterisks that might be read as "asterisk"
            response_text = response_text.replace('*', '')
            # Remove markdown formatting that might cause issues
            response_text = response_text.replace('_', '')
            response_text = response_text.replace('#', '')
            response_text = response_text.replace('`', '')
            
            logger.info(f"Cleaned response: {response_text}")
            return response_text
        except Exception as e:
            logger.error(f"Error querying documents: {str(e)}")
            return f"I encountered an error searching your documents: {str(e)}"

def prewarm(proc):
    """Initialize components during prewarm"""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Prewarm completed - VAD loaded")

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the user agent"""
    # Use global variables
    global GLOBAL_USER_ID, GLOBAL_COLLECTION_NAME, GLOBAL_PHONE_NUMBER
    
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
        
        # Load user index
        index = load_user_index(GLOBAL_USER_ID, GLOBAL_COLLECTION_NAME)
        logger.info(f"Loaded index for user {GLOBAL_USER_ID}")
        
        # Create user data
        userdata = UserData(
            user_id=GLOBAL_USER_ID,
            collection_name=GLOBAL_COLLECTION_NAME,
            config=config
        )
        userdata.index = index
        
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
        
        # Very simple initialization - exactly like main.py
        logger.info("Creating basic agent session")
        session = AgentSession[UserData](
            vad=vad,
            llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
            stt=deepgram.STT(model="nova-2-general"),
            tts=cartesia.TTS(),  # No customization at all
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
        
        # Start session - exactly like main.py
        logger.info("Starting agent session")
        await session.start(
            agent=SimpleAgent(),
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