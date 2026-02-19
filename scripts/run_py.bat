@echo off
setlocal

REM Usage:
REM   run_py.bat <venv-path-relative-to-repo-root> <python args...>
REM Example:
REM   run_py.bat .venv-webscraper -m debugpy --listen 5679 --wait-for-client webscraper\dev_server.py
REM   run_py.bat freepbx-deploy-backend\.venv-backend -m debugpy --listen 5678 --wait-for-client -m uvicorn freepbx_deploy_backend.main:app --reload --host 127.0.0.1 --port 8002

REM Resolve repo root = parent folder of this scripts directory
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "VENV_REL=%~1"
if "%VENV_REL%"=="" (
  echo ERROR: Missing venv path argument.
  exit /b 1
)

set "PY=%REPO_ROOT%\%VENV_REL%\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python not found: %PY%
  exit /b 1
)

shift
"%PY%" %*
exit /b %ERRORLEVEL%
