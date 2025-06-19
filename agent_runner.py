# agent_runner.py
import os
import sys
import argparse
import json
from pathlib import Path
import subprocess # <--- Ensure this is imported


# Base directory for all user data
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))

def main():
    parser = argparse.ArgumentParser(description="Unified agent runner")
    parser.add_argument("--user-id", required=True, help="User ID for whom to run the agent")
    parser.add_argument("--core-script", required=True, choices=['web-user', 'user-agent'],
                        help="Specify which core agent script to run ('web-user' or 'user-agent')")

    args = parser.parse_args()
    user_id = args.user_id
    core_script_choice = args.core_script

    print(f"--- agent_runner.py: Initializing for user: {user_id}, using core script: {core_script_choice}.py ---")

    # --- 1. Load User-Specific Configuration ---
    config_file_path = BASE_STORAGE_DIR / user_id / "config" / "agent_config.json"
    if not config_file_path.exists():
        print(f"ERROR (agent_runner.py): Configuration file not found for user {user_id} at {config_file_path}")
        sys.exit(1)

    try:
        with open(config_file_path, "r") as f:
            user_config_data = json.load(f)
        print(f"INFO (agent_runner.py): Successfully loaded configuration for user {user_id} from {config_file_path}")
    except json.JSONDecodeError as e:
        print(f"ERROR (agent_runner.py): Failed to parse JSON configuration file {config_file_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR (agent_runner.py): Failed to load configuration file {config_file_path}: {e}")
        sys.exit(1)

    # --- 2. Set Environment Variables from Configuration ---
    print(f"INFO (agent_runner.py): Setting environment variables for user {user_id}...")

    os.environ["USER_AGENT_USER_ID"] = user_id
    print(f"  SET USER_AGENT_USER_ID={user_id}")

    collection_name = user_config_data.get("collection_name_preference")
    if collection_name:
        os.environ["USER_AGENT_COLLECTION"] = collection_name
        print(f"  SET USER_AGENT_COLLECTION={collection_name}")
    else:
        if "USER_AGENT_COLLECTION" in os.environ: del os.environ["USER_AGENT_COLLECTION"]
        print(f"  INFO: USER_AGENT_COLLECTION not set (not found in user config).")

    phone_number = user_config_data.get("default_phone_number_to_dial")
    if phone_number:
        os.environ["USER_AGENT_PHONE"] = phone_number
        print(f"  SET USER_AGENT_PHONE={phone_number}")
    else:
        if "USER_AGENT_PHONE" in os.environ: del os.environ["USER_AGENT_PHONE"]
        print(f"  INFO: USER_AGENT_PHONE not set (not found in user config).")

    required_env_vars_from_config = {
        "OPENAI_API_KEY": user_config_data.get("openai_api_key"),
        "LIVEKIT_URL": user_config_data.get("livekit_url"),
        "LIVEKIT_API_KEY": user_config_data.get("livekit_api_key"),
        "LIVEKIT_API_SECRET": user_config_data.get("livekit_api_secret"),
        "DEEPGRAM_API_KEY": user_config_data.get("deepgram_api_key"),
        "CARTESIA_API_KEY": user_config_data.get("cartesia_api_key"),
    }
    missing_keys = [key for key, value in required_env_vars_from_config.items() if not value]
    if missing_keys:
        print(f"ERROR (agent_runner.py): Missing required API keys/details in config for user {user_id}: {', '.join(missing_keys)}")
        sys.exit(1)

    for key, value in required_env_vars_from_config.items():
        if value:
            os.environ[key] = value
            print(f"  SET {key} (from user config)")

    if user_config_data.get("sip_trunk_id"):
        os.environ["SIP_TRUNK_ID"] = user_config_data["sip_trunk_id"]
        print(f"  SET SIP_TRUNK_ID (from user config)")
    else:
        if "SIP_TRUNK_ID" in os.environ: del os.environ["SIP_TRUNK_ID"]
        
    print(f"INFO (agent_runner.py): Environment variables set based on user '{user_id}' configuration.")

    # --- 3. Determine and Launch the Core Agent Script ---
    core_script_name = f"{core_script_choice}.py"
    core_script_path = Path(__file__).resolve().parent / core_script_name

    if not core_script_path.exists():
        print(f"ERROR (agent_runner.py): Core agent script '{core_script_name}' not found at {core_script_path}")
        sys.exit(1)

    # Add the "start" command for the LiveKit agent CLI
    cmd = [sys.executable, str(core_script_path), "start"] # <--- "start" ADDED HERE

    print(f"INFO (agent_runner.py): Starting core agent script: {' '.join(cmd)}")
    print(f"--- agent_runner.py: Handing off to {core_script_name} for user {user_id} ---")
    sys.stdout.flush()

    try:
        process_result = subprocess.run(cmd)
        print(f"--- agent_runner.py: Core agent script '{core_script_name}' for user {user_id} has exited with code {process_result.returncode}. ---")
        sys.exit(process_result.returncode)
    except FileNotFoundError:
        print(f"ERROR (agent_runner.py): Python executable '{sys.executable}' or script '{core_script_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR (agent_runner.py): An unexpected error occurred while trying to run '{core_script_name}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()