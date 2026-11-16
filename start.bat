@echo off
setlocal
cd /d "%~dp0" || exit /b 1
title Jack Kernel

REM Preserve the accepted Agentic transaction configuration.
set "JACK_AGENTIC_TRANSACTION_LINKS=1"
set "JACK_AGENTIC_TASK_ANCHOR=0"

REM A fresh Git clone does NOT refresh Pi's installed global extension.
REM Synchronize Jack's exact origin-specific native edit guard on EVERY launch.
REM Pi must be restarted (or /reload used) if it was already running.
if not exist "%~dp0Pi\install-jack-kernel-extension.ps1" (
    echo ERROR: Jack's Pi extension installer is missing.
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Pi\install-jack-kernel-extension.ps1"
if errorlevel 1 (
    echo ERROR: Pi extension installation failed. Jack's native edit protection is not ready.
    exit /b 1
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
