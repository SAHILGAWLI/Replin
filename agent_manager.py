import os
import time
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
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent-manager")

# Detect operating system
IS_WINDOWS = platform.system() == "Windows"
logger.info(f"Detected platform: {platform.system()}")

# --- CONFIGURATION ---
AGENT_MANAGER_DIR = Path(__file__).resolve().parent
# Path to the UNIFIED agent_runner.py script
PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT = str(AGENT_MANAGER_DIR / "agent_runner.py") # <--- ENSURE THIS IS CORRECT

# Directory where agent_runner.py and other agent scripts reside, used for CWD
PROJECT_ROOT_FOR_AGENTS_CWD = str(AGENT_MANAGER_DIR)
# If agent_manager.py is in a subdir like "manager/", then:
# PROJECT_ROOT_FOR_AGENTS_CWD = str(AGENT_MANAGER_DIR.parent)

AGENT_TRACKING_DIR = Path(PROJECT_ROOT_FOR_AGENTS_CWD) / "agent_tracking"
os.makedirs(AGENT_TRACKING_DIR, exist_ok=True)
# --- END CONFIGURATION ---

app = FastAPI(title="Voice Agent Manager")

allowed_origins = [
    "https://replin.vercel.app",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

running_agents: Dict[str, Dict[str, Any]] = {}

class AgentStartRequest(BaseModel):
    user_id: str
    agent_type: str = Field(default="web", examples=["web", "dialer"],
                            description="Type of agent to start, determines which core script (web-user or user-agent) is used by agent_runner.py.")

def generate_internal_agent_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# ... (kill_process_tree and _prune_stale_agents functions remain the same as the last full version I provided) ...
# For brevity, I'll skip pasting them again here, assume they are correct.
# Ensure kill_process_tree and _prune_stale_agents are copied from the previous full agent_manager.py
def kill_process_tree(pid_to_kill: int, process_name_for_log: str = "Process"):
    logger.info(f"Attempting to kill process tree for {process_name_for_log} (PID: {pid_to_kill})")
    try:
        parent = psutil.Process(pid_to_kill)
        logger.info(f"Found parent process: {parent.name()} (PID: {pid_to_kill}) for {process_name_for_log}")

        if not IS_WINDOWS and hasattr(os, "killpg") and hasattr(os, "getpgid"):
            try:
                pgid = os.getpgid(pid_to_kill)
                if pid_to_kill == pgid:
                    logger.info(f"Unix: {process_name_for_log} (PID {pid_to_kill}) is a group leader (PGID: {pgid}). Attempting SIGTERM on process group.")
                    os.killpg(pgid, signal.SIGTERM)
                    gone, alive = psutil.wait_procs([parent], timeout=0.5)
                    if not alive:
                        logger.info(f"Unix: Process group {pgid} for {process_name_for_log} terminated by SIGTERM.")
                        return True
                    else:
                        logger.info(f"Unix: Process group {pgid} for {process_name_for_log} did not terminate with SIGTERM. Attempting SIGKILL.")
                        os.killpg(pgid, signal.SIGKILL)
                        gone, alive = psutil.wait_procs([parent], timeout=0.2)
                        if not alive:
                            logger.info(f"Unix: Process group {pgid} for {process_name_for_log} terminated by SIGKILL.")
                            return True
                        else:
                            logger.warning(f"Unix: Failed to kill process group {pgid} for {process_name_for_log}. Falling back.")
            except ProcessLookupError:
                 logger.info(f"Unix: Process {pid_to_kill} for {process_name_for_log} not found during killpg attempt (likely already gone).")
                 return True
            except Exception as e_killpg:
                logger.warning(f"Unix: Error using killpg for {process_name_for_log} (PID {pid_to_kill}, PGID {pgid if 'pgid' in locals() else 'unknown'}): {e_killpg}. Falling back.")

        children = parent.children(recursive=True)
        child_pids = [child.pid for child in children]
        if children:
            logger.info(f"Found children for {process_name_for_log} (PID {pid_to_kill}) via psutil: {child_pids}")

        for child_pid in child_pids:
            try:
                child_proc = psutil.Process(child_pid)
                logger.info(f"Terminating child PID: {child_proc.pid} ({child_proc.name()}) of {process_name_for_log}")
                child_proc.terminate()
            except psutil.NoSuchProcess:
                logger.info(f"Child PID: {child_pid} of {process_name_for_log} already gone.")
            except Exception as e:
                logger.warning(f"Error terminating child PID {child_pid} of {process_name_for_log}: {e}")
        
        if children:
            gone, still_alive = psutil.wait_procs(children, timeout=1)
            for child_proc in still_alive:
                try:
                    logger.info(f"Force killing child PID: {child_proc.pid} ({child_proc.name()}) of {process_name_for_log}")
                    child_proc.kill()
                except psutil.NoSuchProcess: pass
                except Exception as e: logger.warning(f"Error force killing child PID {child_proc.pid} of {process_name_for_log}: {e}")
        
        logger.info(f"Terminating parent {process_name_for_log} (PID: {pid_to_kill})")
        parent.terminate()
        try: parent.wait(timeout=1)
        except psutil.TimeoutExpired:
            logger.info(f"Parent {process_name_for_log} (PID: {pid_to_kill}) did not terminate in 1s, force killing.")
            parent.kill()
            try: parent.wait(timeout=1)
            except psutil.TimeoutExpired: logger.error(f"CRITICAL: Failed to confirm kill of {process_name_for_log} (PID: {pid_to_kill}) after SIGKILL.")
            except psutil.NoSuchProcess: logger.info(f"Parent {process_name_for_log} (PID: {pid_to_kill}) gone after SIGKILL.")

        if parent.is_running(): logger.error(f"CRITICAL: {process_name_for_log} (PID: {pid_to_kill}) still running after all attempts.")
        else: logger.info(f"{process_name_for_log} (PID: {pid_to_kill}) successfully terminated.")
        return not parent.is_running()

    except psutil.NoSuchProcess:
        logger.info(f"{process_name_for_log} (PID {pid_to_kill}) not found, likely already terminated.")
        return True
    except Exception as e:
        logger.error(f"Error in kill_process_tree for {process_name_for_log} (PID {pid_to_kill}): {str(e)}", exc_info=True)
        return False

def _prune_stale_agents():
    pruned_count = 0
    for user_id_iter in list(running_agents.keys()):
        agent_info_iter = running_agents.get(user_id_iter)
        if not agent_info_iter: continue

        process_handle: Optional[subprocess.Popen] = agent_info_iter.get("process_handle")
        log_file_handle = agent_info_iter.get("log_file_handle")
        log_path = agent_info_iter.get("log_path")
        internal_agent_id = agent_info_iter.get("internal_agent_id", "N/A")

        process_alive = False
        if process_handle and process_handle.poll() is None:
            process_alive = True
        elif process_handle: # Process has exited
            logger.info(f"Agent for user {user_id_iter} (ID: {internal_agent_id}, PID: {process_handle.pid if hasattr(process_handle, 'pid') else 'N/A'}) has exited with code {process_handle.returncode}.")
        else: # No process handle
            logger.warning(f"Agent entry for user {user_id_iter} (ID: {internal_agent_id}) has no process handle. Pruning.")

        if not process_alive:
            logger.info(f"Pruning stale agent entry for user {user_id_iter} (ID: {internal_agent_id}).")
            if log_file_handle and not log_file_handle.closed:
                try: log_file_handle.close()
                except Exception as e_close: logger.warning(f"Error closing log file {log_path} for stale agent {user_id_iter}: {e_close}")
            
            if user_id_iter in running_agents: del running_agents[user_id_iter]
            pruned_count += 1
    if pruned_count > 0: logger.info(f"Pruned {pruned_count} stale agent(s). Current running: {len(running_agents)}")


@app.post("/start-agent")
async def start_agent_endpoint(request: AgentStartRequest):
    _prune_stale_agents()
    user_id = request.user_id
    agent_type = request.agent_type # This determines the --core-script argument
    internal_agent_id = generate_internal_agent_id()

    if user_id in running_agents:
        agent_info = running_agents[user_id]
        current_pid = agent_info.get('process_handle').pid if agent_info.get('process_handle') else 'N/A'
        logger.warning(f"Attempt to start agent for user {user_id}, but an agent (ID: {agent_info.get('internal_agent_id')}, PID: {current_pid}) is already running.")
        raise HTTPException(status_code=409, detail=f"An agent is already running for user {user_id}.")

    # Determine the --core-script argument for agent_runner.py
    core_script_arg_for_runner: str
    if agent_type == "web":
        core_script_arg_for_runner = "web-user"
    elif agent_type == "dialer":
        core_script_arg_for_runner = "user-agent"
    else:
        logger.error(f"Invalid agent_type '{agent_type}' requested for user {user_id}.")
        raise HTTPException(status_code=400, detail=f"Invalid agent_type: {agent_type}. Must be 'web' or 'dialer'.")
        
    if not Path(PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT).is_file():
        logger.error(f"CRITICAL: Unified agent runner script configured path '{PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT}' not found or is not a file.")
        raise HTTPException(status_code=500, detail="Unified agent runner script misconfiguration or not found.")

    python_executable_for_runner = sys.executable
    cmd = [
        python_executable_for_runner,
        PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT, # Call the single agent_runner.py
        "--user-id", user_id,
        "--core-script", core_script_arg_for_runner # Tell agent_runner which core logic to use
    ]

    kwargs = {}
    kwargs["cwd"] = PROJECT_ROOT_FOR_AGENTS_CWD
    logger.info(f"Setting CWD for agent runner to: {PROJECT_ROOT_FOR_AGENTS_CWD}")

    agent_log_path = AGENT_TRACKING_DIR / f"agent_{user_id}_{agent_type}_{internal_agent_id}.log"
    try:
        agent_log_file = open(agent_log_path, "wb")
        kwargs["stdout"] = agent_log_file
        kwargs["stderr"] = agent_log_file
    except Exception as e_log:
        logger.error(f"Failed to open log file {agent_log_path} for agent {user_id} ({agent_type}): {e_log}")
        raise HTTPException(status_code=500, detail=f"Failed to prepare agent logging: {e_log}")

    if IS_WINDOWS: kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        if hasattr(os, 'setpgrp'): kwargs["preexec_fn"] = os.setpgrp

    try:
        logger.info(f"Starting unified agent runner for user {user_id} (Type: {agent_type}, Internal ID: {internal_agent_id}) with command: {' '.join(cmd)}. Logs at: {agent_log_path}")
        process_handle = subprocess.Popen(cmd, **kwargs)

        await asyncio.sleep(0.7)
        if process_handle.poll() is not None:
            if not agent_log_file.closed: agent_log_file.close()
            logger.error(f"Unified agent runner for user {user_id} (Type: {agent_type}, ID: {internal_agent_id}) failed to start or exited immediately (exit code {process_handle.returncode}). Check logs: {agent_log_path}")
            raise HTTPException(status_code=500, detail=f"Agent failed to start. Exit code: {process_handle.returncode}. See manager and agent logs.")

        running_agents[user_id] = {
            "internal_agent_id": internal_agent_id,
            "process_handle": process_handle,
            "pid": process_handle.pid,
            "log_path": str(agent_log_path),
            "log_file_handle": agent_log_file,
            "started_at": time.time(),
            "agent_type": agent_type # agent_type determines --core-script for runner
        }
        logger.info(f"{agent_type} agent (via unified runner) started for user {user_id} (Internal ID: {internal_agent_id}, PID: {process_handle.pid}).")
        return {"status": "started", "user_id": user_id, "agent_type": agent_type, "internal_agent_id": internal_agent_id, "pid": process_handle.pid}

    except Exception as e:
        logger.error(f"Error starting unified agent runner for user {user_id} (Type: {agent_type}, Internal ID: {internal_agent_id}): {str(e)}", exc_info=True)
        if 'agent_log_file' in locals() and agent_log_file and not agent_log_file.closed: agent_log_file.close()
        if 'process_handle' in locals() and process_handle and process_handle.poll() is None:
            try: process_handle.terminate(); process_handle.wait(timeout=0.5)
            except: pass
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")

# ... (stop_agent_endpoint, list_agents_endpoint, periodic_cleanup_task, startup_event, shutdown_event remain largely the same as the last full version)
# Ensure they use agent_type from running_agents[user_id] for logging if needed.
@app.post("/stop-agent/{user_id}")
async def stop_agent_endpoint(user_id: str):
    _prune_stale_agents()
    if user_id not in running_agents:
        logger.warning(f"Stop request for user {user_id}, but no active agent found.")
        raise HTTPException(status_code=404, detail=f"No active agent found for user {user_id} to stop.")

    agent_info = running_agents[user_id]
    internal_agent_id = agent_info["internal_agent_id"]
    pid_to_kill = agent_info.get("pid")
    log_file_handle = agent_info.get("log_file_handle")
    log_path = agent_info.get("log_path")
    agent_type = agent_info.get("agent_type", "UnknownType")


    logger.info(f"Stopping {agent_type} agent for user {user_id} (Internal ID: {internal_agent_id}, PID: {pid_to_kill}).")
    if pid_to_kill :
        process_handle: Optional[subprocess.Popen] = agent_info.get("process_handle")
        if process_handle and process_handle.poll() is None:
            kill_process_tree(pid_to_kill, process_name_for_log=f"Agent {internal_agent_id} ({agent_type}) for user {user_id}")
        elif process_handle:
             logger.info(f"{agent_type} agent process for user {user_id} (PID: {pid_to_kill}) already exited (code: {process_handle.returncode}).")
        else:
            logger.warning(f"Agent for user {user_id} has PID {pid_to_kill} but no process_handle. Attempting kill by PID.")
            kill_process_tree(pid_to_kill, process_name_for_log=f"Agent {internal_agent_id} ({agent_type}, PID only) for user {user_id}")
    else:
        logger.warning(f"No valid PID found to stop for {agent_type} agent of user {user_id}.")

    if log_file_handle and not log_file_handle.closed:
        try: log_file_handle.close(); logger.info(f"Closed agent log file: {log_path}")
        except Exception as e_close: logger.warning(f"Error closing agent log file {log_path}: {e_close}")

    if user_id in running_agents: del running_agents[user_id]
    logger.info(f"{agent_type} agent for user {user_id} (Internal ID: {internal_agent_id}) removed from running list.")
    return {"status": "stopped", "user_id": user_id, "internal_agent_id": internal_agent_id}

@app.get("/agents")
async def list_agents_endpoint():
    _prune_stale_agents()
    agent_list = []
    for user_id, info in running_agents.items():
        process_handle: Optional[subprocess.Popen] = info.get("process_handle")
        pid = info.get("pid")
        status = "unknown"
        if process_handle: status = "running" if process_handle.poll() is None else f"exited({process_handle.returncode})"
        elif pid and psutil.pid_exists(pid): status = "running (handle lost, PID exists)"
        elif pid: status = "exited (PID not found)"

        agent_list.append({
            "user_id": user_id,
            "internal_agent_id": info.get("internal_agent_id", "N/A"),
            "agent_type": info.get("agent_type", "N/A"),
            "pid": pid,
            "status": status,
            "running_time_seconds": round(time.time() - info.get("started_at", time.time()), 2) if info.get("started_at") else -1,
            "log_path": info.get("log_path", "N/A")
        })
    return {"agents": agent_list, "count": len(agent_list)}

async def periodic_cleanup_task():
    while True:
        await asyncio.sleep(180)
        logger.debug("Running periodic agent cleanup task...")
        try: _prune_stale_agents()
        except Exception as e_task: logger.error(f"Error in periodic_cleanup_task: {str(e_task)}", exc_info=True)

@app.on_event("startup")
async def startup_event():
    logger.info(f"Agent Manager starting up. Main script: {__file__}")
    logger.info(f"Python executable for manager: {sys.executable}")
    logger.info(f"Current working directory for manager: {os.getcwd()}")
    logger.info(f"AGENT_MANAGER_DIR: {AGENT_MANAGER_DIR}")
    logger.info(f"PROJECT_ROOT_FOR_AGENTS_CWD: {PROJECT_ROOT_FOR_AGENTS_CWD}")
    logger.info(f"PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT: {PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT}")

    logger.info("Performing initial stale agent check...")
    _prune_stale_agents()
    asyncio.create_task(periodic_cleanup_task())
    logger.info("Periodic cleanup task scheduled.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Agent Manager shutting down. Stopping all running agents...")
    user_ids_to_stop = list(running_agents.keys())
    for user_id in user_ids_to_stop:
        logger.info(f"Attempting to stop agent for user {user_id} during shutdown...")
        agent_info = running_agents.get(user_id)
        if agent_info:
            pid_to_kill = agent_info.get("pid")
            internal_agent_id = agent_info.get("internal_agent_id", "N/A")
            log_file_handle = agent_info.get("log_file_handle")
            agent_type = agent_info.get("agent_type", "UnknownType")
            if pid_to_kill: kill_process_tree(pid_to_kill, process_name_for_log=f"Agent {internal_agent_id} ({agent_type}, shutdown) for user {user_id}")
            if log_file_handle and not log_file_handle.closed:
                try: log_file_handle.close()
                except: pass
            if user_id in running_agents: del running_agents[user_id]
    logger.info("All tracked agents have been requested to stop.")


if __name__ == "__main__":
    if not Path(PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT).is_file():
        logger.critical(f"FATAL: Unified agent runner script '{PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT}' not found or not a file. Please configure correctly.")
        sys.exit(1)
    else:
        logger.info(f"Using unified agent_runner.py from: {Path(PATH_TO_UNIFIED_AGENT_RUNNER_SCRIPT).resolve()}")

    if not Path(PROJECT_ROOT_FOR_AGENTS_CWD).is_dir():
        logger.critical(f"FATAL: Configured PROJECT_ROOT_FOR_AGENTS_CWD '{PROJECT_ROOT_FOR_AGENTS_CWD}' is not a valid directory. Exiting.")
        sys.exit(1)
    logger.info(f"Verified PROJECT_ROOT_FOR_AGENTS_CWD: {Path(PROJECT_ROOT_FOR_AGENTS_CWD).resolve()}")

    port = int(os.environ.get("PORT", 8001))
    logger.info(f"Starting Agent Manager API on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)