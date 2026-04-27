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
