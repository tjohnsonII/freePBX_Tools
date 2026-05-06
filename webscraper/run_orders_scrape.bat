@echo off
setlocal

set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv-webscraper\Scripts\python.exe
set ENV_FILE=%SCRIPT_DIR%..\.env
set SCRAPER=%SCRIPT_DIR%scripts\scrape_orders.py

if not exist "%VENV_PYTHON%" (
    echo ERROR: venv not found at %VENV_PYTHON%
    echo Run: py -3.12 -m venv .venv-webscraper
    exit /b 1
)

if not exist "%ENV_FILE%" (
    echo WARNING: .env not found at %ENV_FILE% -- credentials must already be in environment
) else (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        set "line=%%A"
        if not "%%A"=="" if not "%%A:~0,1%"=="#" (
            set "%%A=%%B"
        )
    )
)

echo %TIME%  Starting orders scrape ^(CLIENT_MODE=%CLIENT_MODE% -^> %INGEST_SERVER_URL%^)
"%VENV_PYTHON%" "%SCRAPER%"
if errorlevel 1 (
    echo WARNING: scraper exited with error
    exit /b 1
)
echo %TIME%  Done.
endlocal
