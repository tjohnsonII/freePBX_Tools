@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "LOG_DIR=%REPO_ROOT%\webscraper\var\logs"
set "LOG=%LOG_DIR%\kill_ports.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

set "PORTS=%*"
if "%PORTS%"=="" set "PORTS=8787 3004"

call :timestamp TS
echo %TS% [kill_ports] Checking ports %PORTS%...>>"%LOG%"
echo [kill_ports] Checking ports %PORTS%...

for %%P in (%PORTS%) do call :kill_port %%P

for /L %%I in (1,1,3) do (
  timeout /t 1 /nobreak >nul
  for %%P in (%PORTS%) do call :kill_port %%P
)

call :timestamp TS
echo %TS% [kill_ports] Done.>>"%LOG%"
echo [kill_ports] Done.
exit /b 0

:kill_port
set "PORT=%~1"
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  set "PID=%%A"
  call :timestamp TS
  echo %TS% [kill_ports] Killing PID !PID! on port %PORT%>>"%LOG%"
  echo [kill_ports] Killing PID !PID! on port %PORT%
  taskkill /PID !PID! /F /T >nul 2>&1
)
exit /b 0

:timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value ^| find "="') do set "dt=%%I"
set "%~1=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%:%dt:~12,2%"
exit /b 0
