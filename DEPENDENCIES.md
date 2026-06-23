# Dependencies

Dependency boundaries and classes per subproject. For exact versions, see each project's `requirements.txt` / `pyproject.toml` / `package.json`.

---

## Python Venvs Overview

| Venv | Projects | Key packages |
|------|---------|-------------|
| `.venv` | General scripts, `web_manager.py` | flask, requests, paramiko |
| `.venv-web-manager` | `webscraper_manager/` (Manager API) | fastapi, uvicorn, pydantic |
| `.venv-webscraper` | `webscraper/` (Ticket API + scraper) | fastapi, uvicorn, selenium, requests |

Bootstrap all: `python3 scripts/bootstrap_venvs.py`

---

## 1. Manager API (`.venv-web-manager`)

**Location:** `webscraper_manager/`
**Entry point:** `uvicorn webscraper_manager.api.server:app`

Requirements file: `webscraper_manager/requirements.txt`

Core deps:
- `fastapi` — web framework
- `uvicorn` — ASGI server
- `pydantic` — request/response models
- `python-dotenv` — `.env` loading
- `requests` — HTTP client (for proxying)

---

## 2. Ticket API + Scraper (`.venv-webscraper`)

**Location:** `webscraper/src/webscraper/`
**Entry points:**
- `uvicorn webscraper.ticket_api.app:app` (ticket API)
- `python -m webscraper --mode headless` (scraper worker)

Requirements files:
- `webscraper/pyproject.toml` (primary)
- Or `webscraper/requirements*.txt` if present

Core deps:
- `fastapi` — ticket API web framework
- `uvicorn` — ASGI server
- `pydantic` — models
- `requests` — ingest client HTTP calls (db_client.py)
- `selenium` — browser automation for scraping
- `beautifulsoup4` + `lxml` — HTML parsing
- `sqlite3` — stdlib, ticket database

**External requirements:**
- Chrome or Chromium browser installed
- ChromeDriver version must match browser version exactly

---

## 3. General Scripts (`.venv`)

**Location:** Root, `scripts/`, `web_manager.py`

Core deps:
- `flask` — web_manager.py
- `requests` — HTTP calls
- `paramiko` — SSH operations (deploy scripts)
- `python-dotenv` — env loading
- Standard library: `json`, `pathlib`, `subprocess`, `sqlite3`

---

## 4. FreePBX CLI Tools (Remote — Python 3.6.7)

**Location:** `freepbx-tools/bin/`
**Runtime:** Python 3.6.7 on production FreePBX hosts (not this server)

**All dependencies must be Python 3.6 compatible.**

Core deps (stdlib only where possible):
- `argparse` — CLI argument parsing
- `json` — data serialization
- `subprocess` — MySQL CLI calls (`mysql -NBe`)
- `os`, `sys`, `pathlib`

**Explicitly forbidden:**
- Any Python DB driver (`mysqlclient`, `pymysql`, `sqlalchemy`)
- Walrus operator (`:=`)
- Pattern matching (`match`/`case`)
- `from __future__ import annotations`
- Modern typing features

---

## 5. Node / Front-End Dependencies

### Manager UI (`manager-ui/`)
```
next: 14.2.x        → Next.js App Router
react: 18.3.x       → UI library
tailwindcss: 3.4.x  → Utility CSS
typescript: 5.5.x   → Type safety
```

### Ticket UI (`webscraper/ticket-ui/`)
Next.js app — see `webscraper/ticket-ui/package.json`

### Polycom / Yealink Config UI
```
react: 19.x              → UI library
typescript: 5.x          → Type safety
vite: 6.x               → Build tool
react-data-grid: 7.0.0-beta.59  → Excel-like import tables
papaparse                → CSV parsing
```

### HomeLab Tracker (`HomeLab_NetworkMapping/ccna-lab-tracker/`)
Next.js app — see its `package.json`

### Traceroute Visualizer (`traceroute-visualizer-main/`)
Next.js app — see its `package.json`

### FreePBX Deploy UI (`freepbx-deploy-ui/`)
Vite + React — see its `package.json`

---

## 6. System-Level Dependencies (Server)

| Package | Purpose |
|---------|---------|
| `apache2` | Reverse proxy + static serving |
| `certbot` + `python3-certbot-apache` | Let's Encrypt SSL |
| `nodejs` / `npm` | Front-end builds and production servers |
| `python3` (3.12.x) | Runtime for all Python services |
| `sqlite3` | SQLite CLI (debugging) |
| `openvpn3` | VPN client |
| `x11vnc` | VNC server (on virtual display) |
| `Xvfb` | Virtual framebuffer for headless Chrome |
| `openbox` | Minimal window manager for Xvfb session |
| `google-chrome` or `chromium-browser` | Browser for Selenium scraping |
| `chromium-chromedriver` | WebDriver (must match Chrome version) |
| `systemd` | Service management |

---

## What Is NOT Tracked Here

- Individual transitive npm/pip dependencies
- Virtual environment contents (derived, not source)
- Lock file details (see `package-lock.json`, `pyproject.toml`)

---

## Dependency Rules

1. **Never** add packages to a venv by hand — always update `requirements.txt` or `pyproject.toml` first
2. **Never** install pip packages into the system Python
3. **Never** use `npm install <package>` without also adding it to `package.json` (use `npm install --save`)
4. **Never** add modern Python syntax to `freepbx-tools/bin/` — it runs on Python 3.6
5. **Never** use Python DB drivers for MySQL on FreePBX hosts — use the `mysql` CLI via subprocess
