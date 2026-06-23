# freePBX_Tools — AI Agent Instructions (Server Branch)

## What this repo is

A suite of always-on web services running on an Ubuntu server at **123hostedtools.com**. The server branch is the deploy target — code runs as systemd services, served through Apache reverse proxies over HTTPS.

This is **not** a script collection or call-flow analyzer. That description is stale. Ignore it.

---

## Architecture

```
                        ┌─────────────────────────────────┐
  client laptop ──VPN──▶│  Apache :443 (HTTPS)            │
  (scraper runs here)   │  ├── polycom.123hostedtools.com  │
                        │  ├── manager.123hostedtools.com  │
                        │  ├── tickets.123hostedtools.com  │
                        │  ├── traceroute.123hostedtools.com│
                        │  └── homelab.123hostedtools.com  │
                        │                                  │
                        │  Internal services (127.0.0.1):  │
                        │  :5000  Web Manager API          │
                        │  :8787  Manager API (FastAPI)    │
                        │  :8788  Ticket API (FastAPI)     │
                        │  :8789  Client trigger API       │
                        │  :3004  Manager UI (Next.js)     │
                        │  :3005  Ticket UI (Next.js)      │
                        │  :3006  Traceroute (Node)        │
                        │  :3011  HomeLab (Next.js)        │
                        └─────────────────────────────────┘
```

All services bind to `127.0.0.1` — Apache proxies public traffic to them. Never expose internal ports directly.

---

## Services and their source directories

| Service | Port | Source | Venv / runtime |
|---------|------|--------|----------------|
| Web Manager API | 5000 | `webscraper_manager/` | `.venv-web-manager` |
| Manager API | 8787 | `webscraper/src/webscraper/manager_api.py` | `.venv-webscraper` |
| Ticket API | 8788 | `webscraper/src/webscraper/ticket_api.py` | `.venv-webscraper` |
| Client trigger API | 8789 | `webscraper/src/webscraper/client_trigger_api.py` | `.venv-webscraper` |
| Manager UI | 3004 | `manager-ui/` | Node (pm2) |
| Ticket UI | 3005 | `webscraper/ticket-ui/` | Node (pm2) |
| Traceroute | 3006 | `traceroute-visualizer-main/` | Node (pm2) |
| HomeLab | 3011 | `HomeLab_NetworkMapping/` | Node (pm2) |
| Polycom Config UI | static | `PolycomYealinkMikrotikSwitchConfig-main/dist/` | Apache static |

---

## Python venvs — three, isolated, not interchangeable

| Venv | Path | Purpose |
|------|------|---------|
| General | `.venv/` | FreePBX CLI tools, scripts, ad-hoc |
| Web Manager | `.venv-web-manager/` | `webscraper_manager/` Flask API only |
| Webscraper | `.venv-webscraper/` | All FastAPI services + scraper modules |

Never install packages into the wrong venv. Never use `pip install` without activating or using the venv's direct path.

---

## Client / server split

The **client laptop** runs `start_client.sh` with `CLIENT_MODE=1` set. It:
1. Launches `ultimate_scraper.py` against `secure.123.net` through VPN
2. POSTs scraped data to `/api/ingest/*` on this server
3. Auth: `X-Ingest-Key` header — HMAC-SHA256, constant-time compare in `ingest_routes.py`

The **server** never scrapes. It receives data, stores to SQLite, and serves APIs.

The `INGEST_API_KEY` lives in `.env` (gitignored). Generate with:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Secrets model

- `.env` at repo root — gitignored, never commit, holds `INGEST_API_KEY`
- `FREEPBX_USER` / `FREEPBX_PASSWORD` / `FREEPBX_ROOT_PASSWORD` — env vars, not in code
- No hardcoded credentials anywhere
- Pre-commit hooks run `detect-secrets` and `gitleaks` — do not bypass with `--no-verify`

---

## Startup

```bash
# Full rebuild + restart (used after code changes):
sudo bash FULL_START.sh

# Targeted restart of a single service:
sudo bash RESTART.sh ticket_api

# systemd controls the initial boot:
# /etc/systemd/system/freepbx-tools.service → scripts/start_services.sh
```

`FULL_START.sh` uses MD5 hashes of source dirs to skip frontend rebuilds that aren't needed. If a frontend isn't rebuilding after a code change, delete its `.src_hash` file.

---

## Database

- SQLite at `webscraper/db/tickets.db` (canonical path)
- Accessed by Ticket API and Manager API — never by the scraper directly on server
- Schema managed in `webscraper/src/webscraper/db.py`

```bash
sqlite3 webscraper/db/tickets.db ".tables"
sqlite3 webscraper/db/tickets.db "SELECT COUNT(*) FROM tickets;"
```

---

## Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Source of truth — merges from both server and client |
| `server` | Deploy target for this machine — rebases from main |
| `client` | Deploy target for scraper laptop — rebases from main |

Deploy server changes:
```bash
git push --force-with-lease origin server
# then on server:
git pull --rebase origin server
sudo bash FULL_START.sh
```

---

## Frontend build notes

- React/Next.js apps build with `npm run build` in their directory
- Polycom Config UI (`PolycomYealinkMikrotikSwitchConfig-main/`) builds to `dist/` — Apache serves that statically, no Node process runs
- Manager UI and Ticket UI run as pm2 processes after `npm run build && npm start`

---

## What NOT to do

- Do not run `sudo npm install` or `sudo npm run build` — permission issues; run as your user
- Do not touch `.env` or commit it
- Do not bind services to `0.0.0.0` — always `127.0.0.1`
- Do not install Python packages system-wide — always use the correct venv
- Do not use `--no-verify` on commits
- Do not push directly to `main` with `--force`

---

## Key files

| File | Purpose |
|------|---------|
| `RUNBOOK.md` | Exact commands for every operational task |
| `docs/ARCHITECTURE.md` | Deep-dive on data flow, API routes, startup sequence |
| `CODING_RULES.md` | Port registry, venv rules, secrets model, commit rules |
| `KNOWN_ISSUES.md` | 12 known issues with exact fixes |
| `webscraper/src/webscraper/ingest_routes.py` | Ingest API — HMAC auth, data ingestion |
| `webscraper/src/webscraper/ticket_api.py` | Ticket API — FastAPI, port 8788 |
| `webscraper/src/webscraper/manager_api.py` | Manager API — FastAPI, port 8787 |
| `scripts/start_services.sh` | Boot script called by systemd |
| `FULL_START.sh` | Full rebuild + restart script |
