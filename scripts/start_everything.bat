@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py -3"

echo [start_everything] Starting canonical web app launcher from "%ROOT%"
cd /d "%ROOT%"
%PYTHON% scripts\run_all_web_apps.py --browser existing-profile --webscraper-mode combined --doctor --strict-readiness
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo [start_everything] Launcher failed with exit code %RC%.
  echo [start_everything] Review var\web-app-launcher\startup_summary.json and logs under var\web-app-launcher\logs.
  exit /b %RC%
)

echo [start_everything] Startup complete.
exit /b 0
