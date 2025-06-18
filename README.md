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

<<<<<<< HEAD
Optionally, you can specify a collection name:

```bash
python test_document_upload.py --user user123 upload --collection finance path/to/finance_docs.pdf
```

### 3. Configure the Agent

```bash
python test_document_upload.py --user user123 config --prompt "You are a helpful financial assistant who provides concise information about financial products." --voice nova --name "Finance Assistant"
```

### 4. Start an Agent

For inbound calls:

```bash
python user_agent.py --user 100xEngineers
```

With a specific collection:

```bash
python user_agent.py --user user123 --collection finance
```

For outbound calls:

```bash
python user_agent.py --user user123 --phone +1234567890
```

## API Endpoints

### Document Upload API

- `POST /upload/{user_id}` - Upload documents
- `POST /config/{user_id}` - Save agent configuration
- `GET /collections/{user_id}` - List document collections
 .\venv\Scripts\activate
## Architecture

The system consists of these main components:

1. **Document Upload Service** - Handles document ingestion and indexing
2. **Agent Configuration** - Manages user-specific agent settings
3. **Voice Agent** - Uses LiveKit for real-time communication
4. **RAG Engine** - Retrieval-augmented generation using LlamaIndex

## Security Considerations

- All user data is stored in isolated directories
- Credentials should be properly secured in production
- Add authentication to the API endpoints in a production deployment

## Customization

You can customize the system by:

- Adding more agent configurations
- Supporting different document types
- Implementing more complex RAG strategies
- Adding analytics and monitoring
- Creating a web UI for easier management

## License

MIT

## Deployment to Render

### Prerequisites

1. A [Render](https://render.com/) account
2. OpenAI API key
3. LiveKit credentials (if using voice features)

### Deployment Steps

1. **Fork or clone this repository to your GitHub account**

2. **Log in to Render**
   - Go to https://dashboard.render.com/
   - Sign in or create an account

3. **Deploy using the render.yaml blueprint**
   - Click "New" > "Blueprint"
   - Connect your GitHub repository
   - Follow the prompts to deploy all services

4. **Alternative: Manual Deployment**

   If you prefer to deploy manually:

   a. **Deploy Document Upload API**
      - Click "New" > "Web Service"
      - Connect your GitHub repository
      - Configure as follows:
        - Name: `document-upload-api`
        - Environment: Python
        - Build Command: `pip install -r requirements.txt`
        - Start Command: `uvicorn document_upload:app --host 0.0.0.0 --port $PORT`
      - Add environment variables:
        - `OPENAI_API_KEY`: Your OpenAI API key
        - `STORAGE_PATH`: `/data/user_data`
      - Add a disk:
        - Name: `user-data`
        - Mount Path: `/data`
        - Size: 10 GB

   b. **Deploy Agent Manager**
      - Click "New" > "Web Service"
      - Connect your GitHub repository
      - Configure as follows:
        - Name: `agent-manager`
        - Environment: Python
        - Build Command: `pip install -r requirements.txt`
        - Start Command: `uvicorn agent_manager:app --host 0.0.0.0 --port $PORT`
      - Add environment variables:
        - `STORAGE_PATH`: `/data/user_data`
        - `LIVEKIT_URL`: Your LiveKit URL
        - `LIVEKIT_API_KEY`: Your LiveKit API key
        - `LIVEKIT_API_SECRET`: Your LiveKit API secret
        - `SIP_TRUNK_ID`: Your SIP trunk ID (if using outbound calling)
      - Add a disk:
        - Name: `user-data`
        - Mount Path: `/data`
        - Size: 10 GB

5. **Verify Deployment**
   - Test document uploads at `https://document-upload-api.onrender.com/docs`
   - Test agent management at `https://agent-manager.onrender.com/docs`

## Local Development

To run the application locally:
=======
### Local Development
>>>>>>> 7f5633a9e220c1ca483f9a559c5e3b5f25cc9159

```bash
# Start document upload API
.\env\Scripts\activate 

uvicorn document_upload:app --host 0.0.0.0 --port 8000

<<<<<<< HEAD
cd C:\Users\Administrator\Downloads\loophole-cli_1.0.0-beta.15_windows_64bit\loophole-cli_1.0.0-beta.15_windows_64bit

 .\loophole.exe http 8000

# Start agent manager

.\env\Scripts\activate 

uvicorn agent_manager:app --host 0.0.0.0 --port 8001

cd C:\Users\Administrator\Downloads\loophole-cli_1.0.0-beta.15_windows_64bit\loophole-cli_1.0.0-beta.15_windows_64bit

.\loophole.exe http 8001
=======
# Start agent manager 
uvicorn agent_manager:app --host 0.0.0.0 --port 8001

# Test document uploads
python test_document_upload.py --user <user_id> upload <files>

# Start a voice agent
python web-agent-run.py --user <user_id> --collection <collection_name>
>>>>>>> 7f5633a9e220c1ca483f9a559c5e3b5f25cc9159
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

