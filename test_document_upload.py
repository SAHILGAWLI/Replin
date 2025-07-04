import os
import requests
import argparse
from pathlib import Path
os.environ["DEEPGRAM_API_KEY"] = "46dc27edd5a1de0dd3c652b9a6059649340ea5aa"
os.environ["OPENAI_API_KEY"] = "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"
os.environ["CARTESIA_API_KEY"] = "sk_car_GSJ35Gm4DBHpE3ZXWCrumB"

os.environ["LIVEKIT_URL"] = "wss://best-xy0fdmnc.livekit.cloud"
os.environ["LIVEKIT_API_KEY"] = "APIYm4aBpab8vTY"
os.environ["LIVEKIT_API_SECRET"] = "wgEMadTahhxElFmAa6bMlQMullI83mbLeo8sqbchzFT"

os.environ["SIP_TRUNK_ID"] = "ST_jgGFecEDULvV"  
def upload_files(api_url, user_id, file_paths, collection_name=None):
    """Upload files to the document processing API"""
    url = f"{api_url}/upload/{user_id}"
    
    # Prepare files for upload
    files = []
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            print(f"Warning: File {file_path} does not exist. Skipping.")
            continue
            
        files.append(
            ('files', (path.name, open(path, 'rb'), 'application/octet-stream'))
        )
    
    if not files:
        print("Error: No valid files to upload")
        return
    
    # Add collection name if provided
    data = {}
    if collection_name:
        data['collection_name'] = collection_name
    
    # Make the request
    try:
        response = requests.post(url, files=files, data=data)
        
        # Close all file handles
        for _, (_, file_obj, _) in files:
            file_obj.close()
            
        # Check response
        if response.status_code == 200:
            result = response.json()
            print(f"Success: {result['message']}")
            print(f"Document count: {result['document_count']}")
            print(f"Index ID: {result['index_id']}")
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error uploading files: {str(e)}")
        
        # Ensure all file handles are closed
        for _, (_, file_obj, _) in files:
            file_obj.close()

def save_config(api_url, user_id, system_prompt, voice="alloy", model="gpt-4o-mini", agent_name=None):
    """Save agent configuration for a user"""
    url = f"{api_url}/config/{user_id}"
    
    config = {
        "system_prompt": system_prompt,
        "voice": voice,
        "model": model
    }
    
    if agent_name:
        config["agent_name"] = agent_name
    
    try:
        response = requests.post(url, json=config)
        
        if response.status_code == 200:
            result = response.json()
            print(f"Config saved: {result['message']}")
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error saving config: {str(e)}")

def list_collections(api_url, user_id):
    """List all document collections for a user"""
    url = f"{api_url}/collections/{user_id}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            result = response.json()
            collections = result.get("collections", [])
            
            if not collections:
                print(f"No collections found for user {user_id}")
                return
            
            print(f"Collections for user {user_id}:")
            for collection in collections:
                default_marker = " (default)" if collection.get("is_default") else ""
                print(f"- {collection['name']}{default_marker}")
                print(f"  Path: {collection['path']}")
                print()
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error listing collections: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test document upload API")
    parser.add_argument("--api", default="http://localhost:8000", help="API URL")
    parser.add_argument("--user", required=True, help="User ID")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload documents")
    upload_parser.add_argument("files", nargs="+", help="Files to upload")
    upload_parser.add_argument("--collection", help="Collection name")
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Save agent configuration")
    config_parser.add_argument("--prompt", required=True, help="System prompt")
    config_parser.add_argument("--voice", default="alloy", help="Voice for TTS")
    config_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    config_parser.add_argument("--name", help="Agent name")
    
    # List collections command
    subparsers.add_parser("list", help="List document collections")
    
    args = parser.parse_args()
    
    if args.command == "upload":
        upload_files(args.api, args.user, args.files, args.collection)
    elif args.command == "config":
        save_config(args.api, args.user, args.prompt, args.voice, args.model, args.name)
    elif args.command == "list":
        list_collections(args.api, args.user)
    else:
        parser.print_help() 