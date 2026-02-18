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

set "BACKEND_DIR=%ROOT%\freepbx-deploy-backend"
set "BACKEND_CMD=npm run dev || (echo [WARN] npm run dev failed for freepbx-deploy-backend. Try: npm start)"
call :launch_service "B) freepbx-deploy-backend" "%BACKEND_DIR%" "%BACKEND_CMD%"

set "UI_DIR=%ROOT%\freepbx-deploy-ui"
call :launch_service "C) freepbx-deploy-ui" "%UI_DIR%" "npm run dev"

set "POLYCOM_DIR=%ROOT%\PolycomYealinkMikrotikSwitchConfig-main\PolycomYealinkMikrotikSwitchConfig-main"
call :launch_service "D) Polycom/Yealink/Mikrotik/Switch config app" "%POLYCOM_DIR%" "npm run dev"

set "CLI_DIR=%ROOT%\web-manager"
call :launch_service "E) CLI web manager" "%CLI_DIR%" "npm run dev"

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
  echo [WARN] !SERVICE_LABEL! not found at: "%SERVICE_DIR%". Skipping.
  exit /b 0
)

if not exist "%SERVICE_DIR%\package.json" (
  echo [WARN] !SERVICE_LABEL! not found at: "%SERVICE_DIR%". Skipping.
  exit /b 0
)

echo [START] !SERVICE_LABEL!
echo         Dir: !SERVICE_DIR!
echo         Cmd: !SERVICE_CMD!
start "" cmd /k "cd /d \"!SERVICE_DIR!\" && !SERVICE_CMD!"
if errorlevel 1 (
  set "LAUNCH_FAILED=1"
  echo [ERROR] Failed to launch !SERVICE_LABEL! window.
) else (
  echo [OK] Launched !SERVICE_LABEL!.
)
echo.
exit /b 0
