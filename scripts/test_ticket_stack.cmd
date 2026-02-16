@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%" || exit /b 1

set "API_HOST=127.0.0.1"
set "API_PORT=8787"
set "UI_PORT=3000"
set "DB_PATH=webscraper\output\tickets.sqlite"
set "SMOKE_ONLY=0"
if /I "%~1"=="--smoke-only" set "SMOKE_ONLY=1"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist ".venv-webscraper\Scripts\python.exe" (
  set "PYTHON_EXE=.venv-webscraper\Scripts\python.exe"
) else (
  where py >nul 2>nul && (
    set "PYTHON_EXE=py"
    set "PYTHON_PREFIX=-3"
  )
)
if not defined PYTHON_EXE (
  where python >nul 2>nul && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  echo FAIL  Python executable not found.
  exit /b 1
)

echo INFO  Ensuring DB indexes exist...
%PYTHON_EXE% %PYTHON_PREFIX% -c "from webscraper.ticket_api import db; db.ensure_indexes(r'%REPO_ROOT%\%DB_PATH%'); print('indexes ensured')"
if errorlevel 1 (
  echo FAIL  Failed to ensure DB indexes.
  exit /b 1
)
echo PASS  Database indexes ensured.

if "%SMOKE_ONLY%"=="0" (
  echo INFO  Starting API in a new terminal window...
  start "ticket-api" cmd.exe /d /k "cd /d "%REPO_ROOT%" && %PYTHON_EXE% %PYTHON_PREFIX% -m webscraper.ticket_api.app --host %API_HOST% --port %API_PORT% --reload --db %DB_PATH%"

  echo INFO  Starting Ticket UI in a new terminal window...
  start "ticket-ui" cmd.exe /d /k "cd /d "%REPO_ROOT%\webscraper\ticket-ui" && set TICKET_API_PROXY_TARGET=http://%API_HOST%:%API_PORT% && npm.cmd run dev -- --port %UI_PORT%"
)

set "API_BASE=http://%API_HOST%:%API_PORT%"
set "READY=0"
for /L %%I in (1,1,45) do (
  curl.exe --silent --show-error "%API_BASE%/api/health" >nul 2>nul && (
    set "READY=1"
    goto :api_ready
  )
  timeout /t 1 /nobreak >nul
)

:api_ready
if not "%READY%"=="1" (
  echo FAIL  API did not become ready at %API_BASE%/api/health
  echo Next step: check the ticket-api terminal for errors.
  exit /b 1
)
echo PASS  API ready: %API_BASE%/api/health

curl.exe --silent --show-error "%API_BASE%/api/health" > "%TEMP%\ticket_api_health.json"
if errorlevel 1 (
  echo FAIL  GET /api/health failed.
  exit /b 1
)
echo PASS  GET /api/health

curl.exe --silent --show-error "%API_BASE%/api/handles/all?limit=5" > "%TEMP%\ticket_handles_all.json"
if errorlevel 1 (
  echo FAIL  GET /api/handles/all?limit=5 failed.
  exit /b 1
)
for /f "usebackq delims=" %%I in (`%PYTHON_EXE% %PYTHON_PREFIX% -c "import json; import sys; d=json.load(open(sys.argv[1], encoding='utf-8')); print(d.get('items',[None])[0] if d.get('items') else '')" "%TEMP%\ticket_handles_all.json"`) do set "SCRAPE_HANDLE=%%I"
echo PASS  GET /api/handles/all?limit=5

curl.exe --silent --show-error "%API_BASE%/api/handles/summary?limit=5" > "%TEMP%\ticket_handles_summary.json"
if errorlevel 1 (
  echo FAIL  GET /api/handles/summary?limit=5 failed.
  exit /b 1
)
echo PASS  GET /api/handles/summary?limit=5

if not defined SCRAPE_HANDLE (
  echo FAIL  No handle available for POST /api/scrape.
  echo Next step: seed tickets/handles in %DB_PATH% and rerun this script.
  exit /b 1
)

set "PAYLOAD={\"handle\":\"%SCRAPE_HANDLE%\",\"mode\":\"latest\",\"limit\":5}"
curl.exe --silent --show-error -X POST "%API_BASE%/api/scrape" -H "Content-Type: application/json" -d "%PAYLOAD%" > "%TEMP%\ticket_scrape_submit.json"
if errorlevel 1 (
  echo FAIL  POST /api/scrape failed.
  exit /b 1
)

for /f "usebackq delims=" %%I in (`%PYTHON_EXE% %PYTHON_PREFIX% -c "import json; import sys; d=json.load(open(sys.argv[1], encoding='utf-8')); print(d.get('jobId',''))" "%TEMP%\ticket_scrape_submit.json"`) do set "JOB_ID=%%I"
if not defined JOB_ID (
  echo FAIL  POST /api/scrape did not return a jobId.
  type "%TEMP%\ticket_scrape_submit.json"
  exit /b 1
)
echo PASS  POST /api/scrape queued jobId=%JOB_ID%

set "POLL_OK=0"
for /L %%I in (1,1,8) do (
  curl.exe --silent --show-error "%API_BASE%/api/scrape/%JOB_ID%" > "%TEMP%\ticket_scrape_poll.json"
  if errorlevel 1 (
    echo FAIL  GET /api/scrape/%JOB_ID% failed on poll %%I.
    exit /b 1
  )
  for /f "usebackq delims=" %%S in (`%PYTHON_EXE% %PYTHON_PREFIX% -c "import json; import sys; d=json.load(open(sys.argv[1], encoding='utf-8')); print(d.get('status',''))" "%TEMP%\ticket_scrape_poll.json"`) do set "JOB_STATUS=%%S"
  if defined JOB_STATUS (
    set "POLL_OK=1"
    echo PASS  GET /api/scrape/%JOB_ID% poll %%I status=!JOB_STATUS!
    if /I "!JOB_STATUS!"=="completed" goto :done
    if /I "!JOB_STATUS!"=="failed" goto :done
  )
  timeout /t 2 /nobreak >nul
)

:done
if not "%POLL_OK%"=="1" (
  echo FAIL  Polling did not return a status for jobId=%JOB_ID%.
  exit /b 1
)

echo PASS  Ticket stack smoke test complete.
echo INFO  UI URL is usually http://127.0.0.1:%UI_PORT% (Next.js may auto-bump to 3001+).
exit /b 0
