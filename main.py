import logging
import os
import asyncio
from dataclasses import dataclass
from typing import Optional, AsyncIterable, AsyncGenerator
from pathlib import Path

from dotenv import load_dotenv

from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    ChatContext,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.agents.job import get_job_context
from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import deepgram, openai, silero, cartesia, elevenlabs

# Import RAG components
from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)

# uncomment to enable Krisp BVC noise cancellation, currently supported on Linux and MacOS
# from livekit.plugins import noise_cancellation

## The Aaple Sarkar agent is a multi-agent system that helps citizens resolve their government-related queries.
## It has an initial agent to gather citizen information and a main service agent to provide assistance.

logger = logging.getLogger("gov-agent")

load_dotenv()

# Initialize RAG index
THIS_DIR = Path(__file__).parent
PERSIST_DIR = THIS_DIR / "query-engine-storage"
if not PERSIST_DIR.exists():
    # load the documents and create the index
    logger.info("Creating new RAG index")
    documents = SimpleDirectoryReader(THIS_DIR / "data").load_data()
    index = VectorStoreIndex.from_documents(documents)
    # store it for later
    index.storage_context.persist(persist_dir=PERSIST_DIR)
else:
    # load the existing index
    logger.info("Loading existing RAG index")
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    index = load_index_from_storage(storage_context)

# Create query engine at module level
query_engine = None

common_instructions = (
    "Your name is Aaple Sarkar. You are a government AI assistant. "
    "Be extremely concise and to the point. Keep all responses brief. "
    "Avoid unnecessary greetings or explanations. "
    "Always prioritize brevity - use 1-2 sentences maximum whenever possible. "
    "You have access to a knowledge base of government documents and can provide accurate information about government services."
)


@dataclass
class CitizenData:
    # Shared data about the citizen that's used by the government agent
    name: Optional[str] = None
    district: Optional[str] = None
    query_type: Optional[str] = None


class GreetingAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=f"{common_instructions} "
            "Collect name, district, and query type efficiently. "
            "Use an extremely short greeting (5-10 words). "
            "Example: 'I'm Aaple Sarkar. Your name and district?'",
            # Using OpenAI's GPT-4o-mini model to avoid rate limits
            llm=openai.LLM(
                model="gpt-4o-mini",
                temperature=0.7,
            ),
            # Uncomment to use Groq's Llama model again later
            # llm=openai.LLM(
            #     model="llama3-70b-8192",
            #     temperature=0.7,
            #     api_key=os.environ.get("GROQ_API_KEY"),
            #     base_url="https://api.groq.com/openai/v1",
            # ),
        )

    async def on_enter(self):
        # when the agent is added to the session, it'll generate a reply
        # according to its instructions
        self.session.generate_reply()

    @function_tool
    async def information_collected(
        self,
        context: RunContext[CitizenData],
        name: str,
        district: str,
        query_type: str,
    ):
        """Called when the citizen has provided their basic information needed to assist them.

        Args:
            name: The name of the citizen
            district: The district where the citizen resides
            query_type: The category of the citizen's query
        """

        context.userdata.name = name
        context.userdata.district = district
        context.userdata.query_type = query_type

        service_agent = ServiceAgent(name, district, query_type)
        # by default, ServiceAgent will start with a new context, to carry through the current
        # chat history, pass in the chat_ctx
        # service_agent = ServiceAgent(name, district, query_type, chat_ctx=context.chat_ctx)

        logger.info(
            "switching to the service agent with the provided citizen data: %s", context.userdata
        )
        return service_agent, f"Thanks, {name}. How can I help with your {query_type} query?"


class ServiceAgent(Agent):
    def __init__(self, name: str, district: str, query_type: str, *, chat_ctx: Optional[ChatContext] = None) -> None:
        super().__init__(
            instructions=f"{common_instructions} "
            "Provide direct, concise answers. "
            "Skip pleasantries and unnecessary details. "
            "Use short, simple language. "
            f"User: {name}, district: {district}, query: {query_type}. "
            "Give only the exact information requested - nothing more.",
            # Using OpenAI's GPT-4o-mini model to avoid rate limits
            llm=openai.LLM(
                model="gpt-4o-mini",
                temperature=0.7,
            ),
            # Uncomment to use Groq's Llama model again later
            # llm=openai.LLM(
            #     model="llama3-70b-8192",
            #     temperature=0.7,
            #     api_key=os.environ.get("GROQ_API_KEY"),
            #     base_url="https://api.groq.com/openai/v1",
            # ),
            tts=None,
            chat_ctx=chat_ctx,
        )

    async def on_enter(self):
        # when the agent is added to the session, we'll initiate the conversation by
        # using the LLM to generate a reply
        self.session.generate_reply()

    @function_tool
    async def query_info(self, context: RunContext[CitizenData], query: str) -> str:
        """Get specific information from government knowledge base.

        Args:
            query: The specific question to search for in government documents
        """
        global query_engine
        if query_engine is None:
            query_engine = index.as_query_engine(use_async=True)
        
        logger.info(f"RAG query: {query}")
        res = await query_engine.aquery(query)
        logger.info(f"RAG result: {res}")
        
        # Return the answer
        return str(res)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    # Initialize and store query engine
    global query_engine
    query_engine = index.as_query_engine(use_async=True)


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    
    session = AgentSession[CitizenData](
        vad=ctx.proc.userdata["vad"],
        # Using OpenAI's GPT-4o-mini model to avoid rate limits
        llm=openai.LLM(
            model="gpt-4o-mini",
            temperature=0.7,
        ),
        # Uncomment to use Groq's Llama model again later
        # llm=openai.LLM(
        #     model="llama3-70b-8192",
        #     temperature=0.7,
        #     api_key=os.environ.get("GROQ_API_KEY"),
        #     base_url="https://api.groq.com/openai/v1",
        # ),
        stt=deepgram.STT(model="nova-2-general"),
        # Use standard TTS
        tts=elevenlabs.TTS(
            model="eleven_monolingual_v1",
            api_key=os.environ.get("ELEVEN_API_KEY"),
            voice_id="21m00Tcm4TlvDq8ikWAM"  # Default voice (Rachel)
        ),
        userdata=CitizenData(),
    )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=GreetingAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # uncomment to enable Krisp BVC noise cancellation
            # noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )


# if __name__ == "__main__":
#     cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))



if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint, 
        prewarm_fnc=prewarm
    ))