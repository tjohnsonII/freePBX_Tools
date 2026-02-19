@echo off
setlocal

REM Usage: run_py.bat <venv-folder> <python args...>

set "VENV_REL=%~1"
if "%VENV_REL%"=="" (
  echo ERROR: Missing venv folder.
  exit /b 1
)

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "PY=%REPO_ROOT%\%VENV_REL%\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python not found: %PY%
  exit /b 1
)

shift
"%PY%" %*
exit /b %ERRORLEVEL%
