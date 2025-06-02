web: uvicorn WebVoiceAgent:app --host 0.0.0.0 --port $PORT
document_api: uvicorn document_upload:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
web_agent_manager: uvicorn agent_manager:app --host 0.0.0.0 --port $PORT 