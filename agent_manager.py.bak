import os
import time
import json
import logging
import asyncio
import subprocess
import random
import string
import signal
import psutil
import platform
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-manager")

# Detect operating system
IS_WINDOWS = platform.system() == "Windows"
logger.info(f"Detected platform: {platform.system()}")

app = FastAPI(title="Voice Agent Manager")

# Add CORS middleware to handle OPTIONS preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, change this to your actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store running processes
running_agents = {}

# Directory for tracking agents
AGENT_TRACKING_DIR = os.path.join(os.getcwd(), "agent_tracking")
os.makedirs(AGENT_TRACKING_DIR, exist_ok=True)

class AgentRequest(BaseModel):
    user_id: str
    collection_name: str = None
    phone_number: str = None
    agent_type: str = "voice"  # "voice" or "web"

def generate_agent_id():
    """Generate a unique agent ID for tracking"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_agent_script(agent_id, user_id, agent_type, collection_name=None, phone_number=None, port=None):
    """Create a platform-independent script to run the agent"""
    script_path = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.py")
    
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env python3\n")
        f.write("import os\n")
        f.write("import sys\n")
        f.write("import subprocess\n")
        f.write("import signal\n")
        f.write("import time\n\n")
        
        # Create the PID file
        pid_file = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.pid")
        f.write(f"# Write PID to file\n")
        f.write(f"with open(r'{pid_file}', 'w') as pid_file:\n")
        f.write(f"    pid_file.write(str(os.getpid()))\n\n")
        
        # Set environment variables
        f.write(f"# Set environment variables\n")
        f.write(f"os.environ['USER_AGENT_USER_ID'] = '{user_id}'\n")
        if collection_name:
            f.write(f"os.environ['USER_AGENT_COLLECTION'] = '{collection_name}'\n")
        if phone_number:
            f.write(f"os.environ['USER_AGENT_PHONE'] = '{phone_number}'\n")
        if port:
            f.write(f"os.environ['USER_AGENT_PORT'] = '{port}'\n")
        
        # Determine which script to run
        script_name = "web-agent-run.py" if agent_type == "voice" else "run_agent.py"
        
        # Build and execute the command
        f.write(f"\n# Build and run the command\n")
        f.write(f"cmd = [sys.executable, '{script_name}'")
        f.write(f", '--user', '{user_id}'")
        if collection_name:
            f.write(f", '--collection', '{collection_name}'")
        if phone_number:
            f.write(f", '--phone', '{phone_number}'")
        if port:
            f.write(f", '--port', '{port}'")
        f.write(f"]\n\n")
        
        # Handle signals for clean shutdown
        f.write("def handle_signal(signum, frame):\n")
        f.write("    print(f'Received signal {signum}, shutting down agent')\n")
        f.write("    if 'process' in globals() and process:\n")
        f.write("        process.terminate()\n")
        f.write(f"    if os.path.exists(r'{pid_file}'):\n")
        f.write(f"        os.remove(r'{pid_file}')\n")
        f.write("    sys.exit(0)\n\n")
        
        f.write("signal.signal(signal.SIGTERM, handle_signal)\n")
        f.write("signal.signal(signal.SIGINT, handle_signal)\n\n")
        
        # Run the process
        f.write("try:\n")
        f.write("    process = subprocess.Popen(cmd)\n")
        f.write("    process.wait()\n")
        f.write("except Exception as e:\n")
        f.write("    print(f'Error running agent: {str(e)}')\n")
        f.write("finally:\n")
        f.write(f"    if os.path.exists(r'{pid_file}'):\n")
        f.write(f"        os.remove(r'{pid_file}')\n")
    
    # Make script executable on Unix systems
    if not IS_WINDOWS:
        try:
            os.chmod(script_path, 0o755)
        except Exception as e:
            logger.warning(f"Could not make script executable: {str(e)}")
    
    return script_path

def kill_process_tree(pid):
    """Kill a process and all its children in a platform-independent way"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # First try to terminate children gracefully
        for child in children:
            try:
                child.terminate()
            except:
                pass
        
        # Wait for children to terminate
        _, still_alive = psutil.wait_procs(children, timeout=1)
        
        # Force kill any remaining children
        for child in still_alive:
            try:
                child.kill()
            except:
                pass
        
        # Terminate parent
        parent.terminate()
        parent.wait(timeout=1)
        
        # Force kill if still alive
        if parent.is_running():
            parent.kill()
            parent.wait(timeout=1)
            
    except psutil.NoSuchProcess:
        pass  # Process already gone
    except Exception as e:
        logger.warning(f"Error killing process tree: {str(e)}")

@app.post("/start-agent")
async def start_agent(request: AgentRequest):
    """Start an agent for a specific user"""
    user_id = request.user_id
    
    # Check if agent is already running
    if user_id in running_agents:
        # Check if the PID file still exists
        pid_file = running_agents[user_id].get("pid_file")
        if pid_file and os.path.exists(pid_file):
            return {"status": "already_running", "user_id": user_id}
        else:
            # Clean up stale entry
            del running_agents[user_id]
    
    # Generate unique agent ID and port for this agent
    agent_id = generate_agent_id()
    base_port = 9000
    agent_port = base_port + (hash(user_id) % 1000)  # Port between 9000-9999
    
    # Create PID file path
    pid_file = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.pid")
    
    # Create agent script
    agent_script = create_agent_script(
        agent_id=agent_id,
        user_id=user_id,
        agent_type=request.agent_type,
        collection_name=request.collection_name,
        phone_number=request.phone_number,
        port=agent_port
    )
    
    # Start the process in a platform-independent way
    try:
        # Platform-specific process creation that works for both Windows and Linux
        kwargs = {}
        
        # Common settings
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        
        # Platform-specific settings
        if IS_WINDOWS:
            # Windows-specific: Use subprocess flags that work on Windows
            # Import only on Windows to avoid errors on Linux
            try:
                from subprocess import CREATE_NEW_PROCESS_GROUP
                kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP
            except ImportError:
                # Fall back if import fails
                kwargs["creationflags"] = 0x00000200  # Value of CREATE_NEW_PROCESS_GROUP
        else:
            # Unix-specific: Use preexec_fn to create a new process group
            kwargs["preexec_fn"] = os.setpgrp if hasattr(os, 'setpgrp') else None
        
        # Start the process
        process = subprocess.Popen([sys.executable, agent_script], **kwargs)
        
        # Wait a moment to make sure PID file is created
        await asyncio.sleep(1)
        
        # Store agent info
        running_agents[user_id] = {
            "agent_id": agent_id,
            "script": agent_script,
            "pid_file": pid_file,
            "started_at": time.time(),
            "agent_type": request.agent_type,
            "port": agent_port
        }
        
        logger.info(f"Started {request.agent_type} agent for user {user_id} on port {agent_port} (Agent ID: {agent_id})")
        return {"status": "started", "user_id": user_id, "port": agent_port, "agent_id": agent_id}
    
    except Exception as e:
        # Clean up files if there was an error
        for file in [agent_script, pid_file]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass
        
        logger.error(f"Error starting agent for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")

@app.post("/stop-agent/{user_id}")
async def stop_agent(user_id: str):
    """Stop a running agent"""
    if user_id not in running_agents:
        raise HTTPException(status_code=404, detail=f"No agent running for user {user_id}")
    
    agent_info = running_agents[user_id]
    agent_id = agent_info["agent_id"]
    
    try:
        # Try to read PID from file
        pid_file = agent_info.get("pid_file")
        if pid_file and os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Try to terminate the process using platform-independent method
                logger.info(f"Terminating process {pid} for user {user_id}")
                try:
                    # Use our custom function that works on any platform
                    kill_process_tree(pid)
                except Exception as e:
                    logger.warning(f"Error terminating process {pid}: {str(e)}")
            except Exception as e:
                logger.warning(f"Error reading PID from file: {str(e)}")
        
        # Clean up any running processes by agent ID or user ID (platform independent)
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.cmdline() if proc.cmdline() else [])
                if (agent_id in cmdline or user_id in cmdline) and 'agent_manager' not in cmdline:
                    logger.info(f"Killing process {proc.pid} with cmdline: {cmdline[:50]}...")
                    try:
                        kill_process_tree(proc.pid)
                    except Exception as e:
                        logger.warning(f"Error killing process {proc.pid}: {str(e)}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Clean up files
        for file_key in ["script", "pid_file"]:
            if file_key in agent_info and agent_info[file_key] and os.path.exists(agent_info[file_key]):
                try:
                    os.remove(agent_info[file_key])
                except Exception as e:
                    logger.warning(f"Could not remove {file_key}: {str(e)}")
        
        logger.info(f"Terminated agent {agent_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error in termination process for agent {agent_id}, user {user_id}: {str(e)}")
    
    # Remove from running agents
    del running_agents[user_id]
    
    return {"status": "stopped", "user_id": user_id}

@app.get("/agents")
async def list_agents():
    """List all running agents"""
    # Clean up stale entries by checking pid files
    for user_id in list(running_agents.keys()):
        pid_file = running_agents[user_id].get("pid_file")
        if pid_file and not os.path.exists(pid_file):
            # PID file is gone, agent is no longer running
            logger.info(f"Removing stale agent entry for user {user_id}")
            for file_key in ["script"]:
                if file_key in running_agents[user_id] and running_agents[user_id][file_key] and os.path.exists(running_agents[user_id][file_key]):
                    try:
                        os.remove(running_agents[user_id][file_key])
                    except:
                        pass
            del running_agents[user_id]
    
    # Return active agents
    return {
        "agents": [
            {
                "user_id": user_id,
                "agent_type": info["agent_type"],
                "agent_id": info.get("agent_id", ""),
                "port": info.get("port", 0),
                "running_time": time.time() - info["started_at"]
            }
            for user_id, info in running_agents.items()
        ]
    }

# Cleanup function to run periodically
async def cleanup_stale_agents():
    """Clean up stale agent entries and leftover files"""
    while True:
        try:
            # Check for stale entries in running_agents
            for user_id in list(running_agents.keys()):
                pid_file = running_agents[user_id].get("pid_file")
                if pid_file and not os.path.exists(pid_file):
                    logger.info(f"Cleaning up stale agent for user {user_id}")
                    for file_key in ["script"]:
                        if file_key in running_agents[user_id] and running_agents[user_id][file_key] and os.path.exists(running_agents[user_id][file_key]):
                            try:
                                os.remove(running_agents[user_id][file_key])
                            except:
                                pass
                    del running_agents[user_id]
            
            # Clean up any orphaned files in the tracking directory
            current_time = time.time()
            for filename in os.listdir(AGENT_TRACKING_DIR):
                file_path = os.path.join(AGENT_TRACKING_DIR, filename)
                
                # Skip directories
                if os.path.isdir(file_path):
                    continue
                
                # Remove files older than 1 hour
                if current_time - os.path.getmtime(file_path) > 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"Removed stale file: {filename}")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
        
        await asyncio.sleep(300)  # Run every 5 minutes

if __name__ == "__main__":
    # Create tracking directory if it doesn't exist
    os.makedirs(AGENT_TRACKING_DIR, exist_ok=True)
    
    # Start cleanup task
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_stale_agents())
    
    # Start API server
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"Starting agent manager on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port) 