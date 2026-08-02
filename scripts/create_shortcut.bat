@echo off
setlocal

set "WIN_PYTHON=E:\DevTools\Python\python.exe"
if not exist "%WIN_PYTHON%" (
    echo ERROR: %WIN_PYTHON% not found. Update the path in create_shortcut.bat
    pause
    exit /b 1
)

echo [1/2] Creating shortcut...
cscript //nologo "%~dp0create_shortcut.vbs"
if errorlevel 1 exit /b 1

echo [2/2] Stamping AppUserModelID...
"%WIN_PYTHON%" "%~dp0set_shortcut_appid.py"
if errorlevel 1 (
    echo WARNING: Could not set AppUserModelID - icon may still show as Python
    pause
)

echo Done. Unpin the old taskbar icon then right-click the desktop shortcut and Pin to taskbar.
