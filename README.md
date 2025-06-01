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
python user_agent.py --user user123
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