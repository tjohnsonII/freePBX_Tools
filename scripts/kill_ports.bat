@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py -3"

cd /d "%ROOT%"
echo [kill_ports] Delegating to canonical stop routine.
%PYTHON% scripts\stop_all_web_apps.py
exit /b %ERRORLEVEL%
