# web-user.py
import logging
import os
import asyncio
import re
import json
import ssl 
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path
import aiohttp 

from dotenv import load_dotenv

from livekit import api
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
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

load_dotenv() 
logger = logging.getLogger("user-agent") 
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))
global_query_engine = None

# --- SSL Patching Logic ---
_original_ssl_create_default_context = None
_original_aiohttp_tcp_connector_init = None 

def _get_custom_non_verifying_ssl_context_for_global_patch():
    # Using logger here as basicConfig should be set by the time __main__ calls it,
    # or if run as module, the parent logger should be configured.
    # If this runs too early before logging is set, change to print().
    logger.info("Creating custom non-verifying SSL context for global patch.")
    custom_ctx = ssl.create_default_context() 
    custom_ctx.check_hostname = False
    custom_ctx.verify_mode = ssl.CERT_NONE
    return custom_ctx

def _apply_ssl_bypasses():
    global _original_ssl_create_default_context, _original_aiohttp_tcp_connector_init
    logger.warning("Attempting to apply ALL SSL bypass patches.")

    if _original_ssl_create_default_context is None:
        _original_ssl_create_default_context = ssl.create_default_context
        _non_verifying_context_for_ssl_default = _original_ssl_create_default_context() 
        _non_verifying_context_for_ssl_default.check_hostname = False
        _non_verifying_context_for_ssl_default.verify_mode = ssl.CERT_NONE
        logger.info("Created non-verifying SSL context for ssl.create_default_context patch.")
        def _patched_create_default_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
            logger.warning(f"Global SSL Patch: ssl.create_default_context returning custom NON-VERIFYING SSL context (original purpose: {purpose}).")
            return _non_verifying_context_for_ssl_default
        if ssl.create_default_context is not _patched_create_default_context:
            ssl.create_default_context = _patched_create_default_context
            logger.info("Applied global monkey patch to ssl.create_default_context.")
    else:
        logger.debug("Original ssl.create_default_context already stored; patch might be active.")

    if _original_aiohttp_tcp_connector_init is None:
        if hasattr(aiohttp, 'TCPConnector'): 
            _original_aiohttp_tcp_connector_init = aiohttp.TCPConnector.__init__
            logger.info("Stored original aiohttp.TCPConnector.__init__ for patching.")
            def PatchedAIOHTTPTCPConnector__init__(self_connector, *args_patch, **kwargs_patch):
                original_ssl_kwarg = kwargs_patch.get('ssl')
                kwargs_patch['ssl'] = False 
                logger.warning(f"Patched aiohttp.TCPConnector.__init__ called, forcing ssl=False. Original ssl kwarg: {original_ssl_kwarg}.")
                _original_aiohttp_tcp_connector_init(self_connector, *args_patch, **kwargs_patch)
            if aiohttp.TCPConnector.__init__ is not PatchedAIOHTTPTCPConnector__init__:
                aiohttp.TCPConnector.__init__ = PatchedAIOHTTPTCPConnector__init__
                logger.info("aiohttp.TCPConnector has been monkey-patched to use ssl=False.")
        else:
            logger.warning("aiohttp.TCPConnector not found for patching.")
    else:
        logger.debug("Original aiohttp.TCPConnector.__init__ already stored for ssl=False patch.")

    os.environ["AIOHTTP_SSL_VERIFY"] = "0"
    logger.info("Set AIOHTTP_SSL_VERIFY=0 environment variable.")

# !!!!! TEMPORARY CHANGE FOR DEBUGGING !!!!!
# Force the patch to apply regardless of the environment variable for this test run
logger.warning("FORCING SSL BYPASS PATCHES TO APPLY for this test run in web-user.py (module scope)!")
_apply_ssl_bypasses()
# !!!!! END TEMPORARY CHANGE !!!!!
# --- End SSL Patching Logic ---

@dataclass
class UserData:
    user_id: Optional[str] = None
    collection_name: Optional[str] = None
    agent_behavior_config: Dict[str, Any] = field(default_factory=dict)
    index: Any = None

def get_user_paths(user_id: str) -> Dict[str, Path]:
    if not user_id:
        logger.error("get_user_paths called with no user_id")
        raise ValueError("user_id cannot be None for get_user_paths")
    user_dir = BASE_STORAGE_DIR / user_id
    return {
        "base": user_dir,
        "index_base": user_dir / "knowledge-storage",
        "config_file": user_dir / "config" / "agent_config.json"
    }

def load_user_behavioral_config(user_id: str) -> Dict[str, Any]:
    if not user_id:
        logger.error("load_user_behavioral_config called with no user_id.")
        return {
            "system_prompt": "You are a generic AI assistant.",
            "voice": "alloy", "model": "gpt-4o-mini", "agent_name": "Assistant"
        }
    paths = get_user_paths(user_id)
    config_file = paths["config_file"]
    default_behavior_config = {
        "system_prompt": "You are a helpful AI assistant. Please be concise.",
        "voice": "alloy", "model": "gpt-4o-mini", "agent_name": "Assistant"
    }
    if not config_file.exists():
        logger.warning(f"Behavioral config file not found for user {user_id} at {config_file}. Using defaults.")
        return default_behavior_config
    try:
        with open(config_file, "r") as f:
            full_user_config = json.load(f)
        loaded_behavior_config = {}
        for key, default_value in default_behavior_config.items():
            loaded_behavior_config[key] = full_user_config.get(key, default_value)
            if key not in full_user_config or full_user_config.get(key) is None:
                 logger.info(f"Behavioral setting '{key}' not found or null in config for user {user_id}, using default: '{default_value}'")
        return loaded_behavior_config
    except Exception as e:
        logger.error(f"Error loading behavioral config for user {user_id} from {config_file}: {str(e)}. Using defaults.")
        return default_behavior_config

def load_user_index(user_id: str, collection_name: Optional[str] = None):
    if not user_id:
        logger.error("load_user_index called with no user_id.")
        return None
    paths = get_user_paths(user_id)
    index_storage_dir = paths["index_base"]
    actual_index_dir_to_load = index_storage_dir
    if collection_name:
        actual_index_dir_to_load = index_storage_dir / collection_name
        logger.info(f"Attempting to load index for user {user_id} from specific collection: {collection_name} at {actual_index_dir_to_load}")
    else:
        logger.info(f"No specific collection name provided for user {user_id}. Attempting to load index from default location: {actual_index_dir_to_load}")

    if not actual_index_dir_to_load.is_dir() or not (actual_index_dir_to_load / "docstore.json").exists():
        logger.warning(f"Index directory/files not found for user {user_id} at {actual_index_dir_to_load}.")
        return None
    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(actual_index_dir_to_load))
        index = load_index_from_storage(storage_context)
        logger.info(f"Successfully loaded index for user {user_id} from {actual_index_dir_to_load}")
        return index
    except Exception as e:
        logger.error(f"Error loading index for user {user_id} from {actual_index_dir_to_load}: {str(e)}")
        return None

async def create_sip_participant(room_name: str, phone_number: str):
    LIVEKIT_URL = os.getenv('LIVEKIT_URL')
    LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
    LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
    SIP_TRUNK_ID = os.getenv('SIP_TRUNK_ID')
    
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        logger.error("Missing LiveKit URL/API Key/Secret environment variables for SIP call.")
        raise ValueError("Missing LiveKit credentials for SIP call.")
    if not SIP_TRUNK_ID:
        logger.error("Missing SIP_TRUNK_ID environment variable for SIP call.")
        raise ValueError("SIP_TRUNK_ID is required for outbound SIP calls.")

    logger.info(f"Initiating outbound SIP call to {phone_number} in room {room_name} using trunk {SIP_TRUNK_ID}")
    lk_api = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    try:
        await lk_api.sip.create_sip_participant(
            request=api.CreateSIPParticipantRequest(
                sip_trunk_id=SIP_TRUNK_ID,
                sip_call_to=phone_number,
                room_name=room_name,
                participant_identity=f"sip_out_{phone_number.replace('+', '').replace(' ', '')}",
                participant_name=f"Call to {phone_number}",
                play_ringtone=True
            )
        )
        logger.info(f"SIP participant creation requested for {phone_number} in room {room_name}")
    except Exception as e:
        logger.error(f"Failed to create SIP participant for {phone_number}: {e}")
        raise
    finally:
        await lk_api.aclose()

class SimpleAgent(Agent):
    def __init__(self, agent_behavior_config: Dict[str, Any]) -> None:
        system_prompt = agent_behavior_config.get("system_prompt", "You are a helpful assistant.")
        agent_name = agent_behavior_config.get("agent_name", "Assistant")
        llm_model = agent_behavior_config.get("model", "gpt-4o-mini")

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
        logger.info(f"SimpleAgent initializing with: Name='{agent_name}', Model='{llm_model}'. Prompt starts: '{enhanced_prompt[:100]}...'")
        
        super().__init__(
            instructions=enhanced_prompt,
            llm=openai.LLM(model=llm_model, temperature=0.7),
            tts=cartesia.TTS()
        )
    
    async def on_enter(self):
        user_id_log = "UnknownUser (session not yet fully linked in on_enter)"
        if hasattr(self, 'session') and self.session:
            if self.session.userdata and hasattr(self.session.userdata, 'user_id'): 
                user_id_log = self.session.userdata.user_id
            
            logger.info(f"Agent (ID: {self.id if hasattr(self, 'id') else 'N/A'}) on_enter called for user {user_id_log}.")
            greeting_text = "Hello! How can I help you today?"
            await self.session.say(greeting_text) 
            logger.info(f"Agent {self.id if hasattr(self, 'id') else 'N/A'} said greeting via on_enter.")
        else:
            logger.warning(f"Agent on_enter called, but self.session (or self.session.userdata) is not yet available to say greeting or log user_id.")

    async def process_user_text(self, session: AgentSession, text: str):
        user_id_log = session.userdata.user_id if session.userdata else "UnknownUser"
        logger.info(f"User {user_id_log} said: '{text}' - Agent will generate reply.")
        await session.generate_reply_for_user_text(text)

    def _filter_text_for_speech(self, text_to_filter: Optional[str]) -> Optional[str]:
        if not text_to_filter: return text_to_filter
        filtered_content = text_to_filter
        problematic_chars = ['*', '#', '_', '`', '~', '|', '<', '>', '[', ']']
        for char in problematic_chars:
            filtered_content = filtered_content.replace(char, '')
        filtered_content = re.sub(r'\s+', ' ', filtered_content).strip()
        if text_to_filter != filtered_content:
            user_id_for_log = "UnknownUser"
            if hasattr(self, 'session') and self.session and hasattr(self.session, 'userdata') and self.session.userdata:
                user_id_for_log = self.session.userdata.user_id
            logger.info(f"User {user_id_for_log}: Filtered agent response. Original: '{text_to_filter[:50]}...', Filtered: '{filtered_content[:50]}...'")
        return filtered_content

    @function_tool()
    async def query_documents(self, query: str) -> str:
        global global_query_engine
        if not hasattr(self, 'session') or not self.session:
            logger.error("query_documents called but self.session is not available on the agent instance.")
            return "I'm having trouble accessing session details right now."
        user_data: UserData = self.session.userdata
        if not user_data or not user_data.user_id:
            logger.error("query_documents called but user_id is not available in self.session.userdata.")
            return "User context is missing for document search."
        try:
            logger.info(f"User {user_data.user_id} document query request: '{query}'")
            current_job_query_engine = global_query_engine
            if current_job_query_engine is None:
                logger.error(f"Query engine not available for user {user_data.user_id}. Index might not have loaded or engine init failed.")
                return "I currently don't have access to the documents to answer that."
            logger.info(f"Executing RAG query for user {user_data.user_id}: '{query}'")
            res = await current_job_query_engine.aquery(query)
            raw_result = str(res)
            logger.info(f"RAG query for user {user_data.user_id} successful, result length: {len(raw_result)}")
            if not raw_result.strip():
                logger.warning(f"Empty RAG result for user {user_data.user_id} on query: '{query}'")
                return "I searched the documents but couldn't find relevant information for your query."
            cleaned_document_text = self._filter_text_for_speech(raw_result)
            final_text = f"Based on the available documents: {cleaned_document_text}"
            logger.info(f"Cleaned document search result for user {user_data.user_id}: {final_text[:100]}...")
            return final_text
        except Exception as e:
            logger.error(f"General error in query_documents for user {user_data.user_id} on query '{query}': {str(e)}", exc_info=True)
            return f"I encountered an unexpected issue while searching the documents: {str(e)}"

def prewarm(worker: WorkerOptions):
    logger.info("Prewarming VAD model...")
    try:
        silero.VAD.load()
        logger.info("Silero VAD model prewarmed (cached).")
    except Exception as e:
        logger.error(f"Error during VAD prewarming: {e}", exc_info=True)

async def entrypoint(ctx: JobContext):
    user_id = os.environ.get("USER_AGENT_USER_ID")
    collection_name = os.environ.get("USER_AGENT_COLLECTION")
    phone_number_to_dial = os.environ.get("USER_AGENT_PHONE")
    global global_query_engine

    if not user_id:
        logger.error("CRITICAL: USER_AGENT_USER_ID not found in environment. Agent cannot start job.")
        return

    logger.info(f"Agent entrypoint started for job {ctx.job.id}, user_id: {user_id}")
    logger.info(f"  Collection from ENV: {collection_name}")
    logger.info(f"  Phone from ENV: {phone_number_to_dial}")

    # Global SSL patch is applied at module load time if DISABLE_SSL_VERIFY=1.
    # No specific SSL action needed within entrypoint itself now.

    try:
        agent_b_config = load_user_behavioral_config(user_id)
        logger.info(f"Loaded behavioral config for user {user_id}: {agent_b_config}")
        
        index = load_user_index(user_id, collection_name)
        if index:
            logger.info(f"Index loaded successfully for user {user_id}, collection '{collection_name}'.")
            try:
                global_query_engine = index.as_query_engine(use_async=True)
                logger.info("Query engine initialized/updated successfully for this job.")
            except Exception as e_qe:
                logger.error(f"Failed to initialize query engine from loaded index: {e_qe}")
                global_query_engine = None
        else:
            logger.warning(f"No index loaded for user {user_id}, collection '{collection_name}'. Document search may not be available.")
            global_query_engine = None

        user_data_for_session = UserData(
            user_id=user_id,
            collection_name=collection_name,
            agent_behavior_config=agent_b_config,
            index=index
        )
        
        required_env_keys = ["OPENAI_API_KEY", "DEEPGRAM_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
        if os.environ.get("CARTESIA_API_KEY"): 
            required_env_keys.append("CARTESIA_API_KEY")
        
        if phone_number_to_dial and not os.environ.get("SIP_TRUNK_ID"):
            logger.error(f"CRITICAL: SIP_TRUNK_ID is required for outbound call to {phone_number_to_dial} but not set.")
            raise ValueError("SIP_TRUNK_ID missing for an intended outbound call.")

        for req_key in required_env_keys:
            if not os.environ.get(req_key):
                logger.error(f"CRITICAL: Required environment variable '{req_key}' is not set for user {user_id}. Agent cannot function.")
                raise EnvironmentError(f"Agent misconfiguration: Missing environment variable {req_key}")

        await ctx.connect()
        logger.info(f"Connected to LiveKit room: {ctx.room.name} for user {user_id}")
        
        @ctx.room.on("participant_connected")
        def on_participant_connected(participant, *_):
            logger.info(f"Room {ctx.room.name}: Participant joined: {participant.identity} ({participant.name})")
        
        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant, *_):
            logger.info(f"Room {ctx.room.name}: Participant left: {participant.identity} ({participant.name})")
        
        if phone_number_to_dial:
            logger.info(f"Outbound call mode: Attempting to call {phone_number_to_dial} for room {ctx.room.name}")
            try:
                await create_sip_participant(ctx.room.name, phone_number_to_dial)
            except Exception as e_sip:
                logger.error(f"Failed to initiate SIP call to {phone_number_to_dial}: {e_sip}")
        else:
            logger.info(f"Inbound/Web call mode for room {ctx.room.name}: Waiting for participants.")
        
        vad = silero.VAD.load()
        logger.info("Silero VAD loaded for session.")
        
        usage_collector = metrics.UsageCollector()
        llm_model_to_use = agent_b_config.get("model", "gpt-4o-mini")

        agent_instance = SimpleAgent(agent_b_config)

        session = AgentSession[UserData](
            vad=vad,
            llm=openai.LLM(model=llm_model_to_use, temperature=0.7),
            stt=deepgram.STT(model="nova-2-general"),
            tts=cartesia.TTS(), 
            userdata=user_data_for_session
        )
        
        original_say_method = session.say 
        async def filtered_say_wrapper(text: str, **kwargs):
            filtered_text = agent_instance._filter_text_for_speech(text)
            return await original_say_method(filtered_text, **kwargs)
        session.say = filtered_say_wrapper

        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics); usage_collector.collect(ev.metrics)
            logger.info(f"User {user_id} Metrics: {ev.metrics}")
        
        @session.on("transcription_updated")
        def on_transcription_updated(text: str, final: bool):
            if final and text.strip():
                logger.info(f"User {user_id} FINAL TRANSCRIPTION: '{text}'")
                asyncio.create_task(agent_instance.process_user_text(session, text))
            elif not final:
                logger.debug(f"User {user_id} INTERIM TRANSCRIPTION: '{text}'")

        @session.on("agent_speech_started")
        def on_agent_speech_started(): logger.info(f"User {user_id} AGENT SPEECH STARTED")
        
        @session.on("agent_speech_finished")
        def on_agent_speech_finished(): logger.info(f"User {user_id} AGENT SPEECH FINISHED")

        async def log_final_usage():
            summary = usage_collector.get_summary()
            logger.info(f"User {user_id} Final Usage Summary for job {ctx.job.id}: {summary}")
        
        ctx.add_shutdown_callback(log_final_usage)

        logger.info(f"Starting agent session processing for user {user_id} in room {ctx.room.name}...")
        await session.start(
            room=ctx.room,
            agent=agent_instance,
            room_input_options=RoomInputOptions(),
            room_output_options=RoomOutputOptions(transcription_enabled=True)
        )
        logger.info(f"Agent session processing finished for user {user_id} in room {ctx.room.name}.")
        
    except Exception as e:
        logger.error(f"Error in agent entrypoint for job {ctx.job.id}, user {user_id}: {str(e)}", exc_info=True)
        try:
            if ctx.room and ctx.room.local_participant:
                error_payload = {"error": "An agent processing error occurred.", "detail": str(e)[:200]}
                await ctx.room.local_participant.publish_data(
                    payload=json.dumps(error_payload)
                )
                logger.info(f"Sent error details to room for user {user_id}.")
            else:
                logger.warning(f"Cannot send error to room for user {user_id}: room or local_participant not available during error handling.")
        except Exception as send_e:
            logger.error(f"Failed to send error details to room for user {user_id}: {send_e}")
        raise
    finally:
        logger.info(f"Agent entrypoint cleanup for job {ctx.job.id}, user {user_id}.")

if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main_script_logger = logging.getLogger("user-agent") 
    
    # The global SSL patch (_apply_ssl_bypasses_if_needed) is called when the module is first loaded (see top of file)
    # conditional on DISABLE_SSL_VERIFY=1.
    
    main_script_logger.info(f"{Path(__file__).name} executed directly as __main__. User ID from ENV: {os.environ.get('USER_AGENT_USER_ID')}")

    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm, 
        port=0 
    ))