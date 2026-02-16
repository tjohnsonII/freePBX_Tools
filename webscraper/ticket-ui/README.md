# ticket-ui

Next.js 14 UI for browsing ticket data and controlling scraper jobs through the FastAPI ticket API.

## Windows runbook (PowerShell-friendly)

### 1) Start API (repo root)

```powershell
cd E:\DevTools\freepbx-tools
python -m webscraper.ticket_api.app --host 127.0.0.1 --port 8787 --reload --db webscraper\output\tickets.sqlite
```

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
- If port 3000 is busy, Next.js may auto-bump to 3001+; this is expected.

## curl.exe smoke examples (Windows)

Use `curl.exe` (not the PowerShell `curl` alias):

```powershell
curl.exe --silent --show-error "http://127.0.0.1:8787/api/health"
curl.exe --silent --show-error "http://127.0.0.1:8787/api/handles/all?limit=5"
curl.exe --silent --show-error "http://127.0.0.1:8787/api/handles/summary?limit=5"
```

POST scrape with valid JSON:

```powershell
curl.exe --silent --show-error -X POST "http://127.0.0.1:8787/api/scrape" -H "Content-Type: application/json" -d '{"handle":"KPM","mode":"latest","limit":5}'
```

Generate a valid command dynamically:

```powershell
python scripts\print_scrape_curl.py --handle KPM --mode latest --limit 5
```

## Features

- Searchable/debounced handle dropdown (`GET /api/handles/all?q=&limit=`).
- Run scrape jobs (`POST /api/scrape`) with mode + optional limit.
- Job polling and live log tail (`GET /api/scrape/{jobId}`).
- API diagnostics (`/api/health` and proxy target visibility).

## Quick verification checklist

1. `curl.exe --silent --show-error "http://127.0.0.1:8787/api/health"` returns `status: ok`.
2. Open `http://127.0.0.1:3000` (or auto-bumped port) and verify handles load.
3. Start a scrape job from UI and verify status/logs update.
4. Verify tickets return from API:
   - `curl.exe --silent --show-error "http://127.0.0.1:8787/api/tickets?page=1&pageSize=20"`
