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

REM Try self-heal bootstrap for registry-managed envs before launching python.
set "HOST_PY="
where py >nul 2>nul && set "HOST_PY=py -3"
if not defined HOST_PY (
  where python >nul 2>nul && set "HOST_PY=python"
)

if defined HOST_PY (
  %HOST_PY% "%REPO_ROOT%\scripts\bootstrap_venv.py" --venv "%VENV_REL%" --auto-from-registry --quiet
  if errorlevel 1 (
    echo ERROR: Bootstrap failed for "%VENV_REL%".
    exit /b 1
  )
) else (
  echo [run_py] WARN: No host python found for bootstrap check; continuing with existing venv lookup.
)

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
shift
"%PY%" %*
exit /b %ERRORLEVEL%
