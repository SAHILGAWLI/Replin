import os
import shutil
import logging
import asyncio
import json
import tempfile
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

# Import GCS storage handler
from gcs_storage import get_gcs_handler, GCSStorageHandler

logger = logging.getLogger("document-upload")

# Base directory for all user data (for local fallback)
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))

# Check if GCS is enabled
USE_GCS = os.environ.get("USE_GCS", "false").lower() == "true"

# Initialize GCS handler if enabled
gcs_handler = None
if USE_GCS:
    try:
        gcs_handler = get_gcs_handler()
        logger.info("Google Cloud Storage initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Google Cloud Storage: {str(e)}")
        logger.warning("Falling back to local storage")

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
    
    # For GCS, we create directories in the cloud
    if USE_GCS and gcs_handler:
        try:
            # Create directory structure in GCS
            gcs_handler.create_directory(user_id, "uploads")
            gcs_handler.create_directory(user_id, "temp")
            gcs_handler.create_directory(user_id, "knowledge-storage")
            gcs_handler.create_directory(user_id, "config")
            logger.info(f"Created GCS directories for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to create GCS directories for user {user_id}: {str(e)}")
    
    # Always create local directories as well (needed for temp processing)
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    
    logger.info(f"Created local directories for user {user_id}")
    return paths

async def save_uploaded_file(upload_file: UploadFile, user_id: str, folder: str) -> str:
    """Save an uploaded file using the appropriate storage method"""
    file_name = upload_file.filename
    
    # Read file contents
    contents = await upload_file.read()
    
    if USE_GCS and gcs_handler:
        try:
            # Upload to GCS
            from io import BytesIO
            file_io = BytesIO(contents)
            gcs_path = gcs_handler.upload_file(
                user_id=user_id,
                file_path=f"{folder}/{file_name}",
                file_content=file_io,
                content_type=upload_file.content_type
            )
            logger.info(f"Saved file {file_name} to GCS: {gcs_path}")
            return gcs_path
        except Exception as e:
            logger.error(f"Error saving file to GCS: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error saving file to GCS: {str(e)}")
    else:
        # Save locally
        paths = get_user_storage_paths(user_id)
        destination_folder = paths[folder] if folder in paths else paths["base"] / folder
        os.makedirs(destination_folder, exist_ok=True)
        
        file_path = destination_folder / file_name
        with open(file_path, "wb") as f:
            f.write(contents)
        
        logger.info(f"Saved file {file_name} locally to {file_path}")
        return str(file_path)

async def prepare_temp_directory(user_id: str, files: List[str]) -> Path:
    """
    Prepare a temporary directory with all files for processing.
    If using GCS, download files to a local temp directory.
    """
    paths = get_user_storage_paths(user_id)
    temp_dir = paths["temp"]
    
    # Clear temp directory
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    # If using GCS, download files to temp dir
    if USE_GCS and gcs_handler and files:
        for file_path in files:
            try:
                file_name = os.path.basename(file_path)
                local_path = temp_dir / file_name
                gcs_handler.download_file(file_path, str(local_path))
                logger.info(f"Downloaded file from GCS: {file_path} to {local_path}")
            except Exception as e:
                logger.error(f"Error downloading file from GCS: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error preparing files: {str(e)}")
    
    return temp_dir

async def save_index_to_storage(user_id: str, index: VectorStoreIndex, collection_name: Optional[str] = None) -> str:
    """
    Save the index to storage (local or GCS).
    For GCS, we save locally first, then upload to GCS.
    """
    paths = get_user_storage_paths(user_id)
    
    # Determine index directory
    index_dir = paths["index"]
    if collection_name:
        index_dir = index_dir / collection_name
    
    os.makedirs(index_dir, exist_ok=True)
    
    # Save the index locally first
    index.storage_context.persist(persist_dir=index_dir)
    logger.info(f"Saved index locally to {index_dir}")
    
    # If using GCS, upload the index files
    if USE_GCS and gcs_handler:
        try:
            # Path in GCS where index will be stored
            gcs_base_path = f"knowledge-storage"
            if collection_name:
                gcs_base_path = f"{gcs_base_path}/{collection_name}"
                
            # Upload all files in the index directory
            for file_name in os.listdir(index_dir):
                file_path = index_dir / file_name
                if os.path.isfile(file_path):
                    with open(file_path, "rb") as f:
                        from io import BytesIO
                        file_io = BytesIO(f.read())
                        gcs_path = gcs_handler.upload_file(
                            user_id=user_id,
                            file_path=f"{gcs_base_path}/{file_name}",
                            file_content=file_io
                        )
                        logger.info(f"Uploaded index file to GCS: {gcs_path}")
            
            logger.info(f"Saved index to GCS for user {user_id}, collection {collection_name or 'default'}")
            return f"gcs://{user_id}/{gcs_base_path}"
        except Exception as e:
            logger.error(f"Error saving index to GCS: {str(e)}")
            # Return local path as fallback
            return str(index_dir)
    
    return str(index_dir)

async def process_documents(
    user_id: str,
    files: List[UploadFile],
    collection_name: Optional[str] = None
) -> DocumentUploadResponse:
    """Process uploaded documents and create a vector index"""
    # Ensure user directories exist
    ensure_user_directories(user_id)
    
    # Save uploaded files
    saved_files = []
    for file in files:
        try:
            # Save to temp folder
            temp_file_path = await save_uploaded_file(file, user_id, "temp")
            saved_files.append(temp_file_path)
            
            # Also save to persistent uploads folder
            await save_uploaded_file(file, user_id, "uploads")
        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing file {file.filename}")
    
    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid files were uploaded")
    
    try:
        # Prepare a temporary directory with all files
        temp_dir = await prepare_temp_directory(user_id, saved_files)
        
        # Load documents from files
        documents = SimpleDirectoryReader(temp_dir).load_data()
        
        # Create and save the vector index
        index = VectorStoreIndex.from_documents(documents)
        index_id = await save_index_to_storage(user_id, index, collection_name)
        
        return DocumentUploadResponse(
            status="success",
            message=f"Successfully processed {len(documents)} documents",
            document_count=len(documents),
            index_id=index_id
        )
    except Exception as e:
        logger.error(f"Error creating index for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}")

async def save_user_config_to_storage(user_id: str, config: Dict) -> str:
    """Save user configuration to storage (local or GCS)"""
    paths = get_user_storage_paths(user_id)
    config_dir = paths["config"]
    os.makedirs(config_dir, exist_ok=True)
    
    # Always save locally first
    config_file = config_dir / "agent_config.json"
    with open(config_file, "w") as f:
        f.write(json.dumps(config, indent=2))
    
    logger.info(f"Saved config locally to {config_file}")
    
    # If using GCS, upload the config file
    if USE_GCS and gcs_handler:
        try:
            with open(config_file, "rb") as f:
                from io import BytesIO
                file_io = BytesIO(f.read())
                gcs_path = gcs_handler.upload_file(
                    user_id=user_id,
                    file_path="config/agent_config.json",
                    file_content=file_io,
                    content_type="application/json"
                )
                logger.info(f"Uploaded config to GCS: {gcs_path}")
                return gcs_path
        except Exception as e:
            logger.error(f"Error saving config to GCS: {str(e)}")
            return str(config_file)
            
    return str(config_file)

async def get_collections_from_storage(user_id: str) -> List[Dict]:
    """Get all document collections for a user from storage"""
    collections = []
    
    if USE_GCS and gcs_handler:
        try:
            # Check for default index in GCS
            gcs_base_path = f"users/{user_id}/knowledge-storage"
            
            # List all files and identify collections from prefixes
            blobs = gcs_handler.client.list_blobs(
                gcs_handler.bucket_name, 
                prefix=gcs_base_path,
                delimiter="/"
            )
            
            # Check if default collection exists
            default_exists = False
            for blob in gcs_handler.client.list_blobs(
                gcs_handler.bucket_name, 
                prefix=f"{gcs_base_path}/docstore.json"
            ):
                default_exists = True
                break
            
            if default_exists:
                collections.append({
                    "name": "default",
                    "path": f"gcs://{user_id}/knowledge-storage",
                    "is_default": True
                })
            
            # Add named collections from prefixes
            for prefix in blobs.prefixes:
                # Extract collection name from prefix
                collection_name = prefix.rstrip("/").split("/")[-1]
                
                # Skip if it's somehow the default collection
                if collection_name == "knowledge-storage":
                    continue
                
                # Check if it has docstore.json
                collection_exists = False
                for blob in gcs_handler.client.list_blobs(
                    gcs_handler.bucket_name,
                    prefix=f"{prefix}docstore.json"
                ):
                    collection_exists = True
                    break
                
                if collection_exists:
                    collections.append({
                        "name": collection_name,
                        "path": f"gcs://{user_id}/{prefix}",
                        "is_default": False
                    })
            
            logger.info(f"Found {len(collections)} collections in GCS for user {user_id}")
            
            if collections:
                return collections
                
        except Exception as e:
            logger.error(f"Error getting collections from GCS: {str(e)}")
            logger.warning("Falling back to local storage for collections")
    
    # Fallback to local storage or if GCS has no collections
    paths = get_user_storage_paths(user_id)
    index_dir = paths["index"]
    
    if not os.path.exists(index_dir):
        return collections
    
    try:
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
    except Exception as e:
        logger.error(f"Error listing local collections for user {user_id}: {str(e)}")
    
    logger.info(f"Found {len(collections)} collections locally for user {user_id}")
    return collections

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
    # Ensure user directories exist
    ensure_user_directories(user_id)
    
    try:
        # Save config
        config_path = await save_user_config_to_storage(user_id, config.model_dump())
        
        return {"status": "success", "message": "Configuration saved successfully", "path": config_path}
    except Exception as e:
        logger.error(f"Error saving config for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")

@app.get("/collections/{user_id}")
async def list_collections(user_id: str):
    """
    List all document collections for a user
    
    - **user_id**: Unique identifier for the user
    """
    collections = await get_collections_from_storage(user_id)
    return {"collections": collections}

@app.get("/storage-status")
async def storage_status():
    """Get storage status information"""
    status = {
        "storage_type": "Google Cloud Storage" if USE_GCS and gcs_handler else "Local Storage",
        "base_path": str(BASE_STORAGE_DIR),
        "gcs_enabled": USE_GCS and gcs_handler is not None
    }
    
    if USE_GCS and gcs_handler:
        status["gcs_bucket"] = gcs_handler.bucket_name
    
    return status

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting document upload API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port) 