# 🌀 Replin AI – AI Voice Agent as a Service

## 🚀 What It Does

**Replin AI** enables anyone to spin up their own AI voice agent in seconds. Upload a knowledge base, define how the agent should behave with a simple system prompt, choose inbound or outbound mode, pick a voice, and hit start. The agent can then handle natural, real-time phone or web conversations—no code, no friction.

Currently supports English, with support for Indian languages and multilingual workflows coming soon.

## 💰 Business Model

**Replin AI** runs on a **credit-based pricing system** designed for simplicity and accessibility:

* Users **buy credits** to use the AI agent.
* **Credits are consumed** based on two factors:

  1. 📚 **Size of the uploaded knowledge base** (the bigger the knowledge, the more credits used)
  2. 🕒 **Duration of agent activity** (longer active sessions use more credits)

Once credits run out, users can easily top up and continue. There's **no setup fee**, **no technical overhead**, and **no dependency on support teams**—anyone can launch and run their own voice agent independently, within minutes.

## 🧪 Testing Options

You can interact with your **Replin AI** voice agent in two ways:

* **Web Interface (Recommended for Testing)**:
  No setup needed—just use the browser UI to interact with the agent.

* **Phone Call Mode** *(Requires International Plan)*:
  Users with international recharge on their phone can call a US-based number to interact with a live agent.
  *(We're actively switching to Indian SIP trunk providers soon to make phone access locally available and frictionless.)*

## 🧱 Challenges Overcome

* Transitioned from hardcoded voice agents to a **dynamic configuration-based pipeline**
* Built a system that launches and manages agent processes with full **process tracking and cleanup**
* Overcame **multi-server orchestration hurdles**—FastAPI for config + Flask for runtime
* Managed **secure comms** across localhost servers using proxy tunnels and HTTPS adapters
* Designed for **multi-user concurrency** and safe teardown

## 🔥 Technical Highlights

- **Advanced RAG Implementation**: Leverages LlamaIndex for efficient vector indexing and retrieval with dynamic context handling
- **Real-time Voice Communication**: Integrates LiveKit WebRTC infrastructure for high-quality, low-latency audio streaming
- **Multi-agent Architecture**: Dynamically spawns and manages isolated agent instances with dedicated resources
- **Secure Document Processing Pipeline**: Handles document ingestion, chunking, embedding, and vector storage with proper isolation
- **Scalable Microservices Design**: Separate document processing API, agent manager, and voice agent services
- **Voice Optimization**: Specialized formatting and character filtering to enhance TTS quality and prevent artifacts

## 🛠️ How It Works

The architecture behind **Replin AI** blends best-in-class tools to deliver a seamless voice AI pipeline:

* **Language Understanding**: OpenAI GPT-4o-mini
* **Text-to-Speech**: Eleven Labs
* **Speech-to-Text**: Deepgram / DPM
* **Real-time Audio Routing**: LiveKit (open-source WebRTC)
* **Backend Infra**:
  * FastAPI for user configuration
  * Flask for running agent processes
  * Orchestrated on AWS EC2 with dynamic process tracking
  * Local proxy + tunneling to handle HTTPS and secure socket handshakes

Every agent instance is spun up with its own configuration and lives until the user shuts it down. It's isolated, scalable, and behaves exactly as instructed.

## 📚 Technical Architecture

The system consists of four main technical components:

1. **Document Processing Engine** (`document_upload.py`)
   - FastAPI-based document ingestion API with CORS middleware
   - Asynchronous multi-document processing with proper error handling
   - Intelligent document splitting and vector indexing via LlamaIndex
   - Collection-based knowledge management for domain-specific agents

2. **Agent Management System** (`agent_manager.py`)
   - Process orchestration with cross-platform compatibility (Windows/Linux)
   - Process isolation and resource management with proper cleanup mechanisms
   - Port allocation and management for multi-agent deployment
   - Health monitoring and stale instance detection

3. **Voice Agent Core** (`user_agent.py`, `web-user.py`)
   - WebRTC-based real-time communication via LiveKit
   - Voice activity detection (VAD) for natural conversation flow
   - Speech-to-text conversion using Deepgram with enhanced accuracy
   - LLM context management with OpenAI integration
   - Text-to-speech optimization with Cartesia TTS

4. **Runner Infrastructure** (`run_agent.py`, `web-agent-run.py`)
   - Environment configuration and validation
   - Command-line interface for agent deployment
   - Argument parsing and environment variable management

## 🔧 Technical Implementation Details

### Advanced RAG Architecture

```
User Query → STT → LLM Context Window → Document Retrieval → Vector Search → Response Generation → TTS
```

- Implements asynchronous query pipeline for responsive user interactions
- Special character filtering to prevent TTS artifacts
- Robust error handling throughout the RAG pipeline

### LiveKit Integration

- Room-based participant management
- SIP trunk integration for PSTN calling
- Bidirectional audio streaming with WebRTC
- Real-time transcription display

### Data Isolation & Security

- Per-user storage directories with proper access controls
- Collection-based knowledge separation for domain-specific agents
- Configuration management with sensible defaults
- Environment variable protection for sensitive credentials

## 💻 Setup and Deployment

### Local Development

```bash
# Start document upload API
uvicorn document_upload:app --host 0.0.0.0 --port 8000

# Start agent manager 
uvicorn agent_manager:app --host 0.0.0.0 --port 8001

# Test document uploads
python test_document_upload.py --user <user_id> upload <files>

# Start a voice agent
python web-agent-run.py --user <user_id> --collection <collection_name>
```

## 🚀 Technical Innovations

1. **Cross-Platform Agent Management**: Dynamically manages agent processes across Windows and Linux environments
2. **Outbound Calling Integration**: SIP trunk integration for proactive outbound customer engagement
3. **Adaptive Document Processing**: Adjusts to different document formats and content structures
4. **Character Filtering Pipeline**: Prevents TTS issues by removing markdown and special characters
5. **Real-time Metrics Collection**: Tracks usage and performance metrics for optimization

## 📋 API Reference

### Document Upload API

- `POST /upload/{user_id}`: Upload documents with optional collection name
- `POST /config/{user_id}`: Configure agent parameters (system prompt, voice, model)
- `GET /collections/{user_id}`: List all document collections

### Agent Manager API

- `POST /start-agent`: Launch a new agent with specific configuration
- `POST /stop-agent/{user_id}`: Terminate a running agent
- `GET /agents`: List all currently active agents

## 🔒 Security Features

- **CORS Protection**: Configurable origin restrictions
- **Process Isolation**: Each user's agent runs in an isolated environment
- **Path Traversal Prevention**: Safe path handling to prevent directory traversal
- **Error Handling**: Robust error handling to prevent information leakage

## 🌍 Why It Matters

Startups, solopreneurs, and lean teams often struggle with scaling human conversations. Voice AI is powerful—but today it's complex to deploy. Replin AI flips that:

> "If you can type instructions and upload a doc, you can deploy a voice agent."

That's how we democratize intelligent automation. No engineers needed. No call center required. Just your content, and an agent that speaks for you.

## 📈 Vision and Roadmap

* 🔄 **Outbound Calling** — closing the communication loop
* 🛠️ **More Agent Controls** — customize tone, memory, escalation flow, fallback behavior
* 🧠 **AI Function Calling** — enable agents to take smart actions, trigger APIs, and complete tasks
* 🇮🇳 **India SIP Integration** — unlock true local access and reduce calling barriers
* 👥 **Multi-Agent Swarms** — imagine a sales agent talking, a manager agent supervising, and a human stepping in only when needed
* 📊 **Analytics Dashboard** — track performance, call stats, and agent effectiveness

We're building a future where **you don't scale with people—you scale with intelligent agents.**

## 📹 Demo
Click the image below to watch the demo:

[![Watch the demo](https://img.youtube.com/vi/UHVppAMUBAg/0.jpg)](https://www.youtube.com/watch?v=UHVppAMUBAg)

