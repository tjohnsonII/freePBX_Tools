# Running the Dev Stack

This is the single source of truth for starting, stopping, and understanding all local services.

---

## Official Daily Dev Path (Webscraper / Ticket Stack)

```
cd webscraper/ticket-ui
npm run dev:stack
```

This starts:
- **Ticket API** (FastAPI/uvicorn) at `http://127.0.0.1:8787`
- **Ticket UI** (Next.js) at `http://127.0.0.1:3004`

Stop with `Ctrl+C`.

> **Advanced path:** Use `webscraper_manager start webscraper` (via VS Code task "dev: webscraper stack") for the full managed stack with auth, worker, and detached logging.

---

## All App Ports

| App | Port | Type | Start command |
|-----|------|------|---------------|
| Traceroute UI | 3000 | Next.js | VS Code task: `dev: traceroute` |
| Deploy UI | 3003 | Vite/React | VS Code task: `dev: deploy-ui` |
| Polycom/Yealink Config | 3002 | Vite/React | VS Code task: `dev: polycom app` |
| Ticket UI (webscraper) | **3004** | Next.js | `cd webscraper/ticket-ui && npm run dev:stack` |
| Deploy Backend | 8002 | FastAPI | VS Code task: `dev: deploy-backend` |
| Ticket API (webscraper) | **8787** | FastAPI | started by `dev:stack` above |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TICKETS_DB_PATH` | `webscraper/var/db/tickets.sqlite` | Path to the ticket SQLite database |
| `TICKET_API_PROXY_TARGET` | `http://127.0.0.1:8787` | Backend URL used by the Next.js proxy |
| `PORT` | `3004` | UI port (set by `dev:stack`; override to change) |
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
# Ctrl+C in the terminal running dev:stack, or:
./scripts/kill_ports.sh          # Linux/WSL
scripts\kill_ports.bat           # Windows CMD

# Or via VS Code task:
# "dev: stop webscraper stack (freepbx-tools)"
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

VS Code task **"Start Everything + CLI"** launches all apps in parallel:
- Traceroute UI (3000)
- Deploy UI (3003)
- Polycom Config (3002)
- Deploy Backend (8002)
- Webscraper stack (8787 + 3004)
- CLI manager
