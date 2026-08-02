@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
for %%I in ("%ROOT%.") do set "ROOT=%%~fI"

rem Prefer the project-level Windows Python, fall back to py launcher, then PATH python
set "WIN_PYTHON=E:\DevTools\Python\python.exe"

if exist "%WIN_PYTHON%" (
    set "PYTHON=%WIN_PYTHON%"
) else (
    where py >nul 2>nul && set "PYTHON=py -3" || set "PYTHON=python"
)

echo [launch_gui] Starting Scrape Manager with Windows Python: %PYTHON%
cd /d "%ROOT%"
%PYTHON% scrape_gui.py %*
