@echo off
setlocal
cd /d "%~dp0"
title Jack Kernel

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "jack_responses_compat.py"
    goto :done
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 "jack_responses_compat.py"
    goto :done
)

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "jack_responses_compat.py"
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
