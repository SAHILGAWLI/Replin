#!/usr/bin/env python3
"""
Dependency checker for Voice Agent System
This script verifies that all necessary dependencies are installed
and environment variables are configured.
"""

import sys
import os
import importlib
import subprocess
import platform
from pathlib import Path

# List of required modules
REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "dotenv",
    "llama_index",
    "openai",
    "livekit",
    "requests",
    "psutil"
]

# List of required environment variables
REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY"
]

# List of recommended environment variables
RECOMMENDED_ENV_VARS = [
    "STORAGE_PATH",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SIP_TRUNK_ID"
]

# List of required files
REQUIRED_FILES = [
    "document_upload.py",
    "agent_manager.py",
    "user_agent.py",
    "web-user.py",
    "run_agent.py",
    "web-agent-run.py",
    "requirements.txt",
    "render.yaml"
]

def check_modules():
    """Check if all required modules are installed"""
    print("\n🔍 Checking Python modules...")
    
    missing_modules = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
            print(f"✅ {module} is installed")
        except ImportError:
            missing_modules.append(module)
            print(f"❌ {module} is not installed")
    
    if missing_modules:
        print("\n⚠️ Missing modules. Install them with:")
        print(f"pip install {' '.join(missing_modules)}")
    else:
        print("\n✅ All required modules are installed!")
    
    return len(missing_modules) == 0

def check_env_vars():
    """Check if required environment variables are set"""
    print("\n🔍 Checking environment variables...")
    
    missing_required = []
    for var in REQUIRED_ENV_VARS:
        if var not in os.environ:
            missing_required.append(var)
            print(f"❌ {var} is not set (REQUIRED)")
        else:
            print(f"✅ {var} is set")
    
    missing_recommended = []
    for var in RECOMMENDED_ENV_VARS:
        if var not in os.environ:
            missing_recommended.append(var)
            print(f"⚠️ {var} is not set (recommended)")
        else:
            print(f"✅ {var} is set")
    
    if missing_required:
        print("\n⚠️ Missing required environment variables!")
        print("These must be set in Render environment variables.")
    
    if missing_recommended:
        print("\n⚠️ Missing recommended environment variables.")
        print("These should be set in Render environment variables.")
    
    return len(missing_required) == 0

def check_files():
    """Check if all required files exist"""
    print("\n🔍 Checking required files...")
    
    missing_files = []
    for file in REQUIRED_FILES:
        if not Path(file).exists():
            missing_files.append(file)
            print(f"❌ {file} not found")
        else:
            print(f"✅ {file} exists")
    
    if missing_files:
        print("\n⚠️ Missing required files!")
    else:
        print("\n✅ All required files exist!")
    
    return len(missing_files) == 0

def check_platform_compatibility():
    """Check platform compatibility"""
    print("\n🔍 Checking platform compatibility...")
    
    system = platform.system()
    print(f"Current platform: {system}")
    
    if system == "Windows":
        print("⚠️ Your code will run on Windows locally, but Render uses Linux.")
        print("⚠️ Ensure there are no Windows-specific commands in your code.")
        
        # Check for Windows-specific commands in agent_manager.py
        if Path("agent_manager.py").exists():
            with open("agent_manager.py", "r") as f:
                content = f.read()
                windows_commands = []
                
                if "taskkill" in content:
                    windows_commands.append("taskkill")
                if "CREATE_NEW_CONSOLE" in content:
                    windows_commands.append("CREATE_NEW_CONSOLE")
                    
                # Only flag CREATE_NEW_PROCESS_GROUP if not safely used with try/except
                if "CREATE_NEW_PROCESS_GROUP" in content and "try:" not in content:
                    windows_commands.append("CREATE_NEW_PROCESS_GROUP (without try/except)")
                
                if "DETACHED_PROCESS" in content:
                    windows_commands.append("DETACHED_PROCESS")
                if "cmd.exe" in content:
                    windows_commands.append("cmd.exe")
                if ".bat" in content:
                    windows_commands.append(".bat files")
                
                if windows_commands:
                    print("❌ agent_manager.py contains Windows-specific commands:")
                    for cmd in windows_commands:
                        print(f"   - {cmd}")
                    print("   These will not work on Render (Linux environment)")
                    return False
    
    print("✅ Platform compatibility check passed")
    return True

def check_render_deployment_readiness():
    """Check if the application is ready for Render deployment"""
    print("\n🔍 Checking Render deployment readiness...")
    
    # Check for render.yaml
    if not Path("render.yaml").exists():
        print("❌ render.yaml not found - this is needed for Blueprint deployment")
        ready = False
    else:
        print("✅ render.yaml exists")
        ready = True
    
    # Check for PORT handling in main scripts
    if Path("document_upload.py").exists():
        with open("document_upload.py", "r") as f:
            content = f.read()
            if "os.environ.get(\"PORT\"" not in content:
                print("❌ document_upload.py doesn't handle PORT environment variable")
                ready = False
            else:
                print("✅ document_upload.py handles PORT environment variable")
    
    if Path("agent_manager.py").exists():
        with open("agent_manager.py", "r") as f:
            content = f.read()
            if "os.environ.get(\"PORT\"" not in content:
                print("❌ agent_manager.py doesn't handle PORT environment variable")
                ready = False
            else:
                print("✅ agent_manager.py handles PORT environment variable")
    
    return ready

def main():
    """Main function"""
    print("🚀 Voice Agent System Deployment Checker 🚀")
    
    modules_ok = check_modules()
    env_vars_ok = check_env_vars()
    files_ok = check_files()
    platform_ok = check_platform_compatibility()
    render_ready = check_render_deployment_readiness()
    
    print("\n==== Summary ====")
    print(f"✅ Python modules: {'OK' if modules_ok else 'MISSING SOME'}")
    print(f"✅ Environment variables: {'OK' if env_vars_ok else 'MISSING SOME'}")
    print(f"✅ Required files: {'OK' if files_ok else 'MISSING SOME'}")
    print(f"✅ Platform compatibility: {'OK' if platform_ok else 'ISSUES FOUND'}")
    print(f"✅ Render deployment readiness: {'OK' if render_ready else 'ISSUES FOUND'}")
    
    if modules_ok and env_vars_ok and files_ok and platform_ok and render_ready:
        print("\n🎉 All checks passed! Your application is ready for deployment to Render.")
    else:
        print("\n⚠️ Some checks failed. Address the issues before deploying to Render.")
    
    return 0 if (modules_ok and env_vars_ok and files_ok and platform_ok and render_ready) else 1

if __name__ == "__main__":
    sys.exit(main()) 