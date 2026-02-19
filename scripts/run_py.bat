@echo off
setlocal EnableExtensions EnableDelayedExpansion

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
  echo ERROR: Python not found: %PY%
  exit /b 1
)

REM Rebuild args from %2.. end so venv path never reaches python
set "ARGS="
shift
:collect
if "%~1"=="" goto run
set "ARGS=!ARGS! "%~1""
shift
goto collect

:run
REM If no args were provided after venv, just print python version
if "!ARGS!"=="" (
  "%PY%" -V
  exit /b %ERRORLEVEL%
)

REM Run python with rebuilt args
call "%PY%" !ARGS!
exit /b %ERRORLEVEL%
