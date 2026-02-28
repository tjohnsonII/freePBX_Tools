@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Resolve repo root (parent of this scripts directory)
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

REM First arg = venv path relative to repo root
if "%~1"=="" (
  echo ERROR: Missing venv path argument.
  exit /b 1
)

set "VENV_REL=%~1"

set "PY=%REPO_ROOT%\%VENV_REL%\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python not found: "%PY%"
  exit /b 1
)

echo [run_py] Using Python: "%PY%"

REM If no args (beyond venv) remain, just print python version
if "%~2"=="" (
  "%PY%" -V
  exit /b %ERRORLEVEL%
)

REM Run python with remaining args ONLY (skip the venv arg entirely)
"%PY%" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
