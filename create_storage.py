#!/usr/bin/env python3
"""
Storage directory setup script for Render deployment without disk mounts.
This script ensures that the necessary directories exist for user data storage.
"""

import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("storage-setup")

def create_storage_directories():
    """Create the necessary storage directories for the application"""
    # Get storage path from environment or use default
    storage_path = os.environ.get("STORAGE_PATH", "./user_data")
    storage_dir = Path(storage_path)
    
    # Create main storage directory
    os.makedirs(storage_dir, exist_ok=True)
    logger.info(f"Created main storage directory: {storage_dir}")
    
    # Create required subdirectories
    subdirs = [
        "uploads",      # For uploaded files
        "temp",         # For temporary files
        "knowledge-storage",  # For vector indices
        "config"        # For user configurations
    ]
    
    for subdir in subdirs:
        path = storage_dir / subdir
        os.makedirs(path, exist_ok=True)
        logger.info(f"Created subdirectory: {path}")
    
    # Create tracking directory for agent manager
    agent_tracking_dir = Path("agent_tracking")
    os.makedirs(agent_tracking_dir, exist_ok=True)
    logger.info(f"Created agent tracking directory: {agent_tracking_dir}")
    
    # Create a test file to verify storage is working
    test_file = storage_dir / "storage_test.txt"
    try:
        with open(test_file, "w") as f:
            f.write("Storage test - created during startup")
        logger.info(f"Successfully wrote test file: {test_file}")
    except Exception as e:
        logger.error(f"Failed to write test file: {str(e)}")
        raise

    return storage_dir

if __name__ == "__main__":
    logger.info("Starting storage directory setup...")
    try:
        storage_dir = create_storage_directories()
        logger.info(f"Storage directory setup complete at: {storage_dir}")
    except Exception as e:
        logger.error(f"Storage directory setup failed: {str(e)}")
        raise 