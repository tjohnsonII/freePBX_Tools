# ticket-ui

Next.js UI for browsing ticket data and controlling scraper jobs through the FastAPI ticket API.

## Local runbook

### 1) Start API

```bash
python -m webscraper.ticket_api.app --reload --port 8787 --db webscraper/output/tickets.sqlite
```

### 2) Start UI (proxying `/api/*` to local API)

```bash
cd webscraper/ticket-ui
npm install
npm run dev:local-api
```

PowerShell variant:

```powershell
npm run dev:local-api:ps
```

## Features

- Searchable/debounced handle dropdown (`GET /api/handles/all?q=&limit=`).
- Run scrape jobs (`POST /api/scrape`) with mode + optional limit.
- Job polling and live log tail (`GET /api/scrape/{jobId}`).
- Actionable API diagnostics (base/proxy target, startup command, `/api/health` link).

## Quick verification checklist

1. Open `http://127.0.0.1:8787/health` (or `curl http://127.0.0.1:8787/health`) and confirm the API reports `status: ok`.
2. Open `http://127.0.0.1:3000` and confirm the handle dropdown populates.
3. Start a scrape job from UI and confirm job status/logs update.
4. Confirm tickets appear in UI and API returns data:
   - `curl "http://127.0.0.1:8787/api/handles/<HANDLE>/tickets?page=1&pageSize=20"`
