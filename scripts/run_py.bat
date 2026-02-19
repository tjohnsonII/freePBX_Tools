@echo off
setlocal

REM Usage: run_py.bat <venv-folder> <python args...>

set "VENV=%~1"
if "%VENV%"=="" (
  echo ERROR: Missing venv folder.
  exit /b 1
)

set "PY=%CD%\%VENV%\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python not found: %PY%
  exit /b 1
)

shift
"%PY%" %*
exit /b %ERRORLEVEL%
