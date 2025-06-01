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
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-manager")

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

def create_killswitch(agent_id, user_id):
    """Create a killswitch batch file for the agent"""
    killswitch = os.path.join(AGENT_TRACKING_DIR, f"kill_{agent_id}.bat")
    with open(killswitch, "w") as f:
        f.write(f"@echo off\n")
        f.write(f"echo Terminating agent {agent_id} for user {user_id}...\n")
        
        # Try multiple termination strategies
        # 1. PowerShell direct window closing (most reliable)
        f.write(f"powershell -Command \"Get-Process | Where-Object {{$_.MainWindowTitle -like '*{agent_id}*'}} | ForEach-Object {{$_.CloseMainWindow()}} | Out-Null\"\n")
        
        # 2. Try taskkill with various filters
        f.write(f"taskkill /F /FI \"WINDOWTITLE eq Agent-{agent_id}*\" /T\n")
        f.write(f"taskkill /F /FI \"WINDOWTITLE eq *{agent_id}*\" /T\n")
        f.write(f"taskkill /F /FI \"IMAGENAME eq python.exe\" /FI \"COMMANDLINE eq *{agent_id}*\" /T\n")
        f.write(f"taskkill /F /FI \"IMAGENAME eq cmd.exe\" /FI \"WINDOWTITLE eq *{agent_id}*\" /T\n")
        
        # 3. Kill cmd.exe processes more aggressively
        f.write(f"wmic process where \"name='cmd.exe' and commandline like '%{agent_id}%'\" call terminate\n")
        
        # Clean up files
        f.write(f"del \"{os.path.join(AGENT_TRACKING_DIR, f'agent_{agent_id}.pid')}\" 2>nul\n")
        f.write(f"del \"{os.path.join(AGENT_TRACKING_DIR, f'agent_{agent_id}.bat')}\" 2>nul\n")
        f.write(f"echo Agent terminated.\n")
        f.write(f"del \"%~f0\"\n")  # Self-delete
    return killswitch

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
    
    # Choose script based on agent type
    script = "web-agent-run.py" if request.agent_type == "voice" else "run_agent.py"
    
    # Create marker files
    pid_file = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.pid")
    
    # Create a wrapped Python script to run the agent
    # This ensures the process can be cleanly terminated
    wrapper_script = os.path.join(AGENT_TRACKING_DIR, f"wrapper_{agent_id}.py")
    with open(wrapper_script, "w") as f:
        f.write("import sys\n")
        f.write("import os\n")
        f.write("import subprocess\n")
        f.write("import time\n\n")
        
        # Create the PID file
        f.write(f"with open(r'{pid_file}', 'w') as pid_file:\n")
        f.write(f"    pid_file.write(str(os.getpid()))\n\n")
        
        # Build the command
        f.write(f"cmd = [sys.executable, '{script}', '--user', '{user_id}'")
        if request.collection_name:
            f.write(f", '--collection', '{request.collection_name}'")
        if request.phone_number:
            f.write(f", '--phone', '{request.phone_number}'")
        f.write(f", '--port', '{agent_port}']\n\n")
        
        # Run the command
        f.write("try:\n")
        f.write("    process = subprocess.Popen(cmd)\n")
        f.write("    process.wait()\n")
        f.write("finally:\n")
        f.write(f"    if os.path.exists(r'{pid_file}'):\n")
        f.write(f"        os.remove(r'{pid_file}')\n")
    
    # Create the batch file to run this specific agent
    batch_file = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.bat")
    with open(batch_file, "w") as f:
        f.write(f"@echo off\n")
        f.write(f"title Agent-{agent_id}-{user_id}\n")  # Set window title for identification
        f.write(f"echo Agent ID: {agent_id}\n")
        f.write(f"echo User ID: {user_id}\n")
        f.write(f"echo Port: {agent_port}\n")
        # Use start /b to run the python script without creating a new window
        f.write(f"start /b python \"{wrapper_script}\"\n")
        # Self-delete this batch file after starting the agent
        f.write(f"(goto) 2>nul & del \"%~f0\"\n")
    
    # Create killswitch file
    killswitch = create_killswitch(agent_id, user_id)
    
    # Start the process
    try:
        # Start the batch file in a new cmd window
        # Use /c instead of /k to make the cmd window close after script execution
        subprocess.Popen(
            ["cmd", "/c", batch_file],
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        # Wait a moment to make sure PID file is created
        await asyncio.sleep(1)
        
        # Store agent info
        running_agents[user_id] = {
            "agent_id": agent_id,
            "batch_file": batch_file,
            "wrapper_script": wrapper_script,
            "pid_file": pid_file,
            "killswitch": killswitch,
            "started_at": time.time(),
            "agent_type": request.agent_type,
            "port": agent_port
        }
        
        logger.info(f"Started {request.agent_type} agent for user {user_id} on port {agent_port} (Agent ID: {agent_id})")
        return {"status": "started", "user_id": user_id, "port": agent_port, "agent_id": agent_id}
    
    except Exception as e:
        # Clean up files if there was an error
        for file in [batch_file, pid_file, killswitch, wrapper_script]:
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
        # Get current process ID to exclude from termination
        current_pid = os.getpid()
        
        # Create a special script that will kill ALL agent processes - with error handling
        kill_script = os.path.join(AGENT_TRACKING_DIR, f"kill_{agent_id}.bat")
        with open(kill_script, "w") as f:
            f.write("@echo off\n")
            f.write("setlocal enabledelayedexpansion\n")  # Enable better variable handling
            f.write(f"echo KILL SCRIPT FOR AGENT {agent_id}\n")
            f.write(f"echo Current server PID: {current_pid} (will be protected)\n")
            
            # Direct taskkill on PID file if it exists
            f.write("echo Checking PID file...\n")
            pid_file = agent_info.get("pid_file")
            if pid_file and os.path.exists(pid_file):
                f.write(f"if exist \"{pid_file}\" (\n")
                f.write(f"  for /f \"tokens=*\" %%p in ('type \"{pid_file}\"') do (\n")
                f.write("    echo Found PID: %%p\n")
                f.write("    taskkill /F /PID %%p /T 2>nul\n")
                f.write("    if !errorlevel! equ 0 (\n")
                f.write("      echo Successfully killed process %%p\n")
                f.write("    ) else (\n")
                f.write("      echo Failed to kill process %%p, error !errorlevel!\n")
                f.write("    )\n")
                f.write("  )\n")
                f.write(")\n\n")
            
            # Kill by process name and command line content - but skip server processes
            script_types = ["user_agent.py", "run_agent.py", "web-agent-run.py", "web-user.py"]
            for script_type in script_types:
                f.write(f"echo Killing {script_type} processes...\n")
                # Exclude server processes on ports 8000 and 8001, and exclude the current PID
                f.write(f"for /f \"usebackq tokens=1\" %%p in (`wmic process where \"name='python.exe' and commandline like '%{script_type}%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'\" get processid /format:value ^| find \"ProcessId\"`) do (\n")
                f.write("  set pline=%%p\n")
                f.write("  set pid=!pline:ProcessId=!\n")
                f.write("  if not \"!pid!\" == \"\"{current_pid}\" (\n")
                f.write("    echo Killing !pid! running {}\n".format(script_type))
                f.write("    taskkill /F /PID !pid! /T 2>nul\n")
                f.write("    if !errorlevel! equ 0 (\n")
                f.write("      echo Successfully killed !pid!\n")
                f.write("    ) else (\n")
                f.write("      echo Failed to kill !pid!, error !errorlevel!\n")
                f.write("    )\n")
                f.write("  ) else (\n")
                f.write("    echo Skipping server process !pid!\n")
                f.write("  )\n")
                f.write(")\n\n")
            
            # Specifically target agent-related processes only
            if agent_id:
                f.write(f"echo Killing processes with agent ID {agent_id}...\n")
                f.write(f"for /f \"usebackq tokens=1\" %%p in (`wmic process where \"name='python.exe' and commandline like '%{agent_id}%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'\" get processid /format:value ^| find \"ProcessId\"`) do (\n")
                f.write("  set pline=%%p\n")
                f.write("  set pid=!pline:ProcessId=!\n")
                f.write("  if not \"!pid!\" == \"\"{current_pid}\" (\n")
                f.write("    echo Killing agent ID process: !pid!\n")
                f.write("    taskkill /F /PID !pid! /T 2>nul\n")
                f.write("    if !errorlevel! equ 0 (\n")
                f.write("      echo Successfully killed !pid!\n")
                f.write("    ) else (\n")
                f.write("      echo Failed to kill !pid!, error !errorlevel!\n")
                f.write("    )\n")
                f.write("  ) else (\n")
                f.write("    echo Skipping server process !pid!\n")
                f.write("  )\n")
                f.write(")\n\n")
            
            # Target processes by user ID, but protect servers
            f.write(f"echo Killing processes with user ID {user_id}...\n")
            f.write(f"for /f \"usebackq tokens=1\" %%p in (`wmic process where \"name='python.exe' and commandline like '%{user_id}%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'\" get processid /format:value ^| find \"ProcessId\"`) do (\n")
            f.write("  set pline=%%p\n")
            f.write("  set pid=!pline:ProcessId=!\n")
            f.write("  if not \"!pid!\" == \"\"{current_pid}\" (\n")
            f.write("    echo Killing user ID process: !pid!\n")
            f.write("    taskkill /F /PID !pid! /T 2>nul\n")
            f.write("    if !errorlevel! equ 0 (\n")
            f.write("      echo Successfully killed !pid!\n")
            f.write("    ) else (\n")
            f.write("      echo Failed to kill !pid!, error !errorlevel!\n")
            f.write("    )\n")
            f.write("  ) else (\n")
            f.write("    echo Skipping server process !pid!\n")
            f.write("  )\n")
            f.write(")\n\n")
            
            # Kill by window title - simpler approach
            f.write(f"echo Killing CMD windows with agent ID {agent_id}...\n")
            f.write(f"taskkill /F /FI \"WINDOWTITLE eq *{agent_id}*\" /T\n")
            f.write("if %errorlevel% equ 0 (\n")
            f.write("  echo Successfully killed processes by window title\n")
            f.write(") else (\n")
            f.write("  echo No processes found by window title, or error %errorlevel%\n")
            f.write(")\n\n")
            
            # Clean up files
            f.write("echo Cleaning up files...\n")
            for file_key in ["pid_file", "wrapper_script"]:
                if file_key in agent_info:
                    file_path = agent_info[file_key]
                    if file_path and os.path.exists(file_path):
                        f.write(f"if exist \"{file_path}\" del \"{file_path}\" 2>nul\n")
            
            f.write("echo Agent termination complete.\n")
            f.write("timeout /t 2\n")
            f.write("del \"%~f0\"\n")  # Self-delete
        
        # Execute the kill script with explicit logging
        logger.info(f"Executing kill script for agent {agent_id} (user {user_id})")
        
        # Run the script and capture output
        process = subprocess.Popen(
            kill_script,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit for script to run
        try:
            stdout, stderr = process.communicate(timeout=10)
            logger.info(f"Kill script output: {stdout}")
            if stderr:
                logger.error(f"Kill script errors: {stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("Kill script timed out")
            process.kill()
        
        # Final cleanup - direct process termination as backup
        try:
            # More selective taskkill for agent-specific processes only
            # Explicitly exclude server ports 8000 and 8001
            agent_port = agent_info.get("port", 0)
            cmd = f"wmic process where \"name='python.exe' and commandline like '%--port {agent_port}%'\" get processid /format:value | find \"ProcessId\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if "ProcessId" in line:
                    pid = line.replace("ProcessId=", "").strip()
                    if pid and pid != str(current_pid):
                        try:
                            subprocess.run(f"taskkill /F /PID {pid} /T", shell=True, check=False)
                            logger.info(f"Terminated agent process: {pid}")
                        except Exception as e:
                            logger.warning(f"Failed to terminate process {pid}: {str(e)}")
        except Exception as e:
            logger.warning(f"Error in final termination: {str(e)}")
        
        # Clean up any remaining tracking files
        for file_key in ["batch_file", "pid_file", "wrapper_script"]:
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
            for file_key in ["batch_file", "wrapper_script"]:
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
                    for file_key in ["batch_file", "wrapper_script"]:
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
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8001))) 