# freePBX Tools Suite

A production monorepo running on an always-on Ubuntu server. It combines a VoIP management toolkit, a web scraping pipeline, and multiple React/Next.js dashboards — all served behind Apache and managed by systemd.

---

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Source of truth — contains everything |
| `server` | Server deployment — rebases from main |
| `client` | Client (laptop) deployment — rebases from main |

Always develop on `main` and rebase `server`/`client` from it.

---

## System Architecture

```
        Client Laptop (VPN)                  Server (192.168.100.10)
        ─────────────────                    ──────────────────────────────────────
        start_client.sh                      Apache (443/80)  ──── SSL via certbot
           │  CLIENT_MODE=1                       │
           │  INGEST_SERVER_URL=...               ├─ tickets.123hostedtools.com ──► Ticket UI :3005
           │                                      ├─ manager-api.123hostedtools.com ► Manager API :8787
           └──► POST /api/ingest/*               ├─ (other subdomains)
                X-Ingest-Key: <shared>            │
                                                  ├─► Manager UI           :3004  (Next.js)
                                                  ├─► Ticket API           :8788  (FastAPI + SQLite)
                                                  ├─► Ticket UI            :3005  (Next.js)
                                                  ├─► Traceroute UI        :3006  (Next.js)
                                                  ├─► HomeLab Tracker      :3011  (Next.js)
                                                  ├─► FreePBX Web Mgr     :5000  (Flask)
                                                  └─► Polycom Config UI    static dist (Apache)

        systemd: freepbx-tools.service → scripts/start_services.sh (boot)
        Manual:  sudo ./FULL_START.sh  (full rebuild + start)
        Quick:   sudo ./RESTART.sh     (interactive menu, per-service restart)
```

---

## Quick Start (Server)

```bash
# Full rebuild and start (run after code changes or on a fresh clone)
sudo ./FULL_START.sh

# Or force-rebuild all front ends even if source hasn't changed
sudo ./FULL_START.sh --force-rebuild

# Interactive restart menu (single services, no rebuild)
sudo ./RESTART.sh

# Non-interactive — restart one service
sudo ./RESTART.sh manager-api
sudo ./RESTART.sh ticket-api
sudo ./RESTART.sh worker
sudo ./RESTART.sh apache
```

See **RUNBOOK.md** for complete service-by-service commands and health checks.

---

## Applications at a Glance

| App | Path | Port | Stack | Notes |
|-----|------|------|-------|-------|
| Manager UI | `manager-ui/` | 3004 | Next.js 14 | Service dashboard, auth, DB inspector |
| Manager API | `webscraper_manager/` | 8787 | FastAPI | REST backend for Manager UI |
| Ticket UI | `webscraper/ticket-ui/` | 3005 | Next.js | Browse scraped ticket history |
| Ticket API | `webscraper/` | 8788 | FastAPI + SQLite | Scrape data store + ingest endpoint |
| Traceroute Visualizer | `traceroute-visualizer-main/` | 3006 | Next.js | Network path visualization |
| HomeLab Tracker | `HomeLab_NetworkMapping/ccna-lab-tracker/` | 3011 | Next.js | CCNA lab study tracker |
| Polycom/Yealink Config | `PolycomYealinkMikrotikSwitchConfig-main/` | static | Vite + React | Phone/switch config generator |
| FreePBX Web Manager | `web_manager.py` | 5000 | Flask | FreePBX diagnostic UI |
| FreePBX CLI Tools | `freepbx-tools/` | — | Python 3.6 | Run on FreePBX servers as root |

---

## Client / Server Split

The scraper runs on a **client laptop** connected to the 123.net portal over VPN. The server cannot reach the portal directly. Data flows like this:

1. Client runs `./start_client.sh` (sets `CLIENT_MODE=1`)
2. Scraper authenticates to 123.net via browser automation
3. Scraped tickets/handles POST to `https://manager-api.123hostedtools.com/api/ingest/*`
4. Requests carry `X-Ingest-Key` header — server validates with HMAC compare
5. Server writes to SQLite (`webscraper/var/db/tickets.sqlite`)

Required env vars for the client:
```bash
INGEST_SERVER_URL=http://192.168.30.19:8788   # or public URL
INGEST_API_KEY=<shared secret>                 # must match server's .env
```

Copy `.env.example` → `.env` and fill in values. The `.env` file is gitignored.

---

## Virtual Environments

Three separate Python venvs live at the repo root:

| Venv | Used by | Activate |
|------|---------|---------|
| `.venv` | General scripts, freepbx-tools | `source .venv/bin/activate` |
| `.venv-web-manager` | Manager API (`webscraper_manager/`) | `source .venv-web-manager/bin/activate` |
| `.venv-webscraper` | Ticket API + scraper (`webscraper/`) | `source .venv-webscraper/bin/activate` |

Never cross-activate. See **DEPENDENCIES.md** for what each venv contains.

---

## Secrets and Config

| File | Status | Purpose |
|------|--------|---------|
| `.env` | gitignored, must create | `INGEST_API_KEY`, `CLIENT_MODE`, etc. |
| `.env.example` | committed | Template for `.env` |
| `webscraper/var/chrome-profile/` | gitignored | Chrome profile used by scraper |
| `webscraper/var/db/tickets.sqlite` | gitignored | Scraped ticket database |

Never commit `.env` or any credentials. See `docs/SECURITY.md`.

---

## Documentation Index

| Doc | What it covers |
|-----|---------------|
| **RUNBOOK.md** | Exact run commands for every service, health checks, log paths |
| **REPO_MAP.md** | Every folder, what it is, what it's not |
| **ENVIRONMENT.md** | Server OS, venvs, Node versions, shell requirements |
| **DEPENDENCIES.md** | Python/Node dependencies per subproject |
| **KNOWN_ISSUES.md** | Recurring problems and their workarounds |
| **CODING_RULES.md** | Safe change guardrails for humans and AI agents |
| **AGENTS.md** | Rules for AI coding agents (Codex, Claude, Copilot) |
| **docs/ARCHITECTURE.md** | Deep dive: services, data flow, ingest API, branch strategy |
| **docs/SECURITY.md** | Secrets management, ingest auth, pre-commit hooks |

---

## Startup / Boot

systemd starts everything automatically on boot:

```
freepbx-tools.service
  → scripts/start_services.sh
      • Xvfb :99 + x11vnc (virtual display for Chrome scraper)
      • python3 scripts/run_all_web_apps.py
          ▸ Manager API  :8787
          ▸ Manager UI   :3004
          ▸ Ticket API   :8788
          ▸ Ticket UI    :3005
          ▸ Traceroute   :3006
          ▸ HomeLab      :3011
          ▸ Web Manager  :5000
      • Apache reload
```

`FULL_START.sh` adds: git pull, smart front-end rebuild (MD5 source hash), certbot renewal if Apache config is invalid.

---

## Git Safety

Pushes are guarded by:
- `pre-commit` hooks (gitleaks secret scanning)
- `scripts/secure_push.py` (additional checks)

Never bypass with `--no-verify`.
