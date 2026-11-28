@echo off
setlocal
cd /d "%~dp0" || exit /b 1
title Jack Kernel

REM Preserve the accepted Agentic transaction configuration.
set "JACK_AGENTIC_TRANSACTION_LINKS=1"
set "JACK_AGENTIC_TASK_ANCHOR=0"

REM A fresh Git clone does NOT refresh Pi's installed global extension.
REM Synchronize the Pi extension when available. Independent clients do not
REM require a global Pi installation. Never advertise a failed sync as ready.
REM Pi must be restarted (or /reload used) if it was already running.
if not exist "%~dp0Pi\install-jack-kernel-extension.ps1" (
    echo WARNING: Pi extension installer is missing. Use an independent client until Pi is repaired.
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Pi\install-jack-kernel-extension.ps1"
    if errorlevel 1 (
        echo WARNING: Pi extension synchronization failed. Use an independent client until Pi is repaired.
    )
)

REM A clean clone has no dependencies yet. Bootstrap once into .venv.
REM Do not silently fall back to an unrelated global/user Python installation.
if not exist ".venv\Scripts\python.exe" (
    echo First launch: preparing Jack's isolated Python environment...
    call "%~dp0setup.bat"
    if errorlevel 1 (
        echo ERROR: Initial setup failed. Fix the reported issue and rerun setup.bat.
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn, httpx" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Jack's .venv is incomplete. Run setup.bat to repair it.
    exit /b 1
)

".venv\Scripts\python.exe" "jack_secure_entrypoint.py"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
echo.
echo Jack Kernel exited with error code %RC%.
exit /b %RC%
