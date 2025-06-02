import os
import shutil
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.schema import Document

logger = logging.getLogger("document-upload")

# Base directory for all user data
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))

class DocumentUploadResponse(BaseModel):
    """Response model for document uploads"""
    status: str
    message: str
    document_count: int
    index_id: Optional[str] = None

class UserConfig(BaseModel):
    """User agent configuration"""
    system_prompt: str
    voice: str = "alloy"
    model: str = "gpt-4o-mini"
    
    # Additional parameters can be added here as needed
    agent_name: Optional[str] = None
    language: str = "en"

app = FastAPI(title="Voice Agent Document Upload API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_user_storage_paths(user_id: str) -> Dict[str, Path]:
    """Get all storage paths for a specific user"""
    user_dir = BASE_STORAGE_DIR / user_id
    
    return {
        "base": user_dir,
        "uploads": user_dir / "uploads",
        "temp": user_dir / "temp",
        "index": user_dir / "knowledge-storage",
        "config": user_dir / "config"
    }

def ensure_user_directories(user_id: str) -> Dict[str, Path]:
    """Ensure all required directories exist for the user"""
    paths = get_user_storage_paths(user_id)
    
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
        
    return paths

async def save_uploaded_file(upload_file: UploadFile, destination: Path) -> Path:
    """Save an uploaded file to the specified destination"""
    file_path = destination / upload_file.filename
    
    # Write file contents
    with open(file_path, "wb") as f:
        contents = await upload_file.read()
        f.write(contents)
    
    return file_path

async def process_documents(
    user_id: str,
    files: List[UploadFile],
    collection_name: Optional[str] = None
) -> DocumentUploadResponse:
    """Process uploaded documents and create a vector index"""
    paths = ensure_user_directories(user_id)
    
    # Clear temp directory
    if os.path.exists(paths["temp"]):
        shutil.rmtree(paths["temp"])
    os.makedirs(paths["temp"], exist_ok=True)
    
    # Save uploaded files to temp directory
    saved_files = []
    for file in files:
        try:
            file_path = await save_uploaded_file(file, paths["temp"])
            saved_files.append(file_path)
            
            # Also save to persistent uploads folder
            await save_uploaded_file(file, paths["uploads"])
        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing file {file.filename}")
    
    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid files were uploaded")
    
    try:
        # Load documents from files
        documents = SimpleDirectoryReader(paths["temp"]).load_data()
        
        # Create a custom index directory if collection name is provided
        index_dir = paths["index"]
        if collection_name:
            index_dir = index_dir / collection_name
            os.makedirs(index_dir, exist_ok=True)
        
        # Create and save the vector index
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist(persist_dir=index_dir)
        
        return DocumentUploadResponse(
            status="success",
            message=f"Successfully processed {len(documents)} documents",
            document_count=len(documents),
            index_id=str(index_dir)
        )
    except Exception as e:
        logger.error(f"Error creating index for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}")

@app.post("/upload/{user_id}", response_model=DocumentUploadResponse)
async def upload_documents(
    user_id: str,
    files: List[UploadFile] = File(...),
    collection_name: Optional[str] = Form(None)
):
    """
    Upload documents for a specific user and create a vector index
    
    - **user_id**: Unique identifier for the user
    - **files**: List of files to upload (PDF, TXT, MD, DOCX, etc.)
    - **collection_name**: Optional name for this document collection
    """
    return await process_documents(user_id, files, collection_name)

@app.post("/config/{user_id}")
async def save_user_config(user_id: str, config: UserConfig):
    """
    Save configuration for a user's agent
    
    - **user_id**: Unique identifier for the user
    - **config**: Agent configuration parameters
    """
    paths = ensure_user_directories(user_id)
    
    try:
        # Save config to JSON file
        config_file = paths["config"] / "agent_config.json"
        with open(config_file, "w") as f:
            f.write(config.model_dump_json(indent=2))
        
        return {"status": "success", "message": "Configuration saved successfully"}
    except Exception as e:
        logger.error(f"Error saving config for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")

@app.get("/collections/{user_id}")
async def list_collections(user_id: str):
    """
    List all document collections for a user
    
    - **user_id**: Unique identifier for the user
    """
    paths = get_user_storage_paths(user_id)
    
    if not os.path.exists(paths["index"]):
        return {"collections": []}
    
    # Get all subdirectories in the index directory
    collections = []
    try:
        index_dir = paths["index"]
        # Check if default index exists
        if os.path.exists(index_dir / "docstore.json"):
            collections.append({
                "name": "default",
                "path": str(index_dir),
                "is_default": True
            })
        
        # Add any named collections
        for item in os.listdir(index_dir):
            item_path = index_dir / item
            if item_path.is_dir() and os.path.exists(item_path / "docstore.json"):
                collections.append({
                    "name": item,
                    "path": str(item_path),
                    "is_default": False
                })
                
        return {"collections": collections}
    except Exception as e:
        logger.error(f"Error listing collections for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing collections: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting document upload API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port) 