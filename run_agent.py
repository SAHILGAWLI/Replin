import os
import sys
import argparse
from dotenv import load_dotenv
import subprocess

# Load environment variables
load_dotenv()

def main():
    """Main entry point for running an agent with user-specific configuration"""
    parser = argparse.ArgumentParser(description="Start a user-specific voice agent")
    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--collection", help="Collection name (optional)")
    parser.add_argument("--phone", help="Phone number for outbound call (optional)")
    
    args, unknown = parser.parse_known_args()
    
    # Set environment variables for the user agent
    os.environ["USER_AGENT_USER_ID"] = args.user
    if args.collection:
        os.environ["USER_AGENT_COLLECTION"] = args.collection
    if args.phone:
        os.environ["USER_AGENT_PHONE"] = args.phone
    
    # Build the command to run the user_agent.py script
    cmd = [sys.executable, "user_agent.py", "start"]
    
    # Run the command
    print(f"Starting agent for user: {args.user}")
    if args.collection:
        print(f"Using collection: {args.collection}")
    if args.phone:
        print(f"With outbound call to: {args.phone}")
    
    subprocess.run(cmd)

if __name__ == "__main__":
    main() 