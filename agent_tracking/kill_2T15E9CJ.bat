@echo off
setlocal enabledelayedexpansion
echo KILL SCRIPT FOR AGENT 2T15E9CJ
echo Current server PID: 14200 (will be protected)
echo Checking PID file...
if exist "C:\Users\User\Repnix\agent_tracking\agent_2T15E9CJ.pid" (
  for /f "tokens=*" %%p in ('type "C:\Users\User\Repnix\agent_tracking\agent_2T15E9CJ.pid"') do (
    echo Found PID: %%p
    taskkill /F /PID %%p /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed process %%p
    ) else (
      echo Failed to kill process %%p, error !errorlevel!
    )
  )
)

echo Killing user_agent.py processes...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%user_agent.py%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing !pid! running user_agent.py
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing run_agent.py processes...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%run_agent.py%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing !pid! running run_agent.py
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing web-agent-run.py processes...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%web-agent-run.py%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing !pid! running web-agent-run.py
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing web-user.py processes...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%web-user.py%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing !pid! running web-user.py
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing processes with agent ID 2T15E9CJ...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%2T15E9CJ%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing agent ID process: !pid!
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing processes with user ID test_user...
for /f "usebackq tokens=1" %%p in (`wmic process where "name='python.exe' and commandline like '%test_user%' and not commandline like '%--port 8000%' and not commandline like '%--port 8001%'" get processid /format:value ^| find "ProcessId"`) do (
  set pline=%%p
  set pid=!pline:ProcessId=!
  if not "!pid!" == ""{current_pid}" (
    echo Killing user ID process: !pid!
    taskkill /F /PID !pid! /T 2>nul
    if !errorlevel! equ 0 (
      echo Successfully killed !pid!
    ) else (
      echo Failed to kill !pid!, error !errorlevel!
    )
  ) else (
    echo Skipping server process !pid!
  )
)

echo Killing CMD windows with agent ID 2T15E9CJ...
taskkill /F /FI "WINDOWTITLE eq *2T15E9CJ*" /T
if %errorlevel% equ 0 (
  echo Successfully killed processes by window title
) else (
  echo No processes found by window title, or error %errorlevel%
)

echo Cleaning up files...
if exist "C:\Users\User\Repnix\agent_tracking\agent_2T15E9CJ.pid" del "C:\Users\User\Repnix\agent_tracking\agent_2T15E9CJ.pid" 2>nul
if exist "C:\Users\User\Repnix\agent_tracking\wrapper_2T15E9CJ.py" del "C:\Users\User\Repnix\agent_tracking\wrapper_2T15E9CJ.py" 2>nul
echo Agent termination complete.
timeout /t 2
del "%~f0"
