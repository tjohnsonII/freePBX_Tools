> **Status update (2026-03-19):** Canonical launcher is now `scripts/run_all_web_apps.py`. See `docs/startup.md` for current startup contract and VS Code tasks.

# Startup/Control Overhaul (devctl)

## Architecture summary

The startup flow is now built around one supervisor entrypoint: `scripts/devctl.py`.

- **Backend service:** `uvicorn webscraper.ticket_api.app:app` on `127.0.0.1:8787`
- **Frontend service:** `manager-ui` Next.js dev server on `127.0.0.1:3004`
- **State tracking:** `.webscraper_manager/devctl/state.json`
- **Logs:** `.webscraper_manager/devctl/logs/backend.log` and `.webscraper_manager/devctl/logs/frontend.log`
- **Readiness model:** backend must pass `/health`; frontend must return HTTP 200 on `/`

Startup order is strict: backend -> wait healthy -> frontend -> wait healthy.

## Commands

```bash
python scripts/devctl.py doctor
python scripts/devctl.py start
python scripts/devctl.py start-backend
python scripts/devctl.py start-frontend
python scripts/devctl.py stop
python scripts/devctl.py restart
python scripts/devctl.py status
python scripts/devctl.py logs --service backend --tail 200
python scripts/devctl.py login
python scripts/devctl.py auth-check
python scripts/devctl.py ingest --handle HANDLE
python scripts/devctl.py timeline --handle HANDLE
```

## Auth flow changes

- Auto-launch browser loop has been disabled by default (`AUTO_LAUNCH_DEBUG_CHROME=0`).
- Startup does not attempt login.
- `login` opens the secure customers page **once**.
- `auth-check` calls backend auth validation and returns explicit diagnostics.

## API additions/aliases

The backend now exposes these operational endpoints:

- `GET /health`
- `GET /auth/status`
- `POST /auth/open-login`
- `POST /auth/check`
- `POST /jobs/ingest-handle`
- `POST /jobs/build-timeline`
- `GET /handles`
- `GET /companies/{handle}`
- `GET /companies/{handle}/tickets`
- `GET /companies/{handle}/timeline`
- `GET /jobs/{job_id}`
- `GET /system/status`
- `GET /system/logs`

## Database migration/init

Initialize or migrate schema:

```bash
python scripts/init_ticket_kb_db.py
# optional
python scripts/init_ticket_kb_db.py --db /path/to/tickets.sqlite
```

This upgrades/creates these tables used for company-level KB timeline generation:

- `companies`
- `tickets`
- `ticket_events`
- `narratives`
- `artifacts`
- `company_timeline`
- `resolution_patterns`

## Troubleshooting

1. **Backend not ready**
   - Run `python scripts/devctl.py logs --service backend`
   - Validate Python env and imports with `python scripts/devctl.py doctor`

2. **Frontend not ready**
   - Run `python scripts/devctl.py logs --service frontend`
   - Ensure dependencies in `manager-ui` are installed

3. **Auth check fails**
   - Run `python scripts/devctl.py login` and authenticate manually
   - Re-run `python scripts/devctl.py auth-check`

4. **Ingest jobs queued but no tickets appear**
   - Confirm auth first
   - Check job status via `GET /jobs/{job_id}`
   - Check backend logs and `/system/logs`

## Legacy startup scripts to deprecate

These scripts can be phased out in favor of `devctl` for day-to-day operator workflow:

- `scripts/run_all_web_apps.py`
- `scripts/run_web_manager_app.py`
- `scripts/run_webscraper_app.py`
- `scripts/run_manager_ui_app.py`
- `.vscode` task aliases that shell out to the above scripts for this stack

## Migration plan

1. Start using `python scripts/devctl.py doctor` in preflight checks.
2. Replace local docs/task bindings from old launchers to `devctl` commands.
3. Validate backend readiness and auth with `status` + `auth-check`.
4. Move handle ingestion flows to `ingest --handle`.
5. Generate company timelines using `timeline --handle`.
6. After one sprint of stable runs, archive old launch scripts behind a `legacy/` folder or remove them.
