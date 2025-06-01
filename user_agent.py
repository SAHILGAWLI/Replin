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
    ChatContext,
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
    
    # The index is set separately
    def set_index(self, index):
        self.index = index
    
    def get_index(self):
        return getattr(self, 'index', None)

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
    
    if not config_file.exists():
        logger.warning(f"Config file not found for user {user_id}, using defaults")
        return {
            "system_prompt": (
                "You are a helpful AI assistant. Provide accurate and concise information. "
                "Answer questions based on your knowledge base."
            ),
            "voice": "alloy",
            "model": "gpt-4o-mini",
            "agent_name": "Assistant"
        }
    
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config for user {user_id}: {str(e)}")
        raise ValueError(f"Failed to load configuration for user {user_id}")

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

class PersonalAssistantAgent(Agent):
    def __init__(self) -> None:
        # Explicitly set TTS here in the constructor
        # Use a simple fixed system prompt - ignoring any custom ones that might be causing issues
        super().__init__(
            instructions=(
                "You are a helpful AI assistant. Answer questions directly and concisely."
            ),
            llm=openai.LLM(
                model="gpt-4o-mini",
                temperature=0.7,
            ),
            # Explicitly set TTS here
            tts=cartesia.TTS(),
        )
        logger.info("PersonalAssistantAgent initialized with TTS and fixed system prompt")
    
    async def on_enter(self):
        # Generate initial greeting
        logger.info("Agent on_enter called, generating initial greeting")
        self.session.generate_reply()
    
    @function_tool
    async def query_documents(self, context: RunContext[UserData], query: str) -> str:
        """Search the user's personal documents for information.
        
        Args:
            query: The question to search for in the user's documents
        """
        try:
            user_index = context.userdata.get_index()
            if not user_index:
                return "I don't have access to your documents at the moment."
            
            logger.info(f"Querying user documents with: {query}")
            query_engine = user_index.as_query_engine(use_async=True)
            result = await query_engine.aquery(query)
            logger.info(f"Document query result: {result}")
            
            return str(result)
        except Exception as e:
            logger.error(f"Error querying documents: {str(e)}")
            return f"I encountered an error searching your documents: {str(e)}"

def prewarm(proc):
    """Initialize components during prewarm"""
    proc.userdata["vad"] = silero.VAD.load()

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
        
        # Create user data with index
        userdata = UserData(
            user_id=GLOBAL_USER_ID,
            collection_name=GLOBAL_COLLECTION_NAME,
            config=config
        )
        userdata.set_index(index)
        
        # If phone number is provided, initiate an outbound call
        if GLOBAL_PHONE_NUMBER:
            await create_sip_participant(ctx.room.name, GLOBAL_PHONE_NUMBER)
        
        # Load VAD during initialization
        vad = ctx.proc.userdata.get("vad")
        if not vad:
            logger.info("Loading new VAD instance")
            vad = silero.VAD.load()
        
        # Log metrics as they are emitted
        usage_collector = metrics.UsageCollector()
        
        # Initialize agent session with explicit parameters
        # Ignore any custom config that might be causing issues
        logger.info("Creating agent session with fixed settings")
        session = AgentSession[UserData](
            vad=vad,
            llm=openai.LLM(
                model="gpt-4o-mini",
                temperature=0.7,
            ),
            stt=deepgram.STT(model="nova-2-general"),
            # Use simple TTS without any custom voice settings
            tts=cartesia.TTS(),
            userdata=userdata
        )
        logger.info("Agent session created with fixed settings")
        
        # Add monitoring for speech events
        @session.on("speech_started")
        def on_speech_started():
            logger.info("SPEECH STARTED - User is speaking")
        
        @session.on("speech_stopped")
        def on_speech_stopped():
            logger.info("SPEECH STOPPED - User stopped speaking")
        
        @session.on("transcription")
        def on_transcription(text):
            logger.info(f"TRANSCRIPTION: {text}")
            
        @session.on("agent_speaking")
        def on_agent_speaking():
            logger.info("AGENT SPEAKING - TTS output started")
            
        @session.on("agent_done_speaking")
        def on_agent_done_speaking():
            logger.info("AGENT DONE SPEAKING - TTS output finished")
        
        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)
            logger.info(f"Collected metrics: {ev.metrics}")
        
        async def log_usage():
            summary = usage_collector.get_summary()
            logger.info(f"Usage: {summary}")
        
        ctx.add_shutdown_callback(log_usage)
        
        # Start the session with our agent
        logger.info("Starting agent session...")
        await session.start(
            agent=PersonalAssistantAgent(),
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