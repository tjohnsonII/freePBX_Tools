@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "ATTACH_PORT="
set "ATTACH_HOST=127.0.0.1"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--attach" (
  set "ATTACH_PORT=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--attach-host" (
  set "ATTACH_HOST=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--help" goto usage
echo [WARN] Unknown option: %~1
shift
goto parse_args

:usage
echo Usage: scripts\doctor_cmd.bat [--attach PORT] [--attach-host HOST]
echo.
echo Checks:
echo   - Edge executable path
echo   - Edge debugger reachability when --attach is provided
echo   - ticket-ui package.json exists
echo   - Python dependencies import check
exit /b 0

:args_done
set "HAS_FAILURE="
set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>nul && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo [FAIL] Python not found in PATH.
  echo [FIX ] Install Python 3 and ensure py -3 or python is available.
  exit /b 1
)

echo [INFO] Using Python: %PYTHON_CMD%

%PYTHON_CMD% -c "import os,sys,pathlib;c=[];e=os.environ.get('EDGE_PATH') or os.environ.get('EDGE_BINARY_PATH');c+=[e] if e else [];pf86=os.environ.get('ProgramFiles(x86)');pf=os.environ.get('ProgramFiles');c+=[str(pathlib.Path(pf86)/'Microsoft'/'Edge'/'Application'/'msedge.exe')] if pf86 else [];c+=[str(pathlib.Path(pf)/'Microsoft'/'Edge'/'Application'/'msedge.exe')] if pf else [];f=next((p for p in c if p and os.path.exists(p)),None);print('[ OK ] Edge executable: '+f) if f else (print('[FAIL] Edge executable not found.'),print('[FIX ] Set EDGE_PATH to msedge.exe location or install Microsoft Edge.'),sys.exit(1))"
if errorlevel 1 set "HAS_FAILURE=1"

if defined ATTACH_PORT (
  %PYTHON_CMD% -c "import socket;h=r'%ATTACH_HOST%';p=int(r'%ATTACH_PORT%');socket.create_connection((h,p),timeout=2.0).close();print(f'[ OK ] Edge debugger reachable at {h}:{p}')"
  if errorlevel 1 (
    echo [FAIL] Edge debugger %ATTACH_HOST%:%ATTACH_PORT% is not reachable or --attach is invalid.
    echo [FIX ] Launch Edge with --remote-debugging-port=%ATTACH_PORT% and use a numeric --attach value.
    set "HAS_FAILURE=1"
  )
) else (
  echo [INFO] Attach check skipped. Pass --attach PORT to validate debugger connectivity.
)

if exist "%REPO_ROOT%\webscraper\ticket-ui\package.json" (
  echo [ OK ] ticket-ui package.json: %REPO_ROOT%\webscraper\ticket-ui\package.json
) else (
  echo [FAIL] ticket-ui package.json missing at %REPO_ROOT%\webscraper\ticket-ui\package.json
  echo [FIX ] Restore package.json then run: cd webscraper\ticket-ui ^&^& npm install ^&^& npm run dev
  set "HAS_FAILURE=1"
)

%PYTHON_CMD% -c "import importlib.util,sys;m=[x for x in ['selenium','bs4','requests'] if importlib.util.find_spec(x) is None];print('[ OK ] Python dependency probe passed (selenium, bs4, requests).') if not m else (print('[FAIL] Missing Python deps: '+', '.join(m)),print('[FIX ] Run: pip install -r webscraper/requirements.txt'),sys.exit(1))"
if errorlevel 1 set "HAS_FAILURE=1"

if defined HAS_FAILURE (
  echo [DONE] Doctor completed with failures.
  exit /b 1
)

echo [DONE] Doctor checks passed.
exit /b 0
