# webscraper_manager

FastAPI backend that provides a unified REST + WebSocket API for controlling the scraper worker, inspecting the ticket database, streaming logs, and managing authentication cookies. Backs [manager-ui](../manager-ui/README.md) (Next.js, port 3004).

---

## Quick Start

```powershell
cd webscraper_manager
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m webscraper_manager.cli start
```

API at **<http://localhost:8000>**. Docs at **<http://localhost:8000/docs>**.

Or start directly with uvicorn:

```bash
uvicorn webscraper_manager.api.server:app --port 8000 --reload
```

---

## API Routes

### Health

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/health` | Liveness — `{ok: true}` |
| `GET` | `/api/status/summary` | Worker state, DB counts, queue depth |
| `GET` | `/api/status/full` | Extended status including auth and system info |

### Auth / Cookies

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/auth/status` | Cookie file status and validity |
| `POST` | `/api/auth/seed` | Write new cookie credentials |
| `POST` | `/api/auth/validate` | Validate stored credentials against live site |
| `POST` | `/api/auth/sync/chrome` | Import cookies from Chrome profile |
| `POST` | `/api/auth/sync/edge` | Import cookies from Edge profile |
| `POST` | `/api/auth/import` | Import cookies from raw JSON payload |
| `POST` | `/api/auth/clear` | Delete stored cookies |
| `GET` | `/api/auth/cookies/summary` | Count and domain summary |
| `GET` | `/api/auth/cookies/detail` | Full cookie list |
| `GET` | `/api/auth/history` | Auth event history |

### Database

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/db/summary` | Ticket count, file size, last-updated |
| `GET` | `/api/db/handles` | All customer handles in the DB |
| `GET` | `/api/db/tickets` | All tickets (paginated) |
| `GET` | `/api/db/failures` | Failed scrape records |
| `GET` | `/api/db/integrity` | SQLite PRAGMA integrity_check result |

### System

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/system/ports` | Listening ports + owning process |
| `GET` | `/api/system/processes` | Running process list |

### Logs

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/logs/recent` | Last N lines from the active log |
| `GET` | `/api/logs/files` | List available log files |
| `WS` | `/api/logs/stream` | Live log tail via WebSocket |

### Diagnostics

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/debug/report` | Full diagnostic dump (auth, DB, system) |
| `GET` | `/api/diagnostics/ticket-ingestion` | Ticket pipeline health check |
| `GET` | `/api/diagnostics/auth` | Auth subsystem diagnostics |
| `GET` | `/api/diagnostics/db` | Database diagnostics |
| `GET` | `/api/diagnostics/system` | System diagnostics |

### Orders (123NET)

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/orders` | Scrape 123NET orders page — `?pm=tjohnson` filters by project manager |

### Manager / Webscraper Control

| Method | Path | Description |
| ------ | ---- | ----------- |
| *(see manager.py, webscraper.py routes)* | `/api/manager/*`, `/api/webscraper/*` | Scraper worker start/pause/stop, job queuing |

---

## Services (Internal)

| Service | Purpose |
| ------- | ------- |
| `StateStore` | Shared in-memory + on-disk state for worker status |
| `EventBus` | JSONL event log for audit trail |
| `CommandRunner` | Subprocess runner for scraper commands |
| `AuthInspector` | Cookie file inspection and browser sync |
| `TicketPipelineService` | Orchestrates scrape jobs through the pipeline |
| `DBInspector` | SQLite query helpers for tickets DB |
| `SystemInspector` | Port scanning and process enumeration |

---

## CLI

```bash
python -m webscraper_manager.cli start    # Start the API server
python -m webscraper_manager.cli stop     # Stop the API server
python -m webscraper_manager.cli status   # Show running service status
```

---

## Project Structure

```text
webscraper_manager/
  api/
    server.py             # FastAPI app factory, middleware, router registration
    routes/
      auth.py             # /api/auth/* — cookie management
      db.py               # /api/db/* — database inspection
      diagnostics.py      # /api/diagnostics/*, /api/debug/report
      health.py           # /api/health, /api/status/*
      logs.py             # /api/logs/* + WebSocket stream
      manager.py          # /api/manager/* — worker control
      system.py           # /api/system/* — ports, processes
      tickets.py          # /api/tickets/*
      webscraper.py       # /api/webscraper/* — job queuing
    services/
      auth_inspector.py
      command_runner.py
      db_inspector.py
      event_bus.py
      state_store.py
      system_inspector.py
      ticket_pipeline.py
  cli.py                  # typer CLI for start/stop/status
```

---

## Data Files

| Path | Purpose |
| ---- | ------- |
| `webscraper/cookies.json` | Browser-exported cookie jar for 123.net auth |
| `webscraper/var/db/tickets.sqlite` | Scraped ticket database |
| `.webscraper_manager/events.jsonl` | Event bus audit log |
