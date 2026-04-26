# webscraper

Scraping pipeline and ticket data API. Two things in one Python package:

1. **Scraper** — Selenium browser automation that authenticates to the 123.net portal, iterates customer handles, and collects ticket history
2. **Ticket API** — FastAPI service that stores ticket data in SQLite and serves it to the Ticket UI; also accepts ingest from the client scraper via HTTP

---

## Quick Start

### Start the Ticket API (server mode — writes to local SQLite)
```bash
# From repo root
source .venv-webscraper/bin/activate
uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8788
```

Or via RESTART.sh:
```bash
sudo ./RESTART.sh ticket-api
```

### API endpoints

#### Health / status

- `GET /api/health` (also `/health`, `/healthz`)
- `GET /api/system/status`
- `GET /api/db/status`

#### Scrape control

- `POST /api/scrape/start` — launch a new scrape job (body: `{"resume_from_handle": "<HANDLE>|null"}`)
- `POST /api/scrape/selenium_fallback` — alias for `/api/scrape/start` (backward compat)
- `GET /api/scrape/state` — current scrape state snapshot

#### Jobs

- `GET /api/jobs` — list all scrape jobs
- `GET /api/jobs/{job_id}` — single job status
- `GET /api/jobs/{job_id}/events` — event log for a job

#### Handles

- `GET /api/handles` — list tracked handles
- `GET /api/handles/all` — all handles with optional `?q=` filter and `?limit=` cap
- `GET /api/handles/summary` — per-handle ticket counts
- `GET /api/handles/{handle}/latest` — latest scrape result for handle
- `GET /api/handles/{handle}/tickets` — tickets for a handle
- `POST /api/handles` — add a handle
- `DELETE /api/handles/{handle}` — remove a handle

#### Tickets

- `GET /api/tickets` — paginated ticket list
- `GET /api/tickets/{ticket_id}` — single ticket

#### Knowledge base

- `GET /api/kb/tickets` — KB ticket search
- `GET /api/kb/tickets/{ticket_id}` — single KB ticket
- `GET /api/kb/handles` — handles in KB
- `GET /api/kb/export` — export KB data

#### Companies / timeline

- `GET /api/companies/{handle}` — company record
- `GET /api/companies/{handle}/tickets` — tickets for company
- `GET /api/companies/{handle}/timeline` — event timeline for company
- `POST /api/jobs/build-timeline` — build timeline for a handle

#### VPBX

- `GET /api/vpbx/records` — VPBX table records
- `POST /api/vpbx/refresh` — refresh VPBX data
- `GET /api/vpbx/device-configs` — device config records
- `PUT /api/vpbx/device-configs/{device_id}/sidecar` — update sidecar config
- `POST /api/vpbx/device-configs/refresh` — refresh device configs
- `GET /api/vpbx/site-configs` — site config list
- `GET /api/vpbx/site-configs/{handle}` — site config for handle
- `POST /api/vpbx/site-configs/refresh` — refresh site configs

#### NOC queue

- `GET /api/noc-queue/records` — NOC queue records
- `POST /api/noc-queue/refresh` — refresh NOC queue

#### Logs

Localhost only. Enabled automatically in dev environments; set `WEBSCRAPER_LOGS_ENABLED=1` in production.

- `GET /api/logs/enabled` — check if log API is enabled
- `GET /api/logs/list` — list log files
- `GET /api/logs/tail` — tail a log file

#### Artifacts / events

- `GET /api/artifacts` — list scrape artifacts
- `GET /api/events/latest` — latest system events

### Start the Scraper Worker

```bash
# Via RESTART.sh (recommended — handles display env)
sudo ./RESTART.sh worker

# Or directly
source .venv-webscraper/bin/activate
python -m webscraper --mode headless
```

### Start in Client Mode (laptop → sends data to server)
```bash
./start_client.sh          # uses CLIENT_MODE=1 from .env
```

---

## Package Structure

```
webscraper/
├── src/webscraper/              Python package root
│   ├── ticket_api/              FastAPI ticket store
│   │   ├── app.py               Entry point — loads db or db_client based on CLIENT_MODE
│   │   ├── db.py                Local SQLite write path (server mode)
│   │   ├── db_client.py         Remote HTTP write path (CLIENT_MODE=1)
│   │   ├── db_core.py           Shared connection/query utilities
│   │   ├── db_init.py           Schema creation
│   │   ├── ingest_routes.py     POST /api/ingest/* — receive from client
│   │   └── models.py            Pydantic models
│   ├── auth/                    Portal authentication (cookies, sessions)
│   ├── browser/                 Chrome/Selenium browser management
│   ├── scrape/                  Scrape orchestration
│   │   └── runner.py            Main scrape loop
│   ├── parsers/                 HTML parsers for ticket/handle data
│   ├── kb/                      Knowledge base utilities
│   ├── handles_loader.py        Load handle list from configs/
│   ├── paths.py                 Canonical path resolution
│   ├── logging_config.py        Logging setup
│   └── legacy/                  Quarantined old modules (imports kept for compat)
├── ticket-ui/                   Next.js front end — port 3005
├── configs/
│   └── handles/
│       └── handles_master.txt   Master handle list (541 handles)
├── var/                         Runtime data (gitignored)
│   ├── db/tickets.sqlite        The database
│   ├── chrome-profile/          Chrome session data
│   └── logs/                    Scraper logs
├── tests/                       Pytest tests
├── docs/                        Architecture and review docs
│   ├── auth_api_changelog.md
│   ├── artifacts_contract.md
│   ├── config_map.md
│   └── reviews/
└── pyproject.toml               Package definition + deps
```

---

## Client / Server Mode

The `app.py` entry point switches modes based on `CLIENT_MODE` env var:

```python
if os.getenv("CLIENT_MODE", "").strip() == "1":
    from webscraper.ticket_api import db_client as db   # sends writes to remote server
else:
    from webscraper.ticket_api import db                # writes to local SQLite
```

**Server mode** (default):
- Reads `TICKETS_DB_PATH` or defaults to `webscraper/var/db/tickets.sqlite`
- All writes go to local SQLite
- Exposes `/api/ingest/*` for incoming client data

**Client mode** (`CLIENT_MODE=1`):
- Reads `INGEST_SERVER_URL` and `INGEST_API_KEY` from env
- All writes → `POST INGEST_SERVER_URL/api/ingest/*` with `X-Ingest-Key` header
- No local SQLite
- `db_path` argument is ignored everywhere in `db_client.py`

---

## API Endpoints

```
GET  /api/health
GET  /api/handles           ?q=&limit=500&offset=0
GET  /api/handles/{handle}
GET  /api/tickets/{handle}
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/scrape/run        trigger scrape
POST /api/scrape/run-e2e    trigger E2E scrape

# Ingest (requires X-Ingest-Key from non-localhost)
POST /api/ingest/tickets    body: {handle, tickets: [...]}
POST /api/ingest/handles    body: {rows: [...]}
```

---

## Database

SQLite at `webscraper/var/db/tickets.sqlite`.

```bash
# Inspect
sqlite3 webscraper/var/db/tickets.sqlite ".tables"
sqlite3 webscraper/var/db/tickets.sqlite "SELECT COUNT(*) FROM tickets;"
sqlite3 webscraper/var/db/tickets.sqlite "SELECT handle, last_updated_utc FROM handles ORDER BY last_updated_utc DESC LIMIT 20;"

# Init schema (if DB doesn't exist)
source .venv-webscraper/bin/activate
python -c "from webscraper.ticket_api.db_init import init_db; init_db('webscraper/var/db/tickets.sqlite')"
```

---

## Running Tests

```bash
source .venv-webscraper/bin/activate
pytest -q webscraper/tests
```

---

## Ingest API Auth

The server validates ingest requests with constant-time HMAC compare:

```python
if not hmac.compare_digest(key, provided):
    raise HTTPException(403)
```

If `INGEST_API_KEY` env var is empty on the server, ingest is allowed from `127.0.0.1` / `::1` only (safe for local dev / same-machine operation).

Generate a key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Scraper Config

| File | Purpose |
|------|---------|
| `configs/handles/handles_master.txt` | Master handle list — one per line, `#` = comment |
| `src/webscraper/paths.py` | All canonical paths |
| `src/webscraper/logging_config.py` | Log directories and format |

Chrome profile is stored at `webscraper/var/chrome-profile/` — gitignored. If the profile is lost, the scraper must re-authenticate interactively.

---

## Architecture Notes

- `app.py` startup bootstraps the DB (indexes, handle rows, stale-job reap) in server mode only. Client mode skips all DB setup and just logs the ingest server URL.
- `handles_loader.py` reads the master handle list and returns a deduplicated list, skipping comment lines.
- The `WRITE_LOCK` in `db_core.py` serializes all SQLite writes (SQLite supports one writer at a time).
- `db_client.py` has the same function signatures as `db.py` — it's a drop-in replacement. Functions that accept `db_path` ignore it (no local DB in client mode).

For deeper architecture: see `docs/ARCHITECTURE.md` (repo root) and `webscraper/docs/`.
