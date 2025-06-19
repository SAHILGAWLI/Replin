import os
import shutil
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

os.environ["OPENAI_API_KEY"] = "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"



from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # Import Field for more control if needed

from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
# from llama_index.core.schema import Document # Not directly used in this snippet

logger = logging.getLogger("document-upload")
logging.basicConfig(level=logging.INFO) # Added basicConfig for logger to show output

# Base directory for all user data
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))

class DocumentUploadResponse(BaseModel):
    """Response model for document uploads"""
    status: str
    message: str
    document_count: int
    index_id: Optional[str] = None

# --- MODIFIED UserConfig Pydantic Model ---
class UserConfig(BaseModel):
    """User agent configuration, now including secrets/environment settings"""
    system_prompt: str
    voice: str = "alloy"
    model: str = "gpt-4o-mini"
    agent_name: Optional[str] = None
    language: str = "en"

    # NEW: Fields for API keys and LiveKit details
    # Using Optional[str] = None allows these to be absent initially
    # or if the user hasn't configured them yet.
    # Consider adding `Field(default=None, validate_default=False)` if you want to be explicit
    # about them not being required for model validation if not provided.
    openai_api_key: Optional[str] = None
    deepgram_api_key: Optional[str] = None
    cartesia_api_key: Optional[str] = None # If using Cartesia

    livekit_url: Optional[str] = None
    livekit_api_key: Optional[str] = None
    livekit_api_secret: Optional[str] = None
    sip_trunk_id: Optional[str] = None

    # You can add other specific settings the agent might need from the user
    # For example, if the collection_name or phone_number should be part of this master config:
    # collection_name_preference: Optional[str] = None
    # default_phone_number_to_dial: Optional[str] = None


app = FastAPI(title="Voice Agent Document and Config API") # Renamed for clarity

# Define allowed origins
allowed_origins = [
    "https://replin.vercel.app",
    "http://localhost:3000", # Common for local Next.js dev
    "http://localhost:5173", # Common for local Vite/React dev
    # Add your specific loophole URLs if they are static, or keep "*" for broader dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development. Restrict in production.
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
    for path_key in paths: # Iterate through keys to ensure all are created
        os.makedirs(paths[path_key], exist_ok=True)
    return paths

async def save_uploaded_file(upload_file: UploadFile, destination: Path) -> Path:
    """Save an uploaded file to the specified destination"""
    # Ensure destination directory exists (though ensure_user_directories should handle the parent)
    os.makedirs(destination, exist_ok=True)
    file_path = destination / upload_file.filename

    try:
        with open(file_path, "wb") as f:
            contents = await upload_file.read()
            f.write(contents)
    finally:
        await upload_file.close() # Ensure file is closed
    return file_path

async def process_documents(
    user_id: str,
    files: List[UploadFile],
    collection_name: Optional[str] = None
) -> DocumentUploadResponse:
    """Process uploaded documents and create a vector index"""
    paths = ensure_user_directories(user_id)

    temp_dir_for_processing = paths["temp"] / "current_upload" # Use a sub-folder
    if os.path.exists(temp_dir_for_processing):
        shutil.rmtree(temp_dir_for_processing)
    os.makedirs(temp_dir_for_processing, exist_ok=True)

    saved_files_info = []
    for file in files:
        if not file.filename: # Handle case where filename might be empty
            logger.warning("Uploaded file with no filename, skipping.")
            continue
        try:
            # Save to temp for processing
            temp_file_path = await save_uploaded_file(file, temp_dir_for_processing)
            saved_files_info.append({"path": temp_file_path, "name": file.filename})

            # Also save to persistent uploads folder (optional, if you want to keep raw uploads)
            # persistent_uploads_path = paths["uploads"]
            # if collection_name: # Optionally organize persistent uploads by collection
            #     persistent_uploads_path = persistent_uploads_path / collection_name
            # await save_uploaded_file(file, persistent_uploads_path) # File is already read, need to re-open or pass content

        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {str(e)}")
            # Consider if one failed file should stop the whole batch
            raise HTTPException(status_code=500, detail=f"Error processing file {file.filename}: {str(e)}")

    if not saved_files_info:
        raise HTTPException(status_code=400, detail="No valid files were processed")

    try:
        # Load documents from the temp processing directory
        documents = SimpleDirectoryReader(str(temp_dir_for_processing)).load_data()
        if not documents:
            logger.info(f"No documents were extracted from uploaded files for user {user_id}.")
            # Depending on requirements, this might be an error or just an info message
            # For now, let's assume it's okay to have no documents from some uploads.

        index_dir = paths["index"]
        if collection_name:
            index_dir = index_dir / collection_name
        os.makedirs(index_dir, exist_ok=True) # Ensure specific collection index dir exists

        # Create or update the vector index
        # If index_dir already has an index, VectorStoreIndex might load and update it,
        # or you might need to handle merging explicitly depending on LlamaIndex version/backend.
        # For simplicity, this example overwrites/creates new.
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist(persist_dir=str(index_dir))

        # Clean up temp processing directory
        shutil.rmtree(temp_dir_for_processing)

        return DocumentUploadResponse(
            status="success",
            message=f"Successfully processed {len(documents)} documents into collection '{collection_name or 'default'}'",
            document_count=len(documents),
            index_id=str(index_dir)
        )
    except Exception as e:
        logger.error(f"Error creating index for user {user_id}: {str(e)}", exc_info=True)
        # Clean up temp processing directory on error too
        if os.path.exists(temp_dir_for_processing):
            shutil.rmtree(temp_dir_for_processing)
        raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}")

@app.post("/upload/{user_id}", response_model=DocumentUploadResponse)
async def upload_documents_endpoint( # Renamed for clarity from function name `upload_documents`
    user_id: str,
    files: List[UploadFile] = File(...),
    collection_name: Optional[str] = Form(None)
):
    """
    Upload documents for a specific user and create/update a vector index.
    - **user_id**: Unique identifier for the user.
    - **files**: List of files to upload.
    - **collection_name**: Optional name for this document collection (becomes a sub-directory in knowledge-storage).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")
    return await process_documents(user_id, files, collection_name)

# --- save_user_config Endpoint ---
# This endpoint now handles the extended UserConfig model.
# The frontend will send the complete UserConfig object, including any API keys.
@app.post("/config/{user_id}")
async def save_user_config(user_id: str, config_data: UserConfig): # config_data is the full model
    """
    Save or update configuration for a user's agent, including API keys and operational settings.
    - **user_id**: Unique identifier for the user.
    - **config_data**: Agent configuration parameters including secrets.
    """
    paths = ensure_user_directories(user_id)
    config_file = paths["config"] / "agent_config.json"

    try:
        # If the file already exists, you might want to load it and merge,
        # or simply overwrite as done here. Overwriting is simpler if the frontend
        # always sends the complete desired state of the config.
        # existing_config = {}
        # if config_file.exists():
        #     with open(config_file, "r") as f:
        #         existing_config = json.load(f)
        # # Merge logic: update existing_config with fields from config_data.model_dump()
        # # For simplicity, we'll just overwrite.

        with open(config_file, "w") as f:
            # Use model_dump_json for Pydantic v2. For v1, it was config_data.json()
            # exclude_none=True can be useful if you don't want to write null optional fields
            f.write(config_data.model_dump_json(indent=2, exclude_none=True))

        logger.info(f"Configuration saved for user {user_id} to {config_file}")
        return {"status": "success", "message": "Configuration saved successfully."}
    except Exception as e:
        logger.error(f"Error saving config for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")

# --- NEW: Endpoint to GET current user configuration ---
@app.get("/config/{user_id}", response_model=UserConfig)
async def get_user_config(user_id: str):
    """
    Retrieve the current configuration for a user's agent.
    - **user_id**: Unique identifier for the user.
    """
    paths = get_user_storage_paths(user_id) # No need to ensure_user_directories for a GET
    config_file = paths["config"] / "agent_config.json"

    if not config_file.exists():
        # If no config exists, you could return a default UserConfig,
        # or raise a 404. Raising 404 might be cleaner.
        # For now, let's try to return a default if not found, assuming a new user.
        # This requires UserConfig to have defaults for all required fields,
        # or careful handling if some required fields like system_prompt don't have defaults.
        logger.warning(f"Config file not found for user {user_id} at {config_file}. Returning default or empty config.")
        # Create a UserConfig with default values for required fields or expect client to handle.
        # This assumes 'system_prompt' is the only truly required field without a Pydantic default.
        # A better approach for a "new user" might be an explicit /user/init endpoint as in your original plan.
        # For now, let's raise a 404 if the prompt isn't there, as it's a core part.
        raise HTTPException(status_code=404, detail=f"Configuration not found for user {user_id}. Please save a configuration first.")
        # Or, to return a default structure:
        # return UserConfig(system_prompt="Default system prompt - please configure.")


    try:
        with open(config_file, "r") as f:
            config_data = UserConfig.parse_file(config_file) # Pydantic v2 way
            # For Pydantic v1:
            # import json
            # data = json.load(f)
            # config_data = UserConfig(**data)
        return config_data
    except Exception as e:
        logger.error(f"Error loading config for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")


@app.get("/collections/{user_id}")
async def list_collections_endpoint(user_id: str): # Renamed for clarity
    """
    List all document collections (knowledge bases) for a user.
    - **user_id**: Unique identifier for the user.
    """
    paths = get_user_storage_paths(user_id)
    index_base_dir = paths["index"]

    if not os.path.exists(index_base_dir):
        return {"collections": []}

    collections = []
    try:
        # Check if a "default" index exists directly under knowledge-storage
        # A common check for a LlamaIndex persisted index is the presence of 'docstore.json'
        if os.path.exists(index_base_dir / "docstore.json"):
            collections.append({
                "name": "default", # Or derive from path if preferred
                "path": str(index_base_dir),
                "is_default": True # Conceptual marker
            })

        # List subdirectories which might be named collections
        for item_name in os.listdir(index_base_dir):
            item_path = index_base_dir / item_name
            if item_path.is_dir() and os.path.exists(item_path / "docstore.json"):
                # Avoid re-adding "default" if knowledge-storage itself was the default
                # This logic might need refinement based on how you structure "default"
                is_default_collection_path = (str(item_path) == str(index_base_dir))
                if not (is_default_collection_path and any(c['name'] == 'default' for c in collections)):
                    collections.append({
                        "name": item_name,
                        "path": str(item_path),
                        "is_default": False
                    })
        return {"collections": collections}
    except Exception as e:
        logger.error(f"Error listing collections for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing collections: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Document and Config API on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)