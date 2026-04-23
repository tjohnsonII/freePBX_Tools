@echo off
REM chrome_debug_setup.bat - Launch Chrome for DevTools cookie extraction
REM 1. Close all Chrome browser sessions
REM 2. Ensure Windows Firewall rule for TCP 9222 inbound
REM 3. Launch Chrome with remote debugging

REM Step 1: Close all Chrome browser sessions
TASKKILL /F /IM chrome.exe >nul 2>&1

REM Step 2: Check for firewall rule, create if missing
REM (Requires admin privileges; uses cmd-only netsh)
netsh advfirewall firewall show rule name="Chrome DevTools 9222" >nul 2>&1
if errorlevel 1 (
  netsh advfirewall firewall add rule name="Chrome DevTools 9222" dir=in action=allow protocol=TCP localport=9222
)

REM Step 3: Launch Chrome with remote debugging
start "Chrome DevTools" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=http://localhost:9222 --user-data-dir="C:\Temp\ChromeDebug"

echo Chrome launched with DevTools on port 9222.
pause
