@echo off
setlocal
cd /d %~dp0\..

set PYTHON=%CD%\.venv-webscraper\Scripts\python.exe
if not exist "%PYTHON%" (
  echo Missing venv python at %PYTHON%
  exit /b 1
)

set TICKETS_DB=%CD%\webscraper\output\tickets.sqlite
set OUT_DIR=%CD%\webscraper\output\scrape_runs
set NEXT_PUBLIC_TICKET_API_BASE=http://127.0.0.1:8787

set HANDLE_ARGS=
if not "%~1"=="" set HANDLE_ARGS=--handles %*

echo [PIPELINE] Scraping...
"%PYTHON%" scripts\scrape_all_handles.py %HANDLE_ARGS% --db "%TICKETS_DB%" --out "%OUT_DIR%" --auth-profile-only

echo [PIPELINE] Starting API...
start "ticket-api" cmd /k "cd /d %CD% && set TICKETS_DB=%TICKETS_DB% && "%PYTHON%" -m uvicorn webscraper.ticket_api.app:app --reload --port 8787"

echo [PIPELINE] Starting UI...
if exist "%ProgramFiles%\nodejs\npm.cmd" (
  set NPM_CMD=%ProgramFiles%\nodejs\npm.cmd
) else (
  set NPM_CMD=npm.cmd
)
start "ticket-ui" cmd /k "cd /d %CD%\webscraper\ticket-ui && set NEXT_PUBLIC_TICKET_API_BASE=%NEXT_PUBLIC_TICKET_API_BASE% && "%NPM_CMD%" install && "%NPM_CMD%" run dev"

start "" http://localhost:3000
"%PYTHON%" -c "import os,sqlite3;db=os.environ.get('TICKETS_DB');conn=sqlite3.connect(db);print('handles=',conn.execute('select count(*) from handles').fetchone()[0]);print('tickets=',conn.execute('select count(*) from tickets').fetchone()[0]);print('runs=',conn.execute('select count(*) from runs').fetchone()[0])"

echo If PowerShell blocks npm.ps1, use this .cmd launcher or npm.cmd directly.
endlocal
