@echo off
setlocal
cd /d "%~dp0" || exit /b 1

REM Run validation with the same interpreter/dependencies used by start.bat.
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Jack's virtual environment is not installed.
    echo Run setup.bat once from this folder, then run run-tests.bat.
    exit /b 1
)

".venv\Scripts\python.exe" -m pytest -q %*
exit /b %ERRORLEVEL%
