import os
import time
import json # Not used directly, but common
import logging
import asyncio
import subprocess
import random
import string
import signal
import psutil
import platform
import sys
from pathlib import Path # Not used directly, but good for path ops
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent-manager")

# Detect operating system
IS_WINDOWS = platform.system() == "Windows"
logger.info(f"Detected platform: {platform.system()}")

app = FastAPI(title="Voice Agent Manager")

# Define allowed origins
allowed_origins = [
    "https://replin.vercel.app",
    "http://localhost:3000",
    "https://quiet-colts-hammer.loca.lt",
    "https://five-lines-burn.loca.lt",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development. Consider restricting to `allowed_origins` in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store running processes: user_id -> agent_info_dict
running_agents = {}

AGENT_TRACKING_DIR = os.path.join(os.getcwd(), "agent_tracking")
os.makedirs(AGENT_TRACKING_DIR, exist_ok=True)

class AgentRequest(BaseModel):
    user_id: str
    collection_name: str = None
    phone_number: str = None
    agent_type: str = "voice"  # "voice" or "web"

def generate_agent_id():
    """Generate a unique agent ID."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_agent_script(agent_id, user_id, agent_type, collection_name=None, phone_number=None, port=None):
    """Create a platform-independent wrapper script to run the agent."""
    # Name of the wrapper script itself
    wrapper_script_path = os.path.join(AGENT_TRACKING_DIR, f"agent_wrapper_{agent_id}.py")
    # Path for the PID file, which will store the wrapper script's PID
    pid_file_path_str = os.path.join(AGENT_TRACKING_DIR, f"agent_{agent_id}.pid")

    # Ensure pid_file_path_str is properly escaped for embedding in the script string
    escaped_pid_file_path = pid_file_path_str.replace("\\", "\\\\") if IS_WINDOWS else pid_file_path_str

    actual_agent_script_name = "web-agent-run.py" if agent_type == "voice" else "run_agent.py"
    
    # For robustness, consider resolving actual_agent_script_name to an absolute path
    # or ensure it's in a location findable via PATH or relative to a known base.
    # For now, assuming it's in CWD or on PATH.
    # Example: actual_agent_script_abs_path = str(Path(sys.argv[0]).parent / actual_agent_script_name)

    script_content = f"""#!/usr/bin/env python3
import os
import sys
import subprocess
import signal
import time

# --- Configuration ---
PID_FILE = r'{escaped_pid_file_path}'
MY_PID = os.getpid()
DEBUG_LOG_PREFIX = f"[WrapperPID:{{MY_PID}} AgentID:{agent_id}]"

# --- Utility Functions ---
def log_debug(message):
    print(f"{{DEBUG_LOG_PREFIX}} {{message}}", flush=True)

def write_pid_file():
    log_debug(f"Writing my PID {{MY_PID}} to PID file: {{PID_FILE}}")
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(MY_PID))
    except Exception as e:
        log_debug(f"ERROR: Failed to write PID file: {{e}}")

def remove_pid_file():
    if os.path.exists(PID_FILE):
        log_debug(f"Removing PID file: {{PID_FILE}}")
        try:
            os.remove(PID_FILE)
        except Exception as e:
            log_debug(f"ERROR: Failed to remove PID file: {{e}}")

# --- Main Script Logic ---
write_pid_file() # Create PID file immediately

# Set environment variables for the actual agent
os.environ['USER_AGENT_USER_ID'] = '{user_id}'
if {collection_name is not None}: os.environ['USER_AGENT_COLLECTION'] = '{collection_name}'
if {phone_number is not None}: os.environ['USER_AGENT_PHONE'] = '{phone_number}'
if {port is not None}: os.environ['USER_AGENT_PORT'] = str({port})

# Build command for the actual agent
cmd = [sys.executable, '{actual_agent_script_name}']
cmd.extend(['--user', '{user_id}'])
cmd.extend(['--agent-id', '{agent_id}']) # Crucial for fallback process searching
if {collection_name is not None}: cmd.extend(['--collection', '{collection_name}'])
if {phone_number is not None}: cmd.extend(['--phone', '{phone_number}'])
if {port is not None}: cmd.extend(['--port', str({port})])

actual_agent_process = None

def signal_handler(signum, frame):
    global actual_agent_process
    log_debug(f"Received signal {{signum}}. Initiating shutdown sequence.")
    
    if actual_agent_process and actual_agent_process.poll() is None: # Check if process exists and is running
        log_debug(f"Attempting to terminate actual agent process (PID: {{actual_agent_process.pid}}).")
        actual_agent_process.terminate() # SIGTERM
        try:
            actual_agent_process.wait(timeout=5)
            log_debug(f"Actual agent (PID: {{actual_agent_process.pid}}) terminated gracefully.")
        except subprocess.TimeoutExpired:
            log_debug(f"Actual agent (PID: {{actual_agent_process.pid}}) did not terminate in 5s. Sending SIGKILL.")
            actual_agent_process.kill() # SIGKILL
            try:
                actual_agent_process.wait(timeout=2)
                log_debug(f"Actual agent (PID: {{actual_agent_process.pid}}) confirmed killed.")
            except subprocess.TimeoutExpired:
                log_debug(f"ERROR: Actual agent (PID: {{actual_agent_process.pid}}) failed to die even after SIGKILL.")
            except Exception as e_kill_wait:
                log_debug(f"ERROR: Waiting for agent SIGKILL: {{e_kill_wait}}")
        except Exception as e_term_wait:
            log_debug(f"ERROR: Waiting for agent SIGTERM: {{e_term_wait}}")
    else:
        log_debug(f"Actual agent process not found or already terminated when signal received.")
    
    remove_pid_file()
    log_debug(f"Exiting due to signal {{signum}}.")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler) # For manual Ctrl+C too

try:
    log_debug(f"Starting actual agent with command: {{' '.join(cmd)}}")
    actual_agent_process = subprocess.Popen(cmd)
    log_debug(f"Actual agent started (PID: {{actual_agent_process.pid if actual_agent_process else 'N/A'}}). Waiting for it to complete.")
    if actual_agent_process:
        actual_agent_process.wait() # Block until the agent process exits
        log_debug(f"Actual agent (PID: {{actual_agent_process.pid}}) exited with code: {{actual_agent_process.returncode}}.")
    else:
        log_debug(f"ERROR: Actual agent process was not started successfully.")
except Exception as e:
    log_debug(f"ERROR: Exception during agent execution or waiting: {{e}}")
finally:
    log_debug(f"Wrapper script cleanup and exit.")
    remove_pid_file() # Ensure PID file is removed on any exit path
"""
    with open(wrapper_script_path, "w") as f:
        f.write(script_content)
    
    if not IS_WINDOWS:
        try:
            os.chmod(wrapper_script_path, 0o755)
        except Exception as e:
            logger.warning(f"Could not make script {wrapper_script_path} executable: {e}")
    
    return wrapper_script_path, pid_file_path_str


def kill_process_tree(pid_to_kill: int):
    """Kill a process and all its children in a platform-independent way."""
    logger.info(f"Attempting to kill process tree for PID: {pid_to_kill}")
    try:
        parent = psutil.Process(pid_to_kill)
        logger.info(f"Found parent process: {parent.name()} (PID: {pid_to_kill})")

        # On Unix, if the process is a group leader (due to os.setpgrp), try killing the group first.
        if not IS_WINDOWS and hasattr(os, "killpg") and hasattr(os, "getpgid"):
            try:
                pgid = os.getpgid(pid_to_kill)
                if pid_to_kill == pgid: # It's a process group leader
                    logger.info(f"Unix: PID {pid_to_kill} is a group leader (PGID: {pgid}). Attempting SIGTERM on process group.")
                    os.killpg(pgid, signal.SIGTERM)
                    # Check if parent died (wait_procs expects a list)
                    gone, alive = psutil.wait_procs([parent], timeout=0.5) 
                    if not alive: # parent is gone
                        logger.info(f"Unix: Process group {pgid} (leader {pid_to_kill}) terminated by SIGTERM.")
                        return True # Successfully killed
                    else:
                        logger.info(f"Unix: Process group {pgid} did not terminate with SIGTERM. Attempting SIGKILL.")
                        os.killpg(pgid, signal.SIGKILL)
                        gone, alive = psutil.wait_procs([parent], timeout=0.2)
                        if not alive:
                            logger.info(f"Unix: Process group {pgid} (leader {pid_to_kill}) terminated by SIGKILL.")
                            return True # Successfully killed
                        else:
                            logger.warning(f"Unix: Failed to kill process group {pgid} (leader {pid_to_kill}). Falling back to psutil individual process kill.")
            except ProcessLookupError: # Process might have died before os.getpgid
                 logger.info(f"Unix: Process {pid_to_kill} not found during killpg attempt (likely already gone).")
                 return True # Treat as success
            except Exception as e_killpg:
                logger.warning(f"Unix: Error using killpg for pid {pid_to_kill} (PGID {pgid if 'pgid' in locals() else 'unknown'}): {e_killpg}. Falling back.")
        
        # Standard psutil method (also fallback for Unix if killpg fails or not applicable)
        children = parent.children(recursive=True)
        if children:
            logger.info(f"Found children via psutil: {[child.pid for child in children]}")
        else:
            logger.info(f"No children found for PID: {pid_to_kill} via psutil")

        for child in children:
            try:
                logger.info(f"Terminating child PID: {child.pid} ({child.name()})")
                child.terminate()
            except psutil.NoSuchProcess:
                logger.info(f"Child PID: {child.pid} already gone.")
            except Exception as e:
                logger.warning(f"Error terminating child PID {child.pid}: {e}")
        
        gone, still_alive = psutil.wait_procs(children, timeout=1)
        
        for child in still_alive:
            try:
                logger.info(f"Force killing child PID: {child.pid} ({child.name()})")
                child.kill()
            except psutil.NoSuchProcess: # Check added
                logger.info(f"Child PID: {child.pid} already gone before kill.")
            except Exception as e:
                logger.warning(f"Error force killing child PID {child.pid}: {e}")
        
        logger.info(f"Terminating parent PID: {pid_to_kill} ({parent.name()})")
        parent.terminate()
        parent.wait(timeout=1)
        
        if parent.is_running():
            logger.info(f"Parent PID: {pid_to_kill} still running, force killing.")
            parent.kill()
            parent.wait(timeout=1)
            if parent.is_running():
                logger.error(f"CRITICAL: Failed to kill parent PID: {pid_to_kill} even after force kill.")
                return False
            else:
                logger.info(f"Parent PID: {pid_to_kill} successfully force killed.")
        else:
            logger.info(f"Parent PID: {pid_to_kill} successfully terminated.")
        return True

    except psutil.NoSuchProcess:
        logger.info(f"Process {pid_to_kill} not found during kill_process_tree, likely already terminated.")
        return True # Treat as success
    except Exception as e:
        logger.error(f"Error in kill_process_tree for PID {pid_to_kill}: {str(e)}")
        return False


def _prune_stale_agents():
    """Synchronously prunes stale agents from `running_agents` based on PID file existence."""
    pruned_count = 0
    for user_id_iter, agent_info_iter in list(running_agents.items()): # Iterate on a copy
        pid_file_iter = agent_info_iter.get("pid_file")
        # Check if PID file exists AND if the process itself is still running
        pid_is_valid = False
        if pid_file_iter and os.path.exists(pid_file_iter):
            try:
                with open(pid_file_iter, 'r') as f_pid:
                    pid_val = int(f_pid.read().strip())
                if psutil.pid_exists(pid_val):
                    # Further check if the process name/cmdline matches expectations (optional, more complex)
                    pid_is_valid = True 
                else: # PID file exists, but process with that PID does not
                    logger.info(f"PID {pid_val} from {pid_file_iter} for user {user_id_iter} not running.")
            except Exception as e: # ValueError if PID file is corrupt, FileNotFoundError, etc.
                logger.warning(f"Error checking PID file {pid_file_iter} for user {user_id_iter}: {e}")
        
        if not pid_is_valid: # PID file gone, or process for PID in file gone
            logger.info(f"Pruning stale agent entry for user {user_id_iter} (PID file: {pid_file_iter}).")
            
            # Clean up wrapper script file if it exists
            wrapper_script_to_remove = agent_info_iter.get("script_path") # Ensure key matches what's stored
            if wrapper_script_to_remove and os.path.exists(wrapper_script_to_remove):
                try: os.remove(wrapper_script_to_remove)
                except Exception as e_script: logger.warning(f"Error removing stale script {wrapper_script_to_remove}: {e_script}")
            
            # Clean up PID file if it still exists (e.g. process died, file not cleaned by wrapper)
            if pid_file_iter and os.path.exists(pid_file_iter):
                try: os.remove(pid_file_iter)
                except Exception as e_pid: logger.warning(f"Error removing stale PID file {pid_file_iter}: {e_pid}")

            if user_id_iter in running_agents:
                del running_agents[user_id_iter]
            pruned_count += 1
            
    if pruned_count > 0:
        logger.info(f"Pruned {pruned_count} stale agent(s).")

@app.post("/start-agent")
async def start_agent(request: AgentRequest):
    """Start an agent for a specific user, ensuring only one agent runs globally."""
    _prune_stale_agents() # Prune before check to ensure accurate state

    # Global single-agent lock
    if running_agents:
        active_agent_details = [
            f"user {uid} (AgentID: {info.get('agent_id')}, Port: {info.get('port')})" 
            for uid, info in running_agents.items()
        ]
        details_str = ", ".join(active_agent_details)
        logger.warning(f"Attempt to start agent for user {request.user_id} while an agent is already running: {details_str}")
        raise HTTPException(
            status_code=409, # Conflict
            detail=f"An agent is already running ({details_str}). Only one agent can run at a time."
        )

    user_id = request.user_id
    agent_id = generate_agent_id()
    base_port = 9000 # Example base port
    # A simple port allocation, could be made more robust (check if port is free)
    agent_port = base_port + (sum(ord(c) for c in agent_id) % 1000) 
    
    wrapper_script_path, pid_file_path = create_agent_script(
        agent_id=agent_id,
        user_id=user_id,
        agent_type=request.agent_type,
        collection_name=request.collection_name,
        phone_number=request.phone_number,
        port=agent_port
    )
    
    # For debugging the wrapper script's output:
    wrapper_log_path = os.path.join(AGENT_TRACKING_DIR, f"agent_wrapper_{agent_id}.log")
    
    try:
        kwargs = {}
        # Open the log file for the wrapper script's stdout/stderr
        # This is very useful for debugging the wrapper script itself.
        wrapper_log_file = open(wrapper_log_path, "wb") # Binary mode for subprocess
        kwargs["stdout"] = wrapper_log_file
        kwargs["stderr"] = wrapper_log_file
        
        if IS_WINDOWS:
            try:
                from subprocess import CREATE_NEW_PROCESS_GROUP
                kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP
            except ImportError: # Should not happen with standard Python
                kwargs["creationflags"] = 0x00000200 # Value of CREATE_NEW_PROCESS_GROUP
        else: # Unix-like
            if hasattr(os, 'setpgrp'):
                kwargs["preexec_fn"] = os.setpgrp
            # else: no preexec_fn if os.setpgrp is not available (very rare)
        
        logger.info(f"Starting wrapper script '{wrapper_script_path}' for agent {agent_id} (user {user_id}). Logs: {wrapper_log_path}")
        # The Popen object here is for the wrapper script, not the actual agent.
        process_handle = subprocess.Popen([sys.executable, wrapper_script_path], **kwargs)
        
        # Give a moment for the wrapper script to start and write its PID file
        await asyncio.sleep(1.5) # Increased slightly for robustness

        # Verify PID file creation and process health
        if not os.path.exists(pid_file_path):
            # Wrapper failed to start or write PID file, clean up
            wrapper_log_file.close() # Close log file
            logger.error(f"PID file {pid_file_path} not created for agent {agent_id}. Check wrapper log: {wrapper_log_path}")
            # Try to terminate the process if it somehow started
            if process_handle.poll() is None: # If process is running
                process_handle.terminate()
                try: process_handle.wait(timeout=1)
                except subprocess.TimeoutExpired: process_handle.kill()
            # Clean up script
            if os.path.exists(wrapper_script_path): os.remove(wrapper_script_path)
            raise HTTPException(status_code=500, detail=f"Failed to start agent: PID file not created. Check manager logs and wrapper logs at {wrapper_log_path}.")

        running_agents[user_id] = {
            "agent_id": agent_id,
            "script_path": wrapper_script_path, # Store path to wrapper script
            "pid_file": pid_file_path,
            "wrapper_log_path": wrapper_log_path, # For potential future access/diag
            "wrapper_log_file_handle": wrapper_log_file, # Keep handle to close on stop
            "started_at": time.time(),
            "agent_type": request.agent_type,
            "port": agent_port
        }
        
        logger.info(f"Started {request.agent_type} agent (ID: {agent_id}) for user {user_id} on port {agent_port}. Wrapper PID: {process_handle.pid if process_handle else 'N/A'}")
        return {"status": "started", "user_id": user_id, "port": agent_port, "agent_id": agent_id}
    
    except Exception as e:
        logger.error(f"Error starting agent for user {user_id} (Agent ID: {agent_id}): {str(e)}", exc_info=True)
        # Clean up files if there was an error during startup
        if 'wrapper_log_file' in locals() and wrapper_log_file: wrapper_log_file.close()
        for file_to_remove in [wrapper_script_path, pid_file_path, wrapper_log_path]:
            if file_to_remove and os.path.exists(file_to_remove):
                try: os.remove(file_to_remove)
                except: pass
        # If user_id was added to running_agents prematurely, remove it
        if user_id in running_agents and running_agents[user_id].get("agent_id") == agent_id:
            del running_agents[user_id]
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")

@app.post("/stop-agent/{user_id}")
async def stop_agent(user_id: str):
    """Stop a running agent for a specific user."""
    _prune_stale_agents() # Clean up stale entries first

    if user_id not in running_agents:
        logger.warning(f"Stop request for user {user_id}, but no agent found in running_agents list.")
        # As a fallback, try to find and kill processes by user_id or agent_id from cmdline
        # This part could be enhanced if needed, but primary check is running_agents
        found_and_killed_fallback = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline_str = ' '.join(proc.cmdline() if proc.cmdline() else [])
                # This relies on --user and --agent-id being in the cmdline of the actual agent
                if (f"--user {user_id}" in cmdline_str or f"--agent-id" in cmdline_str) and \
                   'agent_manager' not in cmdline_str and 'agent_wrapper' not in cmdline_str: # Avoid self/wrapper
                    logger.info(f"Fallback: Found process {proc.pid} ({proc.name()}) matching user {user_id} or an agent ID. Attempting to kill.")
                    if kill_process_tree(proc.pid):
                        found_and_killed_fallback = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e_iter:
                logger.warning(f"Error during fallback process scan for stop_agent: {e_iter}")

        if found_and_killed_fallback:
             return {"status": "stopped_via_fallback", "user_id": user_id, "detail": "Agent was not in active list but matching processes were found and terminated."}
        raise HTTPException(status_code=404, detail=f"No active agent found for user {user_id} to stop.")
    
    agent_info = running_agents[user_id]
    agent_id = agent_info["agent_id"]
    pid_file = agent_info.get("pid_file")
    wrapper_script_path = agent_info.get("script_path")
    wrapper_log_path = agent_info.get("wrapper_log_path")
    wrapper_log_file_handle = agent_info.get("wrapper_log_file_handle")

    logger.info(f"Stopping agent {agent_id} for user {user_id}.")
    
    pid_from_file = None
    if pid_file and os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid_from_file = int(f.read().strip())
            logger.info(f"PID from file {pid_file} is {pid_from_file}.")
            if psutil.pid_exists(pid_from_file):
                kill_process_tree(pid_from_file) # This targets the wrapper script's PID
            else:
                logger.info(f"Process with PID {pid_from_file} from file {pid_file} no longer exists.")
        except ValueError: # If PID file is corrupt
            logger.warning(f"Could not parse PID from {pid_file}. It might be corrupted or empty.")
        except Exception as e:
            logger.warning(f"Error reading PID from file {pid_file} or initial termination: {str(e)}")
    else:
        logger.warning(f"PID file {pid_file} for agent {agent_id} not found. Process may have exited uncleanly or file was already removed.")

    # Fallback/aggressive cleanup: Iterate through processes to find any related to this agent_id or user_id
    # This helps catch orphaned actual agent processes if the wrapper failed.
    logger.info(f"Performing fallback scan for processes related to agent {agent_id} or user {user_id}.")
    killed_in_fallback = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.cmdline()
            if cmdline: # Ensure cmdline is not None or empty
                cmdline_str = ' '.join(cmdline)
                # Check for agent_id or user_id in arguments.
                # The actual agent script (e.g., web-agent-run.py) should have these in its args.
                is_target_agent_process = (f"--agent-id {agent_id}" in cmdline_str) or \
                                          (f"--user {user_id}" in cmdline_str and agent_id in cmdline_str) # More specific
                
                # Avoid killing the manager itself or unrelated wrappers
                is_manager_or_unrelated_wrapper = 'agent_manager.py' in cmdline_str or \
                                                  ('agent_wrapper_' in cmdline_str and f"agent_wrapper_{agent_id}.py" not in cmdline_str)


                if is_target_agent_process and not is_manager_or_unrelated_wrapper:
                    # Check if this PID is the same as pid_from_file, if so, it should have been handled
                    if pid_from_file and proc.pid == pid_from_file:
                        logger.info(f"Process {proc.pid} ({proc.name()}) is the wrapper, already attempted kill.")
                        # If still running, kill_process_tree might have failed, try again? Or rely on its robustness.
                        if proc.is_running():
                            logger.warning(f"Wrapper {proc.pid} still running after initial kill attempt. Re-attempting kill.")
                            kill_process_tree(proc.pid)
                            killed_in_fallback = True
                        continue 

                    logger.info(f"Fallback: Found potentially orphaned agent process {proc.pid} ({proc.name()}) cmd: '{cmdline_str[:100]}...'. Attempting to kill.")
                    if kill_process_tree(proc.pid):
                        killed_in_fallback = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass # Process disappeared or not accessible
        except Exception as e_fallback:
            logger.warning(f"Error during fallback process scan for agent {agent_id}: {e_fallback}")
    
    if killed_in_fallback:
        logger.info(f"One or more processes related to agent {agent_id} were killed during fallback scan.")

    # Close the log file handle for the wrapper
    if wrapper_log_file_handle:
        try:
            wrapper_log_file_handle.close()
            logger.info(f"Closed wrapper log file for agent {agent_id}.")
        except Exception as e_close:
            logger.warning(f"Error closing wrapper log file for agent {agent_id}: {e_close}")

    # Clean up files: wrapper script, PID file, wrapper log
    # PID file should ideally be removed by the wrapper itself or kill_process_tree if it was for the wrapper
    for file_to_remove in [wrapper_script_path, pid_file, wrapper_log_path]:
        if file_to_remove and os.path.exists(file_to_remove):
            try:
                os.remove(file_to_remove)
                logger.info(f"Removed file: {file_to_remove}")
            except Exception as e:
                logger.warning(f"Could not remove file {file_to_remove}: {str(e)}")
        
    del running_agents[user_id]
    logger.info(f"Agent {agent_id} for user {user_id} stopped and removed from running list.")
    return {"status": "stopped", "user_id": user_id, "agent_id": agent_id}

@app.get("/agents")
async def list_agents():
    """List all running agents after pruning stale ones."""
    _prune_stale_agents() # Ensure list is fresh
    
    return {
        "agents": [
            {
                "user_id": uid,
                "agent_id": info.get("agent_id", "N/A"),
                "agent_type": info.get("agent_type", "N/A"),
                "port": info.get("port", 0),
                "running_time_seconds": round(time.time() - info.get("started_at", time.time()), 2),
                "pid_file": info.get("pid_file", "N/A"),
                "wrapper_log_path": info.get("wrapper_log_path", "N/A")
            }
            for uid, info in running_agents.items()
        ]
    }

async def periodic_cleanup_task():
    """Periodically clean up stale agent entries and leftover files."""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        logger.info("Running periodic cleanup task...")
        try:
            _prune_stale_agents() # Prunes running_agents and some files

            # More aggressive cleanup for orphaned files in AGENT_TRACKING_DIR
            # (e.g., if manager crashed before cleaning up)
            current_time = time.time()
            # Default max age: 1 day for general orphaned files, shorter for specific types if needed
            max_file_age_seconds = 24 * 60 * 60 
            
            for filename in os.listdir(AGENT_TRACKING_DIR):
                file_path = os.path.join(AGENT_TRACKING_DIR, filename)
                if os.path.isdir(file_path): # Skip directories
                    continue

                try:
                    file_mod_time = os.path.getmtime(file_path)
                    # Check if file is associated with any active agent
                    is_active_file = False
                    for agent_info in running_agents.values():
                        if file_path in [agent_info.get("script_path"), agent_info.get("pid_file"), agent_info.get("wrapper_log_path")]:
                            is_active_file = True
                            break
                    
                    if not is_active_file and (current_time - file_mod_time > max_file_age_seconds):
                        logger.info(f"Periodic cleanup: Removing old orphaned file: {file_path}")
                        os.remove(file_path)
                except FileNotFoundError: # File might be removed by another process/thread
                    pass 
                except Exception as e_cleanup:
                    logger.error(f"Error during periodic file cleanup for {file_path}: {e_cleanup}")
        except Exception as e_task:
            logger.error(f"Error in periodic_cleanup_task main loop: {str(e_task)}")

@app.on_event("startup")
async def startup_event():
    # Initial cleanup on startup
    logger.info("Performing startup cleanup...")
    _prune_stale_agents() 
    # Start periodic cleanup task
    asyncio.create_task(periodic_cleanup_task())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"Starting Agent Manager API on http://0.0.0.0:{port}")
    # Note: loop management for asyncio tasks is handled by uvicorn when running FastAPI app.
    # No need for manual loop.create_task here if using app.on_event("startup").
    uvicorn.run(app, host="0.0.0.0", port=port)