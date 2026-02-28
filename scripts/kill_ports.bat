@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "LOG_DIR=%REPO_ROOT%\webscraper\var\logs"
set "LOG_FILE=%LOG_DIR%\kill_ports.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

set "KILLED="
for %%P in (8787 3004) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    set "PID=%%A"
    echo !KILLED! | findstr /c:";!PID!;" >nul
    if errorlevel 1 (
      call :timestamp NOW
      echo !NOW! [kill_ports] Killing PID !PID! on port %%P>>"%LOG_FILE%"
      taskkill /F /PID !PID! >nul 2>&1
      set "KILLED=!KILLED!;!PID!;"
    )
  )
)

exit /b 0

:timestamp
set "%~1="
for /f "tokens=2 delims==" %%T in ('wmic os get localdatetime /value 2^>nul ^| find "="') do set "DT=%%T"
if defined DT (
  set "%~1=%DT:~0,4%-%DT:~4,2%-%DT:~6,2% %DT:~8,2%:%DT:~10,2%:%DT:~12,2%"
  exit /b 0
)
set "%~1=%date% %time:~0,8%"
exit /b 0
