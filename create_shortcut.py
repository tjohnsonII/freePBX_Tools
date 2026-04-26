#!/usr/bin/env python3
"""Create a Windows desktop shortcut that launches the Scrape Manager GUI.

Run once:
    python create_shortcut.py

What it does:
  - Creates "Scrape Manager.lnk" on your Desktop
  - Points to pythonw.exe (no console window) running scrape_gui.py
  - Sets the working directory to this project folder
  - Uses the Python icon by default (swap ICO_PATH below for a custom icon)

Requirements: Windows only (uses WScript.Shell via PowerShell).
"""

import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT      = PROJECT_ROOT / "scrape_gui.py"

# Ask Windows for the real Desktop path — handles OneDrive-redirected desktops
_desktop_raw = subprocess.check_output(
    ["powershell.exe", "-NoProfile", "-Command",
     "[Environment]::GetFolderPath('Desktop')"],
    text=True,
).strip()
DESKTOP  = Path(_desktop_raw)
SHORTCUT = DESKTOP / "Scrape Manager.lnk"

# pythonw.exe — same install as this script, but no console window on launch
_python = Path(sys.executable)
PYTHONW = _python.parent / "pythonw.exe"
if not PYTHONW.exists():
    PYTHONW = _python          # fall back to python.exe

# Icon: use 123net logo if available, otherwise fall back to Python icon
_ico = PROJECT_ROOT / "assets" / "123net.ico"
ICO_PATH = str(_ico) if _ico.exists() else f"{PYTHONW},0"

# ── Create shortcut via PowerShell WScript.Shell ──────────────────────────────

ps_script = f"""
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('{SHORTCUT}')
$lnk.TargetPath       = '{PYTHONW}'
$lnk.Arguments        = '"{SCRIPT}"'
$lnk.WorkingDirectory = '{PROJECT_ROOT}'
$lnk.IconLocation     = '{ICO_PATH}'
$lnk.Description      = 'FreePBX Scrape Manager'
$lnk.Save()
"""

result = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps_script],
    capture_output=True, text=True,
)

if result.returncode == 0:
    print(f"Shortcut created:\n  {SHORTCUT}")
    print("\nYou can also pin it to the taskbar:")
    print("  Right-click the shortcut -> Pin to taskbar")
else:
    print("Failed to create shortcut:")
    print(result.stderr)
    sys.exit(1)
