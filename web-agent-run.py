import os
import sys
import argparse
from dotenv import load_dotenv
import subprocess
os.environ["DEEPGRAM_API_KEY"] = "657cde1d9a8d627bf957fc41d2d5bd826b5f0ddb"
os.environ["OPENAI_API_KEY"] = "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"
os.environ["CARTESIA_API_KEY"] = "sk_car_xhtk8qBXANW8EajerEMSxn"

os.environ["LIVEKIT_URL"] = "wss://best-xy0fdmnc.livekit.cloud"
os.environ["LIVEKIT_API_KEY"] = "APIYm4aBpab8vTY"
os.environ["LIVEKIT_API_SECRET"] = "wgEMadTahhxElFmAa6bMlQMullI83mbLeo8sqbchzFT"

os.environ["SIP_TRUNK_ID"] = "ST_jgGFecEDULvV"  
# Load environment variables
load_dotenv()

def main():
    """Main entry point for running an agent with user-specific configuration"""
    parser = argparse.ArgumentParser(description="Start a user-specific voice agent")
    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--collection", help="Collection name (optional)")
    parser.add_argument("--phone", help="Phone number for outbound call (optional)")
    parser.add_argument("--port", type=int, help="Port number for the agent", default=0)
    
    args, unknown = parser.parse_known_args()
    
    # Set environment variables for the user agent
    os.environ["USER_AGENT_USER_ID"] = args.user
    if args.collection:
        os.environ["USER_AGENT_COLLECTION"] = args.collection
    if args.phone:
        os.environ["USER_AGENT_PHONE"] = args.phone
    if args.port:
        os.environ["USER_AGENT_PORT"] = str(args.port)
    
    # Build the command to run the web-user.py script
    # Don't pass the port directly as web-user.py doesn't support it
    cmd = [sys.executable, "web-user.py", "start"]
    
    # Run the command
    print(f"Starting agent for user: {args.user}")
    if args.collection:
        print(f"Using collection: {args.collection}")
    if args.phone:
        print(f"With outbound call to: {args.phone}")
    if args.port:
        print(f"Listening on port: {args.port}")
    
    subprocess.run(cmd)

if __name__ == "__main__":
    main() 