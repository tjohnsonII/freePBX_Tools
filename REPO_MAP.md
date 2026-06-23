# FreePBX Tools Suite — Repository Map

Every folder in this repo, what it is, and what it is not.

---

## Top-Level Files

| File | Purpose |
|------|---------|
| `FULL_START.sh` | Full stack startup: git pull → rebuild front ends → start all services. Run as root. |
| `RESTART.sh` | Interactive per-service restart menu (or non-interactive: `./RESTART.sh <service>`). Root required. |
| `start_client.sh` | **Client-only.** Starts scraper in `CLIENT_MODE=1` — sends data to remote server. |
| `start_worker.sh` | Starts the scraper worker directly (server mode). |
| `web_manager.py` | Flask app: FreePBX diagnostic web UI, port 5000. |
| `web_requirements.txt` | Pip deps for `web_manager.py`. |
| `pyproject.toml` | Root-level Python project config (linting, pytest). |
| `pytest.ini` | Pytest configuration. |
| `pyrightconfig.json` | Pyright type checker config for multi-venv monorepo. |
| `.env` | **Gitignored.** Local secrets: `INGEST_API_KEY`, `CLIENT_MODE`, etc. |
| `.env.example` | Committed template — copy to `.env` and fill in. |
| `config.example.py` | Example config (legacy). |
| `scraper_config.example.py` | Scraper config template. |
| `verify_commit_safety.py` | Pre-push safety verification script. |
| `.pre-commit-config.yaml` | Pre-commit hooks (gitleaks, etc.). |
| `.secrets.baseline` | gitleaks baseline — prevents false positives. |
| `freepbx-tools-suite.code-workspace` | VS Code multi-root workspace file. |

---

## Applications (Source Code)

### `manager-ui/`
**Next.js 14 dashboard UI** — Port 3004

The primary web dashboard for managing all server services. Built with Next.js App Router, Tailwind CSS.

Pages/routes:
- `/dashboard` — Service status overview
- `/services` — Start/stop individual services
- `/auth` — Scraper auth/session management
- `/handles` — Browse and manage customer handles
- `/tickets` — Ticket pipeline status
- `/logs` — Live log viewer
- `/system` — System health
- `/database` — SQLite inspector

Built at startup by `FULL_START.sh`. Served by `npm run start` on port 3004.

---

### `webscraper_manager/`
**FastAPI Manager API** — Port 8787

REST backend that powers Manager UI. Venv: `.venv-web-manager`.

```
webscraper_manager/
├── api/
│   ├── server.py          Entry point — FastAPI app factory
│   ├── routes/            One file per route group:
│   │   ├── auth.py        Auth session status
│   │   ├── db.py          Database inspection
│   │   ├── diagnostics.py System diagnostics
│   │   ├── health.py      GET /api/health
│   │   ├── logs.py        Log streaming
│   │   ├── manager.py     Orchestration
│   │   ├── services.py    Service start/stop/status
│   │   ├── system.py      System info
│   │   ├── tickets.py     Ticket pipeline
│   │   └── webscraper.py  Scraper control
│   └── services/          Business logic layer
│       ├── auth_inspector.py
│       ├── command_runner.py
│       ├── db_inspector.py
│       ├── event_bus.py
│       ├── state_store.py
│       ├── system_inspector.py
│       └── ticket_pipeline.py
├── cli.py                 CLI entrypoint
└── requirements.txt       Pip deps (install into .venv-web-manager)
```

Run: `uvicorn webscraper_manager.api.server:app --host 127.0.0.1 --port 8787`

---

### `webscraper/`
**Scraper + Ticket API** — Port 8788

Two things in one package:
1. **Selenium scraper** — authenticates to 123.net portal, scrapes ticket history
2. **FastAPI ticket API** — stores/serves ticket data; also receives ingest from client

```
webscraper/
├── src/webscraper/            Python package (venv: .venv-webscraper)
│   ├── ticket_api/
│   │   ├── app.py             FastAPI app — ticket API + ingest router
│   │   ├── ingest_routes.py   POST /api/ingest/* — receives data from client
│   │   ├── db.py              Local SQLite write path (server mode)
│   │   ├── db_client.py       Remote write path (CLIENT_MODE=1)
│   │   ├── db_core.py         Shared DB utilities
│   │   ├── db_init.py         Schema init
│   │   └── models.py          Pydantic models
│   ├── auth/                  Browser authentication logic
│   ├── browser/               Selenium browser management
│   ├── scrape/                Scraping orchestration
│   ├── parsers/               HTML parsers for ticket data
│   ├── kb/                    Knowledge base utilities
│   ├── handles_loader.py      Load handle list from configs/
│   ├── paths.py               Canonical path resolution
│   └── logging_config.py      Logging setup
├── ticket-ui/                 Next.js UI — port 3005
│   └── app/
│       ├── handles/           Handle browser
│       ├── tickets/           Ticket history view
│       ├── vpbx/              VPBX data browser
│       ├── logs/              Log viewer
│       └── noc-queue/         NOC queue view
├── configs/handles/           Handle lists (handles_master.txt)
├── var/                       Runtime data (gitignored)
│   ├── db/tickets.sqlite      The database
│   └── chrome-profile/        Chrome session data
└── docs/                      Architecture and review docs
```

Run ticket API: `uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8788`

---

### `PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/`
**Polycom / Yealink / Mikrotik Config Generator** — Static Vite app

Served as a static `dist/` by Apache. No server required at runtime.

Tabs:
- **Polycom / Yealink Phone Configs** — model-specific config code generation
- **VPBX / FPBX / Stretto Import** — bulk CSV import/export with react-data-grid tables (200 row default, smart export trimming)
- **DIDs Import** — DID routing import
- **Mikrotik / Switch** — router/switch config templates

Built by `FULL_START.sh` → `npm run build` → served from `dist/`.

---

### `traceroute-visualizer-main/traceroute-visualizer-main/`
**Traceroute Visualizer** — Port 3006

Next.js UI for visualizing network traceroute paths. Nested folder structure is intentional (do not flatten).

---

### `HomeLab_NetworkMapping/ccna-lab-tracker/`
**HomeLab / CCNA Lab Tracker** — Port 3011

Next.js app for tracking CCNA lab study progress. SQLite-backed.

---

### `freepbx-deploy-ui/` + `freepbx-deploy-backend/`
**FreePBX Deploy UI** — Static Vite dist

UI + FastAPI backend for deploying freepbx-tools to FreePBX servers. Backend is local-only (binds 127.0.0.1).

---

### `freepbx-tools/`
**FreePBX CLI Tools** — deployed to FreePBX servers

Python 3.6 tools installed on production FreePBX hosts under `/usr/local/123net/freepbx-tools/`. Must remain Python 3.6 compatible. Run as root.

---

## Supporting Directories

### `scripts/`
Operational scripts and launchers:

| Script | Purpose |
|--------|---------|
| `start_services.sh` | Lean startup (no rebuild) — called by systemd |
| `run_all_web_apps.py` | Python launcher for all services |
| `stop_all_web_apps.py` | Graceful shutdown of all services |
| `bootstrap_venvs.py` | Create/populate all three venvs |
| `install_systemd.sh` | Install systemd unit files |
| `db_check.py` | SQLite database health check |
| `scrape_all_handles.py` | Bulk scrape all handles |
| `devctl.py` | Developer control plane |
| `generate_vhosts.py` | Apache vhost config generator |
| `doctor_devs.py` | Developer environment diagnostics |
| `validate_handles_csv.py` | Validate handles input files |

### `systemd/`
Systemd unit files (owned by root):

| File | Purpose |
|------|---------|
| `freepbx-tools.service` | Main service — starts everything on boot |
| `freepbx-tools-watchdog.service` | Watchdog that auto-restarts crashed services |
| `freepbx-nightly-scrape.service` | Nightly scrape job |
| `freepbx-nightly-scrape.timer` | Timer for nightly scrape |

### `docs/`
Architecture and operational reference docs. See `docs/ARCHITECTURE.md` for the authoritative design doc.

### `archive/`
Old docs and scripts no longer in active use. Do not reference for current behavior.

### `mikrotik/`
Mikrotik router config generation scripts.

### `templates/`
Config and text templates used by various tools.

### `static/`
Static assets served by Apache or Flask.

---

## Runtime / Generated Directories (not source code)

| Path | What it is |
|------|-----------|
| `var/` | Runtime logs, state files, web-app-launcher state |
| `webscraper/var/` | Scraper runtime: Chrome profile, SQLite DB, logs |
| `.venv/` | General Python venv |
| `.venv-web-manager/` | Manager API Python venv |
| `.venv-webscraper/` | Ticket API + scraper Python venv |
| `manager-ui/.next/` | Next.js build output |
| `webscraper/ticket-ui/.next/` | Next.js build output |
| `PolycomYealinkMikrotikSwitchConfig-main/.../dist/` | Vite build output |
| `node_modules/` | npm packages (never commit) |
| `scraped_tickets/` | Legacy scraped data (not current DB) |
| `__pycache__/` | Python bytecode cache |
| `.webscraper_manager/` | Manager state/event log |
| `CAGE_INFO` | Customer cage reference data |
| `cisco switches/` | Switch config references |
| `freePBX_Dial_Plans/` | Dial plan reference files |

---

## Golden Rules

1. Never treat `var/`, `dist/`, `.next/`, or `node_modules/` as source.
2. Never flatten the nested `...-main/...-main/` folder structures.
3. Never activate one venv from another project's context.
4. Never commit `.env`, SQLite databases, or Chrome profile data.
5. `freepbx-tools/bin/` must stay Python 3.6 compatible.
