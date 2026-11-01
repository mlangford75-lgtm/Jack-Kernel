@echo off
setlocal
cd /d "%~dp0"
title Jack Kernel
REM Restore branch only: enable host-linked memory in the normal launcher.
REM Does not modify reasoning, Preserve Thinking, tool policy, or cache config.
set "JACK_AGENTIC_TRANSACTION_LINKS=1"
set "JACK_AGENTIC_TASK_ANCHOR=0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "jack_secure_entrypoint.py"
    goto :done
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 "jack_secure_entrypoint.py"
    goto :done
)

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "jack_secure_entrypoint.py"
    goto :done
)

echo.
echo Jack Kernel requires Python 3.
echo Install Python 3, then install dependencies with:
echo   py -3 -m pip install -r requirements.txt
echo.
pause
exit /b 1

:done
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
echo.
echo Jack Kernel exited with error code %RC%.
echo If dependencies are missing, run:
echo   py -3 -m pip install -r requirements.txt
echo.
pause
exit /b %RC%
