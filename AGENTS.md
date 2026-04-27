# AGENTS.md — AI Agent and Automation Guidance

Rules for AI coding agents (Claude, Codex, Copilot, etc.) working in this repo.

**High sensitivity:** parts of this repo interact with customer systems and contain scraped ticket data. Follow the hard rules. When in doubt, add a `TODO/VERIFY` comment rather than guessing.

---

## Hard Rules (Non-Negotiable)

### Secrets and sensitive data
- **Never** create, modify, or commit:
  - `.env` files (gitignored — contains `INGEST_API_KEY` and similar)
  - Cookies, sessions, auth tokens
  - Customer data, scrape outputs, ticket databases
  - SQLite database files (`*.db`, `*.sqlite`)
  - Chrome profile data (`webscraper/var/chrome-profile/`)
- Treat these paths as **off-limits**:
  - `webscraper/var/` — runtime data, never committed
  - `scraped_tickets/` — legacy scrape outputs
  - `.env` — local secrets
  - `var/` — runtime state files

### Never do these
- Never bypass pre-commit hooks with `--no-verify`
- Never commit to `server` or `client` branch directly — develop on `main`
- Never run `npm run dev` on the server — production builds only
- Never install Python packages into system Python — always use the project venv
- Never share or cross-activate venvs between zones
- Never add modern Python 3.7+ features to `freepbx-tools/bin/` — those run on Python 3.6.7

---

## Repository Zones

Understanding zones is essential before making any change.

### Zone A — FreePBX CLI (Remote PBX Servers)
**Path:** `freepbx-tools/bin/`  
**Runtime:** Python 3.6.7 on production FreePBX PBX hosts  
**Run as:** root  
These deploy to actual FreePBX phone system servers — not this Ubuntu server. Must stay Python 3.6 compatible. Uses `mysql -NBe` via subprocess (no Python DB drivers).

### Zone B — Server Python Services
**Paths:** `webscraper/`, `webscraper_manager/`, `scripts/`, root helpers  
**Runtime:** Python 3.12.x, Ubuntu Linux server  
Three separate venvs (never cross-activate):
- `.venv-web-manager` → Manager API on port 8787
- `.venv-webscraper` → Ticket API on port 8788 + scraper worker
- `.venv` → general scripts, `web_manager.py`

### Zone C — Front-End Apps
**Paths:** `manager-ui/`, `webscraper/ticket-ui/`, `PolycomYealinkMikrotikSwitchConfig-main/`, `traceroute-visualizer-main/`, `HomeLab_NetworkMapping/ccna-lab-tracker/`  
**Runtime:** Node.js 20+, npm, Ubuntu Linux server  
Built with `npm run build`, served in production with `npm run start`. Never `npm run dev` on server.

### Zone D — Client Scraper (Laptop)
**Entry point:** `start_client.sh`  
**Runtime:** same Python venv as Zone B but with `CLIENT_MODE=1`  
Runs on a laptop over VPN. Sends scraped data to server via authenticated ingest API.

---

## Architecture Summary

```
Client Laptop (VPN, CLIENT_MODE=1)
  → POST /api/ingest/*  X-Ingest-Key: <shared>
  → Server :8788 (Ticket API)
       → writes to webscraper/var/db/tickets.sqlite

Server (Ubuntu, always-on)
  Apache :443 → proxy to internal services
  :8787  Manager API    (.venv-web-manager, FastAPI)
  :8788  Ticket API     (.venv-webscraper, FastAPI + SQLite)
  :3004  Manager UI     (Next.js, npm)
  :3005  Ticket UI      (Next.js, npm)
  :3006  Traceroute UI  (Next.js, npm)
  :3011  HomeLab        (Next.js, npm)
  :5000  Web Manager    (.venv, Flask)
  static Polycom Config UI (dist/ served by Apache)

systemd: freepbx-tools.service → scripts/start_services.sh (boot)
Manual:  sudo ./FULL_START.sh  (full rebuild + start)
Quick:   sudo ./RESTART.sh     (per-service restart menu)
```

---

## Repo Map (Authoritative)

### Applications (Active)

| Directory | What it is |
|-----------|-----------|
| `manager-ui/` | Next.js dashboard UI (port 3004) |
| `webscraper_manager/` | FastAPI Manager API (port 8787) — backend for manager-ui |
| `webscraper/src/webscraper/` | Python package: scraper + Ticket API (port 8788) |
| `webscraper/ticket-ui/` | Next.js ticket browser UI (port 3005) |
| `PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/` | Vite/React static config generator |
| `traceroute-visualizer-main/traceroute-visualizer-main/` | Next.js traceroute UI (port 3006) |
| `HomeLab_NetworkMapping/ccna-lab-tracker/` | Next.js CCNA tracker (port 3011) |
| `freepbx-tools/bin/` | FreePBX CLI tools (deployed to PBX servers, Python 3.6) |
| `freepbx-deploy-ui/` + `freepbx-deploy-backend/` | Deploy tool UI + backend (local dev only) |
| `web_manager.py` | Flask FreePBX web manager (port 5000) |

### Key Supporting Files

| File | Purpose |
|------|---------|
| `FULL_START.sh` | Full rebuild + start all services (run as root) |
| `RESTART.sh` | Per-service restart menu (run as root) |
| `start_client.sh` | Start scraper in client mode (laptop only) |
| `scripts/start_services.sh` | Lean startup called by systemd |
| `scripts/run_all_web_apps.py` | Python launcher for all services |
| `scripts/stop_all_web_apps.py` | Graceful service shutdown |
| `systemd/freepbx-tools.service` | systemd unit (root-owned) |
| `.env` | Gitignored secrets — INGEST_API_KEY, CLIENT_MODE, etc. |
| `.env.example` | Committed template for `.env` |

### Data / Runtime (Never Source)

| Path | What it is |
|------|-----------|
| `webscraper/var/db/tickets.sqlite` | The live ticket database |
| `webscraper/var/chrome-profile/` | Chrome session (gitignored) |
| `var/` | Runtime logs and state |
| `.next/`, `dist/` | Build outputs |
| `node_modules/` | npm packages |
| `scraped_tickets/` | Legacy data |

---

## Run Commands (Source of Truth)

All commands run from `/var/www/freePBX_Tools` as root unless noted.

```bash
# Full rebuild and start
sudo ./FULL_START.sh

# Restart one service
sudo ./RESTART.sh manager-api   # port 8787
sudo ./RESTART.sh ticket-api    # port 8788
sudo ./RESTART.sh manager-ui    # port 3004
sudo ./RESTART.sh ticket-ui     # port 3005
sudo ./RESTART.sh worker        # scraper

# Health checks
curl -sf http://127.0.0.1:8787/api/health
curl -sf http://127.0.0.1:8788/api/health

# systemd
systemctl status freepbx-tools.service
journalctl -fu freepbx-tools.service

# Run tests
source .venv-webscraper/bin/activate
pytest -q webscraper/tests
```

---

## Subproject: webscraper (Zone B)

**Package:** `webscraper/src/webscraper/`  
**Venv:** `.venv-webscraper`

Active modules:
- `ticket_api/app.py` — FastAPI entry point, switches db vs db_client on CLIENT_MODE
- `ticket_api/db.py` — SQLite write path (server mode)
- `ticket_api/db_client.py` — HTTP write path (client mode, sends to INGEST_SERVER_URL)
- `ticket_api/ingest_routes.py` — POST /api/ingest/* with X-Ingest-Key auth
- `auth/` — portal authentication
- `browser/` — Chrome/Selenium management
- `scrape/runner.py` — main scrape loop
- `parsers/` — HTML ticket parsers

Legacy modules (do not use for new work):
- `legacy/` — compatibility shims for old imports
- `webscraper/src/webscraper/scraping/` — deprecated compat shim

Run ticket API: `uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8788`

---

## Subproject: webscraper_manager (Zone B)

**Package:** `webscraper_manager/`  
**Venv:** `.venv-web-manager`  
**Port:** 8787

Active modules:
- `api/server.py` — FastAPI app factory
- `api/routes/` — route groups (auth, db, diagnostics, health, logs, manager, services, system, tickets, webscraper)
- `api/services/` — business logic (StateStore, EventBus, CommandRunner, AuthInspector, TicketPipelineService, DBInspector, SystemInspector)

Run: `uvicorn webscraper_manager.api.server:app --host 127.0.0.1 --port 8787`

---

## Subproject: manager-ui (Zone C)

**Framework:** Next.js 14 App Router + Tailwind CSS  
**Port:** 3004

Pages: `/dashboard`, `/services`, `/auth`, `/handles`, `/tickets`, `/logs`, `/system`, `/database`

API base (browser-side): `NEXT_PUBLIC_API_BASE=https://manager-api.123hostedtools.com`  
Set automatically by `FULL_START.sh` in `manager-ui/.env.local` before each build.

Build: `cd manager-ui && npm ci && npm run build`  
Start: `npm --prefix manager-ui run start -- --port 3004 --hostname 127.0.0.1`

---

## Making Safe Changes

### Before editing any file
1. Identify which zone it belongs to
2. Check if it's a source file (not in `var/`, `dist/`, `.next/`, `node_modules/`)
3. For Zone A: verify changes are Python 3.6 compatible
4. For Zone B: activate the correct venv before testing

### Adding a dependency
- Zone B: add to `requirements.txt` or `pyproject.toml` in the correct subproject, then `pip install -e .`
- Zone C: `npm install --save <package>` in the correct app directory

### Testing changes
```bash
# Python (Zone B)
source .venv-webscraper/bin/activate
pytest -q webscraper/tests

# Type checking
pyright webscraper/src

# Front-end (Zone C) — build to catch type errors
cd manager-ui && npm run build
```

### Documenting changes
- Update the nearest `README.md` with any new commands or behavior
- Update `RUNBOOK.md` if service start/stop commands change
- Update `DEPENDENCIES.md` if you add a package
- Update `CODING_RULES.md` if you establish a new constraint

---

## TODO/VERIFY Pattern

If you're uncertain about a command, path, or behavior, add:
```
# TODO/VERIFY: <what needs to be confirmed and where to look>
```

Do not guess. An incorrect command in documentation is worse than a placeholder.

---

## Source of Truth Order

1. `README.md` (root) — system architecture and quick start
2. `RUNBOOK.md` — exact service commands
3. `REPO_MAP.md` — authoritative folder/file inventory
4. `CODING_RULES.md` — this file's rules
5. `package.json` scripts — Node app commands
6. `pyproject.toml` / `requirements.txt` — Python deps
