@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1

set "REQUIREMENTS=requirements.txt"
if "%~1"=="" goto :args_done
if /I not "%~1"=="--test" goto :usage
set "REQUIREMENTS=requirements-test.txt"
:args_done
if not "%~2"=="" goto :usage

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :install

echo [Jack setup] Creating repository-local .venv...
where py >nul 2>nul
if not errorlevel 1 goto :create_with_py
where python >nul 2>nul
if not errorlevel 1 goto :create_with_python
goto :no_python

:create_with_py
py -3 -m venv ".venv"
if errorlevel 1 goto :venv_failed
goto :install

:create_with_python
python -m venv ".venv"
if errorlevel 1 goto :venv_failed

:install
if not exist "%VENV_PY%" goto :venv_failed
echo [Jack setup] Installing %REQUIREMENTS% into .venv...
"%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
if errorlevel 1 goto :install_failed

echo [Jack setup] Verifying runtime dependencies...
"%VENV_PY%" -c "import fastapi, uvicorn, httpx; print('Jack runtime dependencies available')"
if errorlevel 1 goto :verify_failed

echo.
echo [Jack setup] SUCCESS: repository-local .venv is ready.
echo [Jack setup] Launch Jack with start.bat.
if /I "%~1"=="--test" echo [Jack setup] Run tests with .venv\Scripts\python.exe -m pytest -q tests
exit /b 0

:usage
echo Usage: setup.bat [--test]
echo   --test also installs the regression-test dependencies.
exit /b 2

:no_python
echo [Jack setup] ERROR: Python 3 is required. Install Python 3 and rerun setup.bat.
exit /b 1

:venv_failed
echo [Jack setup] ERROR: Could not create .venv. Confirm Python 3 includes venv/ensurepip.
exit /b 1

:install_failed
echo [Jack setup] ERROR: Dependency installation failed. Check the pip error above.
exit /b 1

:verify_failed
echo [Jack setup] ERROR: Runtime dependencies cannot be imported from .venv.
exit /b 1
