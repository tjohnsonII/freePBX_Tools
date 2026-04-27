> **NOTE (2026-04-27):** This document covers `scripts/run_all_web_apps.py` which is still the underlying launcher called by `FULL_START.sh` and `scripts/start_services.sh`. For the full current startup reference including `FULL_START.sh`, `RESTART.sh`, systemd, and health checks, see **RUNBOOK.md**. Windows `.bat` wrappers listed below are not used on the server.

# Canonical Startup Guide (Web Manager + Webscraper)

## Startup contract (single source of truth)
Use `scripts/run_all_web_apps.py` as the only canonical launcher for web manager + webscraper stack startup.

### Canonical commands

No browser:
```bash
python scripts/run_all_web_apps.py --browser none --webscraper-mode combined --doctor --strict-readiness
```

Open dashboard in existing browser profile:
```bash
python scripts/run_all_web_apps.py --browser existing-profile --webscraper-mode combined --doctor --strict-readiness
```

Inspect mode:
```bash
python scripts/run_all_web_apps.py --browser none --webscraper-mode combined --inspect --doctor
```

Stop everything:
```bash
python scripts/stop_all_web_apps.py
```

---

## Supported launcher arguments

Primary options:
- `--no-bootstrap`
- `--doctor`
- `--no-port-cleanup`
- `--dry-run`
- `--verbose`
- `--inspect`
- `--readiness-timeout`
- `--strict-readiness`
- `--allow-open-port-fallback`
- `--webscraper-mode {worker,ui,api,combined,none}`
- `--browser {none,existing-profile,persistent-profile}`
- `--browser-profile-directory`
- `--browser-user-data-dir`
- `--dashboard-url`
- `--status-file`

Deprecated flag guardrail:
- `--open-browser` now fails fast with: `--open-browser is deprecated; use --browser existing-profile`

---

## Startup phases and deterministic behavior

Each run executes clearly separated phases:
1. `bootstrap`
2. `doctor` (optional)
3. `cleanup`
4. `launch`
5. `readiness`
6. `browser`

Readiness reporting is aggregated per service with:
- started/not started
- PID
- target port
- readiness probe URL
- readiness status + reason

If any service is degraded and `--strict-readiness` is set, launcher exits nonzero.

---

## Status file
Every run writes a structured JSON status file (default):

`var/web-app-launcher/startup_summary.json`

The payload includes:
- timestamp
- args used
- services attempted
- services started
- service-level readiness and ports
- browser launch result
- warnings/failures

Use this file for tooling integrations and post-run diagnostics.

---

## VS Code task standard
Use only these tasks:
- `start: apps`
- `start: apps (no browser)`
- `start: inspect`
- `doctor: apps`
- `stop: apps`

All tasks route through `scripts/run_all_web_apps.py` (or `scripts/stop_all_web_apps.py` for stop).

---

## Windows wrapper standardization

Wrappers are now aligned to the canonical launcher:
- `scripts/start_everything.bat` → calls `scripts/run_all_web_apps.py`
- `scripts/kill_ports.bat` → delegates to `scripts/stop_all_web_apps.py`

No wrapper should call legacy browser flags.

---

## Terminal behavior

For VS Code, tasks are configured to run in the integrated terminal (`panel: shared`) for predictable process ownership and easier debugging.

Legacy `start`/external-window spawning is not used by canonical startup tasks.

---

## Troubleshooting quick checks

1. Inspect stack wiring:
```bash
python scripts/run_all_web_apps.py --inspect --browser none --webscraper-mode combined
```

2. Dry-run doctor + plan:
```bash
python scripts/run_all_web_apps.py --doctor --dry-run --browser none --webscraper-mode combined
```

3. Review status and logs:
- `var/web-app-launcher/startup_summary.json`
- `var/web-app-launcher/logs/*.log`

---

## Audit inventory (startup entry points and references)

Primary launcher files:
- `scripts/run_all_web_apps.py` (canonical)
- `scripts/run_web_manager_app.py`
- `scripts/run_manager_ui_app.py`
- `scripts/run_webscraper_app.py`
- `scripts/stop_all_web_apps.py`

VS Code configs:
- `.vscode/tasks.json`
- `.vscode/launch.json`

Windows wrappers:
- `scripts/start_everything.bat`
- `scripts/kill_ports.bat`
- `scripts/run_py.bat`
- `scripts/doctor_cmd.bat`

Legacy/deprecated reference identified during audit:
- `.vscode/tasks.json` previously used `--open-browser`.
