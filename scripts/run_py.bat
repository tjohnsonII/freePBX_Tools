@echo off
setlocal EnableExtensions

REM Resolve repo root (parent of this scripts directory)
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

REM First arg = venv path relative to repo root
set "VENV_REL=%~1"
if "%VENV_REL%"=="" (
  echo ERROR: Missing venv path argument.
  exit /b 1
)

set "PY=%REPO_ROOT%\%VENV_REL%\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python not found: "%PY%"
  exit /b 1
)

echo [run_py] Using Python: "%PY%"

shift
if "%~1"=="" (
  "%PY%" -V
  exit /b %ERRORLEVEL%
)

"%PY%" %*
exit /b %ERRORLEVEL%
