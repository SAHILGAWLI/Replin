# AI Voice Agent Service

This is a system for creating user-configurable AI voice agents that can make outbound calls or receive inbound calls using documents uploaded by the end user.

## Features

- Upload custom documents to create a knowledge base
- Configure agent personality, voice, and behavior
- Make outbound calls with AI agents powered by user's knowledge
- Process inbound calls with the same agents
- Support for multiple document collections per user

## Setup

### Prerequisites

- Python 3.9+
- LlamaIndex and OpenAI modules
- LiveKit account for voice call integration

### Installation

1. Install required packages:

```bash
pip install -r requirements.txt
```

2. Set up environment variables (create a `.env` file):

```
OPENAI_API_KEY=your_openai_api_key
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
SIP_TRUNK_ID=your_sip_trunk_id
```

## Usage

### 1. Start the Document Upload API

```bash
uvicorn document_upload:app --host 0.0.0.0 --port 8000
```

### 2. Upload Documents

Use the provided client to upload documents:

```bash
python test_document_upload.py --user user123 upload path/to/document1.pdf path/to/document2.txt
```

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

```bash
# Start document upload API
.\env\Scripts\activate 

uvicorn document_upload:app --host 0.0.0.0 --port 8000

cd C:\Users\Administrator\Downloads\loophole-cli_1.0.0-beta.15_windows_64bit\loophole-cli_1.0.0-beta.15_windows_64bit

 .\loophole.exe http 8000

# Start agent manager

.\env\Scripts\activate 

uvicorn agent_manager:app --host 0.0.0.0 --port 8001

cd C:\Users\Administrator\Downloads\loophole-cli_1.0.0-beta.15_windows_64bit\loophole-cli_1.0.0-beta.15_windows_64bit

.\loophole.exe http 8001
```

## API Documentation

- Document Upload API: `/docs` endpoint
- Agent Manager API: `/docs` endpoint 