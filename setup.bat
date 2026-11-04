@echo off
setlocal
cd /d "%~dp0" || exit /b 1

REM First-clone setup: dependencies belong to Jack's own virtual environment.
REM Never install into the system Python or relocate the user's HOME/APPDATA.
if not exist ".venv\Scripts\python.exe" (
    echo Creating Jack's isolated Python environment in .venv...
    py -3 -m venv ".venv" >nul 2>nul
    if errorlevel 1 (
        python -m venv ".venv"
        if errorlevel 1 (
            echo ERROR: Python 3 with venv support is required.
            echo Install Python 3, then rerun setup.bat.
            exit /b 1
        )
    )
)

set "JACK_PYTHON=.venv\Scripts\python.exe"
"%JACK_PYTHON%" -m pip --version >nul 2>nul
if errorlevel 1 (
    "%JACK_PYTHON%" -m ensurepip --upgrade
    if errorlevel 1 exit /b 1
)

echo Installing pinned Jack runtime and test dependencies...
"%JACK_PYTHON%" -m pip install -r requirements-test.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed; check the output above.
    exit /b 1
)

"%JACK_PYTHON%" -c "import sys, fastapi, uvicorn, httpx, pytest; print('Jack environment:', sys.executable); print('httpx:', httpx.__version__); print('pytest:', pytest.__version__)"
if errorlevel 1 (
    echo ERROR: Jack's virtual environment is missing a required dependency.
    exit /b 1
)

echo.
echo Jack is ready. Run run-tests.bat to validate, or start.bat to launch.
exit /b 0
