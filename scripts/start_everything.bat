@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

echo ==================================================
echo  freePBX Tools - Start Everything + CLI
echo ==================================================
echo [NOTE] Dev ports may already be in use. This script does not stop existing processes.
echo.

set "LAUNCH_FAILED=0"

set "TRACE_DIR=%ROOT%\traceroute-visualizer-main\traceroute-visualizer-main"
call :launch_service "A) traceroute visualizer (Next.js)" "%TRACE_DIR%" "npm run dev"

set "POLYCOM_DIR=%ROOT%\PolycomYealinkMikrotikSwitchConfig-main\PolycomYealinkMikrotikSwitchConfig-main"
if not exist "%POLYCOM_DIR%\package.json" (
  set "POLYCOM_DIR="
  for /f "delims=" %%F in ('dir /s /b "%ROOT%\package.json" 2^>nul') do (
    findstr /i /c:"polycom" /c:"yealink" "%%F" >nul 2>&1
    if not errorlevel 1 if not defined POLYCOM_DIR set "POLYCOM_DIR=%%~dpF"
  )
)
if defined POLYCOM_DIR (
  call :launch_service "B) Polycom/Yealink/Mikrotik/Switch config app" "%POLYCOM_DIR%" "npm run dev"
) else (
  echo [WARN] B) Polycom/Yealink/Mikrotik/Switch config app not found. Skipping.
)

set "BACKEND_DIR=%ROOT%\freepbx-deploy-backend"
set "BACKEND_CMD="
if exist "%BACKEND_DIR%\package.json" (
  findstr /i /c:"\"dev\"" "%BACKEND_DIR%\package.json" >nul 2>&1
  if not errorlevel 1 (
    set "BACKEND_CMD=npm run dev"
  ) else (
    findstr /i /c:"\"start\"" "%BACKEND_DIR%\package.json" >nul 2>&1
    if not errorlevel 1 set "BACKEND_CMD=npm start"
  )
)
if defined BACKEND_CMD (
  call :launch_service "C) freepbx-deploy-backend" "%BACKEND_DIR%" "%BACKEND_CMD%"
) else (
  echo [WARN] C) freepbx-deploy-backend package.json scripts not found for npm run dev/npm start. Skipping.
)

set "UI_DIR=%ROOT%\freepbx-deploy-ui"
call :launch_service "D) freepbx-deploy-ui" "%UI_DIR%" "npm run dev"

set "CLI_DIR="
for /f "delims=" %%F in ('dir /s /b "%ROOT%\package.json" 2^>nul') do (
  findstr /i /c:"web-manager" /c:"cli-webmanager" "%%F" >nul 2>&1
  if not errorlevel 1 if not defined CLI_DIR set "CLI_DIR=%%~dpF"
)
if defined CLI_DIR (
  set "CLI_CMD=npm run dev"
  findstr /i /c:"\"dev\"" "!CLI_DIR!package.json" >nul 2>&1
  if errorlevel 1 (
    findstr /i /c:"\"start\"" "!CLI_DIR!package.json" >nul 2>&1
    if not errorlevel 1 set "CLI_CMD=npm start"
  )
  call :launch_service "E) CLI web manager" "!CLI_DIR!" "!CLI_CMD!"
) else (
  echo [WARN] E) CLI web manager package not found. Skipping.
)

echo.
if "%LAUNCH_FAILED%"=="0" (
  echo [DONE] Launch commands were issued.
  exit /b 0
) else (
  echo [ERROR] One or more windows failed to launch.
  exit /b 1
)

:launch_service
set "SERVICE_LABEL=%~1"
set "SERVICE_DIR=%~2"
set "SERVICE_CMD=%~3"

if not exist "%SERVICE_DIR%\" (
  echo [WARN] %SERVICE_LABEL% directory not found: "%SERVICE_DIR%". Skipping.
  exit /b 0
)

echo [START] %SERVICE_LABEL%
echo         Dir: %SERVICE_DIR%
echo         Cmd: %SERVICE_CMD%
start "" cmd /k "cd /d \"%SERVICE_DIR%\" && %SERVICE_CMD%"
if errorlevel 1 (
  set "LAUNCH_FAILED=1"
  echo [ERROR] Failed to launch %SERVICE_LABEL% window.
) else (
  echo [OK] Launched %SERVICE_LABEL%.
)
echo.
exit /b 0
