# System Architecture

Deep-dive reference for how all components fit together.

---

## Overview

This is a monorepo that runs on a single always-on Ubuntu Linux server with a companion client scraper on a laptop. The server hosts multiple web apps behind Apache with SSL. The client laptop connects to the 123.net portal via VPN, scrapes data, and ships it to the server via a secured HTTP ingest API.

---

## Physical Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  SERVER  (Ubuntu Linux, 192.168.100.10)                         │
│                                                                  │
│  Apache (:443/:80)  ←── certbot SSL                             │
│    ├── tickets.123hostedtools.com  ──► Next.js :3005            │
│    ├── manager-api.123hostedtools.com ► FastAPI :8787           │
│    ├── (other subdomains)           ──► :3006, :3011            │
│    └── /polycom/* (static)          ──► dist/ on disk           │
│                                                                  │
│  Internal services (127.0.0.1 only):                            │
│    :3004  Manager UI      (Next.js)                             │
│    :3005  Ticket UI       (Next.js)                             │
│    :3006  Traceroute UI   (Next.js)                             │
│    :3011  HomeLab Tracker (Next.js)                             │
│    :5000  FreePBX Web Mgr (Flask)                               │
│    :8787  Manager API     (FastAPI / uvicorn)                   │
│    :8788  Ticket API      (FastAPI / uvicorn)                   │
│                                                                  │
│  systemd: freepbx-tools.service  (auto-restart on crash)        │
│  Xvfb :99 + x11vnc :5900  (virtual display for Chrome)         │
│  Chrome Remote Desktop :20  (remote access)                     │
└─────────────────────────────────────────────────────────────────┘
            ▲
            │  HTTPS POST /api/ingest/*
            │  Header: X-Ingest-Key: <shared secret>
            │
┌─────────────────────────────────────────────────────────────────┐
│  CLIENT LAPTOP                                                   │
│  • Connected to 123.net portal via OpenVPN (tun0)               │
│  • Runs: ./start_client.sh  (CLIENT_MODE=1)                     │
│  • Browser automation (Chrome/Selenium) → 123.net portal        │
│  • Scraped data → POST to server ingest API                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Services In Depth

### Manager API (`:8787`)

**Stack:** FastAPI + uvicorn | **Venv:** `.venv-web-manager`

Entry point: `webscraper_manager/api/server.py` → `create_app()`

The API is the brains of the server. It:
- Starts/stops individual services
- Streams live logs to the Manager UI
- Inspects the SQLite database
- Monitors the scraper auth state
- Manages the ticket pipeline
- Provides system health metrics

Route groups (`webscraper_manager/api/routes/`):

| Module | Routes | Purpose |
|--------|--------|---------|
| `health.py` | `GET /api/health` | Liveness probe |
| `services.py` | `/api/services/*` | Service management |
| `auth.py` | `/api/auth/*` | Scraper auth status |
| `db.py` | `/api/db/*` | DB inspection |
| `logs.py` | `/api/logs/*` | Log streaming |
| `tickets.py` | `/api/tickets/*` | Ticket pipeline |
| `manager.py` | `/api/manager/*` | Orchestration |
| `system.py` | `/api/system/*` | System info |
| `webscraper.py` | `/api/webscraper/*` | Scraper control |
| `diagnostics.py` | `/api/diagnostics/*` | Diagnostics |

Business logic lives in `webscraper_manager/api/services/`:
- `StateStore` — persistent state (run_state.json)
- `EventBus` — JSONL event log (`.webscraper_manager/events.jsonl`)
- `CommandRunner` — shell command execution
- `AuthInspector` — browser auth session state
- `TicketPipelineService` — scrape job orchestration
- `DBInspector` — SQLite queries
- `SystemInspector` — CPU/mem/disk/process info

---

### Manager UI (`:3004`)

**Stack:** Next.js 14 App Router + Tailwind CSS + TypeScript

App Router pages (`manager-ui/app/`):
- `/dashboard` — overview of all service statuses
- `/services` — start/stop/restart individual services
- `/auth` — Chrome auth session status and management
- `/handles` — browse customer handles, trigger per-handle scrapes
- `/tickets` — ticket pipeline status and job history
- `/logs` — live log tail from any service
- `/system` — CPU, memory, disk
- `/database` — SQLite table browser

Browser fetches go to `NEXT_PUBLIC_API_BASE` (set to `https://manager-api.123hostedtools.com` at build time by `FULL_START.sh`).

---

### Ticket API (`:8788`)

**Stack:** FastAPI + uvicorn + SQLite | **Venv:** `.venv-webscraper`

Entry point: `webscraper/src/webscraper/ticket_api/app.py`

Two modes, selected at startup by `CLIENT_MODE` env var:

**Server mode** (`CLIENT_MODE` unset or `0`):
- Imports `db.py` — writes directly to local `tickets.sqlite`
- Serves ticket data to Ticket UI
- Exposes `/api/ingest/*` for client POSTs

**Client mode** (`CLIENT_MODE=1`):
- Imports `db_client.py` instead of `db.py`
- All writes → HTTP POST to `INGEST_SERVER_URL`
- Reads → proxy to `INGEST_SERVER_URL` GET endpoints
- No local SQLite

Key endpoints:
```
GET  /api/health
GET  /api/handles       query: q, limit, offset
GET  /api/tickets/{handle}
GET  /api/jobs
POST /api/ingest/tickets   (X-Ingest-Key required from non-localhost)
POST /api/ingest/handles   (X-Ingest-Key required from non-localhost)
POST /api/scrape/run
POST /api/scrape/run-e2e
```

---

### Ticket UI (`:3005`)

**Stack:** Next.js (pages in `webscraper/ticket-ui/app/`)

Public URL: `https://tickets.123hostedtools.com`

Pages:
- `/` — handle list with search
- `/handles/[handle]` — handle detail + ticket history
- `/tickets` — all tickets
- `/vpbx` — VPBX data browser
- `/logs` — log viewer
- `/noc-queue` — NOC queue
- `/phone-configs` — phone configuration reference
- `/site-config` — site configuration view

---

### Ingest API (Client → Server Protocol)

The ingest API is how the client scraper sends data to the server without direct DB access.

**Authentication:** HMAC compare via `X-Ingest-Key` header. Key is set in `.env` on the server as `INGEST_API_KEY`. If the env var is empty, ingest is restricted to localhost (safe for local dev).

**Client side:** `db_client.py` wraps all write operations as HTTP POSTs. `_post()` and `_get()` attach the key header automatically from `INGEST_API_KEY` env var.

**Server side:** `ingest_routes.py` validates the header with `hmac.compare_digest()` (constant-time compare, prevents timing attacks) then delegates to the local `db.py` functions.

Ingest endpoints:
```
POST /api/ingest/tickets    body: {handle, tickets: [...]}
POST /api/ingest/handles    body: {rows: [...]}
```

---

## Data Flow: Scraping Pipeline

```
1. Operator triggers scrape (RESTART.sh worker / Manager UI)
       │
2. Scraper Worker starts (python -m webscraper --mode headless)
       │
3. Opens Chrome on Xvfb :99 or :20 (CRD display)
       │
4. Authenticates to 123.net portal (auth/browser modules)
       │
5. Iterates handles from configs/handles/handles_master.txt
       │
6. For each handle:
   ├── Server mode: write tickets to local SQLite via db.py
   └── Client mode: POST to /api/ingest/* on server
       │
7. Ticket API serves data to Ticket UI on request
```

---

## Startup Flow

### Boot (systemd)
```
freepbx-tools.service
  └── ExecStart: scripts/start_services.sh
        1. Load .env
        2. Start Xvfb :99 + openbox + x11vnc :5900
        3. Stop existing services + kill ports
        4. Apache reload/start
        5. python3 scripts/run_all_web_apps.py --webscraper-mode api --extras
```

### Manual Full Start
```
FULL_START.sh
  1. Git pull (rebase)
  2. Rebuild front ends (MD5 source hash, skip if unchanged)
     ├── manager-ui      → .next/
     ├── ticket-ui       → .next/
     ├── homelab         → .next/
     ├── traceroute      → .next/
     ├── deploy-ui       → dist/
     └── polycom         → dist/
  3. Apache systemd override (Restart=on-failure)
  4. Stop all services + kill ports
  5. Apache reload (certbot renewal if config invalid)
  6. run_all_web_apps.py (same as boot)
  7. Health check each port (20 second timeout)
```

---

## Branch Strategy

```
main ──────────────────────────────────────────────► source of truth
  │
  ├── server ←── rebase from main periodically
  │     └── server-specific: systemd configs, server .env handling
  │
  └── client ←── rebase from main periodically
        └── client-specific: start_client.sh, CLIENT_MODE defaults
```

Develop on `main`. When deploying to server/client, rebase their branch from main and push:
```bash
git checkout server && git rebase main && git push origin server --force-with-lease
git checkout client && git rebase main && git push origin client --force-with-lease
```

The server auto-pulls on `FULL_START.sh` using the current checked-out branch.

---

## Python Venv Isolation

Three venvs, strict separation:

```
.venv               → general scripts, freepbx-tools, web_manager.py
.venv-web-manager   → webscraper_manager/ (Manager API)
.venv-webscraper    → webscraper/ (Ticket API + scraper + selenium)
```

The three venvs exist because:
- Selenium + browser deps conflict with FastAPI/uvicorn versions
- Manager API needs different versions than the scraper
- Separating them avoids silent dependency breakage

Bootstrap all three: `python3 scripts/bootstrap_venvs.py`

---

## Front-End Build System

`FULL_START.sh` uses a smart rebuild function:
1. Compute MD5 hash of all `.ts`, `.tsx`, `.css`, `.js`, `.mjs`, config files (excluding build outputs)
2. Compare to stored `.src_hash` file
3. If hash changed (or `--force-rebuild`): `npm ci && npm run build`, write new hash
4. If unchanged: skip (saves 2-5 min per app)

This means front ends only rebuild when source actually changes, not on every server restart.

---

## Apache Reverse Proxy

Apache proxies external domains to internal localhost ports. Key configuration pattern:

```apache
# Example vhost (generated by scripts/generate_vhosts.py)
<VirtualHost *:443>
    ServerName tickets.123hostedtools.com
    ProxyPass        / http://127.0.0.1:3005/
    ProxyPassReverse / http://127.0.0.1:3005/
    SSLEngine on
    ...
</VirtualHost>
```

Polycom Config UI is served as static files (no proxy):
```apache
Alias /polycom /var/www/freePBX_Tools/PolycomYealinkMikrotikSwitchConfig-main/.../dist
```

Cert management: certbot + Let's Encrypt. `FULL_START.sh` attempts `certbot renew --force-renewal` if `apache2ctl configtest` fails (usually a cert expiry).

---

## Security Model

- **Ingest API:** HMAC constant-time compare on `X-Ingest-Key`. Key lives in `.env` (gitignored). If key is unset, only localhost is allowed.
- **Apache:** All public traffic via HTTPS/443. Internal services bind `127.0.0.1` only.
- **Pre-commit:** `gitleaks` runs on every commit — blocks secret leakage.
- **Venvs:** Isolated — a compromised dep in one venv can't affect others.
- **Systemd:** Service runs as `root` (required for Apache ops, port binding). Worker runs as `tim2` via `sudo -H -u tim2`.

See `docs/SECURITY.md` for full security guidance.
