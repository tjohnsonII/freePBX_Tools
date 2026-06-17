# Running the Dev Stack

Canonical startup for the web manager/webscraper stack is now documented in `docs/startup.md`.

## Official Daily Dev Path (Webscraper / Manager Stack)

```bash
python scripts/run_all_web_apps.py --browser none --webscraper-mode combined --doctor --strict-readiness
```

Open dashboard automatically:

```bash
python scripts/run_all_web_apps.py --browser existing-profile --webscraper-mode combined --doctor --strict-readiness
```

Stop stack:

```bash
python scripts/stop_all_web_apps.py
```

> Legacy `npm run dev:stack` flows are not the canonical launcher contract for cross-service startup anymore.

---

## All App Ports

| App | Port | Type | Start command |
|-----|------|------|---------------|
| Traceroute UI | 3000 | Next.js | VS Code task: `dev: traceroute` |
| Deploy UI | 3003 | Vite/React | VS Code task: `dev: deploy-ui` |
| Polycom/Yealink Config | 3002 | Vite/React | VS Code task: `dev: polycom app` |
| Ticket UI (webscraper) | **3004** | Next.js | `python scripts/run_all_web_apps.py --browser none --webscraper-mode combined --doctor --strict-readiness` |
| Deploy Backend | 8002 | FastAPI | VS Code task: `dev: deploy-backend` |
| Ticket API (webscraper) | **8787** | FastAPI | started by `scripts/run_all_web_apps.py` |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TICKETS_DB_PATH` | `webscraper/var/db/tickets.sqlite` | Path to the ticket SQLite database |
| `TICKET_API_PROXY_TARGET` | `http://127.0.0.1:8787` | Backend URL used by the Next.js proxy |
| `PORT` | `3004` | UI port (set by the launcher flow; override to change) |
| `WEBSCRAPER_BROWSER` | `edge` | Browser for auth (`chrome` or `edge`) |
| `WEBSCRAPER_AUTH_MODE` | _(unset)_ | Set to `auto` to attempt automatic auth |

---

## DB Path

The canonical database location is:

```
webscraper/var/db/tickets.sqlite
```

The runtime module (`webscraper.lib.db_path`) resolves it in this priority:

1. `TICKETS_DB_PATH` env var
2. `TICKETS_DB` env var
3. Default: `webscraper/var/db/tickets.sqlite`

> The old path `webscraper/output/tickets.sqlite` is **retired**. If you have an existing DB there, move it:
> ```
> mkdir -p webscraper/var/db
> mv webscraper/output/tickets.sqlite webscraper/var/db/tickets.sqlite
> ```

---

## Stop / Restart

```bash
# Ctrl+C in the terminal running run_all_web_apps.py, or:
./scripts/kill_ports.sh          # Linux/WSL
scripts\kill_ports.bat           # Windows CMD

# Or via VS Code task:
# "stop: apps"
```

---

## Quick DB sanity check

```bash
python scripts/db_check.py
# or
bash scripts/db_sanity.sh
```

---

## Starting Everything at Once

For web manager + webscraper startup, use VS Code task **"start: apps"** (or **"start: apps (no browser)"**).
