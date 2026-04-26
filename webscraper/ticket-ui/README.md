# ticket-ui

Next.js 14 UI for browsing ticket data and controlling scraper jobs through the FastAPI ticket API.

## Windows runbook (PowerShell-friendly)

### 1) Start API (repo root)

Install API/runtime dependencies first (prevents `python-multipart` warnings):

```powershell
cd E:\DevTools\freepbx-tools
python -m pip install -r webscraper\requirements.txt -r webscraper\requirements_api.txt
```

```powershell
cd E:\DevTools\freepbx-tools
python -m webscraper.ticket_api.app --host 127.0.0.1 --port 8787 --reload
```

The DB path defaults to `webscraper/var/db/tickets.sqlite` (auto-created). Pass `--db <path>` to override.

### 2) Start UI (new terminal)

```powershell
cd E:\DevTools\freepbx-tools\webscraper\ticket-ui
npm.cmd install
$env:TICKET_API_PROXY_TARGET = 'http://127.0.0.1:8787'
npm.cmd run dev
```

Notes:

- Use `npm.cmd` in PowerShell to avoid `npm.ps1` execution-policy failures.
- In PowerShell, use normal `cd` paths (`cd E:\...`), not `cd /d` (that is CMD syntax).
- The combined launcher (`python -m webscraper.dev_server --ticket-stack`) starts the API on 8787 and the UI on **port 3004** by default, then waits for `http://127.0.0.1:8787/api/health` before opening the UI.
- When running `npm.cmd run dev` manually, Next.js uses port 3000 by default. Set `$env:PORT = '3004'` to match the combined launcher.

## curl.exe smoke examples (Windows)

Use `curl.exe` (not the PowerShell `curl` alias):

```powershell
curl.exe --silent --show-error "http://127.0.0.1:8787/api/health"
curl.exe --silent --show-error "http://127.0.0.1:8787/api/handles/all?limit=5"
curl.exe --silent --show-error "http://127.0.0.1:8787/api/handles/summary?limit=5"
```

Start a scrape job (handles are loaded from `customer_handles.txt`):

```powershell
curl.exe --silent --show-error -X POST "http://127.0.0.1:8787/api/scrape/start" -H "Content-Type: application/json" -d '{}'
```

Resume from a specific handle:

```powershell
curl.exe --silent --show-error -X POST "http://127.0.0.1:8787/api/scrape/start" -H "Content-Type: application/json" -d '{"resume_from_handle":"KPM"}'
```

Poll a job by ID:

```powershell
curl.exe --silent --show-error "http://127.0.0.1:8787/api/jobs/<job_id>"
curl.exe --silent --show-error "http://127.0.0.1:8787/api/jobs/<job_id>/events"
```

## Features

- Searchable/debounced handle dropdown (`GET /api/handles/all?q=&limit=`).
- Run scrape jobs (`POST /api/scrape/start`); handles are loaded server-side from `customer_handles.txt`.
- Job polling (`GET /api/jobs/{job_id}`) and event log tail (`GET /api/jobs/{job_id}/events`).
- API diagnostics (`/api/health` and proxy target visibility).

## Quick verification checklist

1. `curl.exe --silent --show-error "http://127.0.0.1:8787/api/health"` returns `status: ok`.
2. Open `http://127.0.0.1:3004` (combined launcher default) or `http://127.0.0.1:3000` (manual `npm run dev`) and verify handles load.
3. Start a scrape job from UI and verify status/logs update.
4. Verify tickets return from API:
   - `curl.exe --silent --show-error "http://127.0.0.1:8787/api/tickets?page=1&pageSize=20"`

## Cookie/Auth import guide

1. Open the UI (`/`) and use **Authentication**.
2. Click **Import Cookies** to open a file picker, choose your exported cookies file, then click **Upload Selected File**.
3. Or click **Paste Cookies** and paste one of:
   - Cookie header (`name=value; name2=value2`)
   - Netscape cookie export text
   - JSON cookie array export
4. Click **Validate Auth** — the UI will check session health using the stored cookies.

API helpers:

- `GET /api/system/status` — overall system and DB readiness.
- `GET /api/db/status` — DB path and table stats.
