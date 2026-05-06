@echo off
setlocal

set "ROOT=%~dp0"
for %%I in ("%ROOT%.") do set "ROOT=%%~fI"

REM Prefer the webscraper venv Python; fall back to global py/python
set "VENV_PY=%ROOT%\webscraper\.venv-webscraper\Scripts\python.exe"
if exist "%VENV_PY%" goto :run

set "VENV_PY="
where py >nul 2>nul && set "VENV_PY=py"
if not defined VENV_PY (
    where python >nul 2>nul && set "VENV_PY=python"
)
if not defined VENV_PY (
    echo ERROR: No Python found. Activate the venv or install Python.
    exit /b 1
)

:run
echo Using Python: %VENV_PY%
"%VENV_PY%" "%ROOT%\create_shortcut.py"
if errorlevel 1 (
    echo.
    echo ERROR: create_shortcut.py failed (see above).
    pause
    exit /b 1
)

pause
endlocal
