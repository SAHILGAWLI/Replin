#!/usr/bin/env python3
"""
Google Cloud Storage handler for Replin application.
This module provides functionality to interact with GCS for document storage.
"""

import os
import json
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, BinaryIO, Union
from io import BytesIO

from google.cloud import storage
from google.oauth2 import service_account

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gcs-storage")

class GCSStorageHandler:
    """
    Handler for Google Cloud Storage operations.
    Manages file uploads, downloads, and directory operations.
    """
    
    def __init__(self, bucket_name: str, credentials: Optional[service_account.Credentials] = None):
        """
        Initialize GCS storage handler
        
        Args:
            bucket_name: The name of the GCS bucket
            credentials: Optional service account credentials
        """
        self.bucket_name = bucket_name
        
        if credentials:
            self.client = storage.Client(credentials=credentials)
        else:
            # Use default credentials from environment
            self.client = storage.Client()
            
        # Check if bucket exists, create if not
        try:
            self.bucket = self.client.get_bucket(bucket_name)
            logger.info(f"Connected to existing bucket: {bucket_name}")
        except Exception as e:
            logger.warning(f"Bucket {bucket_name} not found, attempting to create: {str(e)}")
            try:
                self.bucket = self.client.create_bucket(bucket_name)
                logger.info(f"Created new bucket: {bucket_name}")
            except Exception as create_error:
                logger.error(f"Failed to create bucket: {str(create_error)}")
                raise
    
    def upload_file(
        self, 
        user_id: str, 
        file_path: str, 
        file_content: Union[BinaryIO, BytesIO, str, Path],
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to Google Cloud Storage
        
        Args:
            user_id: The user ID (used as a directory prefix)
            file_path: Path within the user's directory
            file_content: File content as BytesIO, path, or string
            content_type: Optional MIME type
            
        Returns:
            Full GCS path of the uploaded file
        """
        # Create full path in GCS (users/<user_id>/path/to/file)
        full_path = f"users/{user_id}/{file_path}"
        
        blob = self.bucket.blob(full_path)
        
        # Set content type if provided
        if content_type:
            blob.content_type = content_type
            
        # Handle different file_content types
        if isinstance(file_content, (BytesIO, BinaryIO)):
            blob.upload_from_file(file_content)
        elif isinstance(file_content, str) and os.path.isfile(file_content):
            blob.upload_from_filename(file_content)
        elif isinstance(file_content, Path) and file_content.is_file():
            blob.upload_from_filename(str(file_content))
        else:
            # Assume it's a string content
            blob.upload_from_string(str(file_content))
            
        logger.info(f"Uploaded file to GCS: {full_path}")
        return full_path
    
    def download_file(self, gcs_path: str, local_path: str) -> bool:
        """
        Download a file from GCS to a local path
        
        Args:
            gcs_path: Full path in GCS or relative to bucket
            local_path: Local path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Handle paths that might include the bucket name
            if gcs_path.startswith(f"gs://{self.bucket_name}/"):
                path = gcs_path[len(f"gs://{self.bucket_name}/"):]
            else:
                path = gcs_path
                
            blob = self.bucket.blob(path)
            blob.download_to_filename(local_path)
            
            logger.info(f"Downloaded {gcs_path} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download {gcs_path}: {str(e)}")
            return False
    
    def create_directory(self, user_id: str, directory: str) -> bool:
        """
        Create a directory in GCS (actually creates a blank placeholder object)
        
        Args:
            user_id: User ID
            directory: Directory to create
            
        Returns:
            True if successful
        """
        # Clean the directory path
        dir_path = directory.rstrip("/")
        
        # Create placeholder object
        path = f"users/{user_id}/{dir_path}/.placeholder"
        blob = self.bucket.blob(path)
        blob.upload_from_string("")
        
        logger.info(f"Created directory in GCS: users/{user_id}/{dir_path}")
        return True
    
    def list_files(self, user_id: str, directory: str = "") -> list:
        """
        List files in a GCS directory
        
        Args:
            user_id: User ID
            directory: Directory path (optional)
            
        Returns:
            List of file paths
        """
        prefix = f"users/{user_id}/{directory}"
        if prefix and not prefix.endswith("/"):
            prefix += "/"
            
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        
        return [blob.name for blob in blobs]
    
    def delete_file(self, gcs_path: str) -> bool:
        """
        Delete a file from GCS
        
        Args:
            gcs_path: Full path in GCS
            
        Returns:
            True if deleted successfully
        """
        try:
            if gcs_path.startswith(f"gs://{self.bucket_name}/"):
                path = gcs_path[len(f"gs://{self.bucket_name}/"):]
            else:
                path = gcs_path
                
            blob = self.bucket.blob(path)
            blob.delete()
            
            logger.info(f"Deleted file from GCS: {gcs_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {gcs_path}: {str(e)}")
            return False

def get_gcs_handler() -> GCSStorageHandler:
    """
    Factory function to get a configured GCS handler
    
    Returns:
        Configured GCS handler instance
    """
    # Get configuration from environment variables
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    credentials_content = os.environ.get("GCS_CREDENTIALS_JSON")
    
    if not bucket_name:
        raise ValueError("GCS_BUCKET_NAME environment variable is required")
    
    credentials = None
    
    # If credentials provided as path
    if credentials_json and os.path.exists(credentials_json):
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        logger.info(f"Using GCS credentials from file: {credentials_json}")
    
    # If credentials provided as JSON content
    elif credentials_content:
        # Create temporary file with credentials content
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write(credentials_content)
            temp_path = temp_file.name
        
        try:
            credentials = service_account.Credentials.from_service_account_file(temp_path)
            logger.info("Using GCS credentials from environment variable")
        finally:
            # Remove temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    return GCSStorageHandler(bucket_name, credentials)

if __name__ == "__main__":
    # Simple test to verify GCS configuration
    try:
        handler = get_gcs_handler()
        print(f"Successfully initialized GCS handler for bucket: {handler.bucket_name}")
        
        # List the root directories
        blobs = handler.client.list_blobs(handler.bucket_name, prefix="", delimiter="/")
        print("Root directories:")
        for prefix in blobs.prefixes:
            print(f"- {prefix}")
            
    except Exception as e:
        print(f"Failed to initialize GCS handler: {str(e)}") 