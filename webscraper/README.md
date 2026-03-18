# Ultimate Scraper – Quickstart

This scraper drives Chrome via Selenium to search customer handles, capture page HTML, enumerate ticket links, and save structured JSON outputs. It’s designed to run interactively (visible browser) so you can complete any VPN/SSO/MFA steps.

## Prerequisites
- Windows with Google Chrome installed
- Python 3.8+ available on PATH (`python --version`)

Install packages:

```cmd
pip install selenium beautifulsoup4 lxml
```

## Windows CLI quickstart (Git Bash vs PowerShell)
- If you are in **Git Bash**, run git commands as shown there.
- If you are in **PowerShell**, run commands **without** a leading `$` (for example, `git status`).
- Do **not** paste the shell prompt line (for example `tjohnson@... MINGW64 ...`) into PowerShell.

PowerShell test commands (no `$` prefix):

```powershell
.\.venv-webscraper\Scripts\python.exe -m pip install -U pip pytest
.\.venv-webscraper\Scripts\python.exe -m pytest -q
```

You can also run:

```powershell
.\scripts\run_tests.ps1
```

## Testing
Run unit tests from repo root (Windows venv example):

```powershell
.\.venv-webscraper\Scripts\python.exe -m pytest
```

Unit tests are restricted to `webscraper/tests` via the repo-root `pytest.ini` (`testpaths = webscraper/tests`, `python_files = test_*.py`, `addopts = -q`). This prevents accidental pytest collection of environment-dependent scripts.

Manual/integration scripts live in `scripts/webscraper_manual_tests/` and should be run directly, for example:

```powershell
.\.venv-webscraper\Scripts\python.exe scripts\webscraper_manual_tests\smoke_manual.py
.\.venv-webscraper\Scripts\python.exe scripts\webscraper_manual_tests\cookie_manual.py
.\.venv-webscraper\Scripts\python.exe scripts\webscraper_manual_tests\dashboard_manual.py
```

Manual script environment variables:
- `EDGE_PROFILE_DIR` (required by cookie/storage/CDP scripts)
- `EDGE_PROFILE_NAME` (optional, defaults to `Default`)
- `FREEPBX_HOST` (optional for dashboard script, defaults to `69.39.69.102`)
- `FREEPBX_USER` and `FREEPBX_PASSWORD` (required for dashboard unless provided via local `config.py`)


## Quick Start (cmd-only, domain-locked Windows)
From repo root (no PowerShell), use the venv activation script and module entrypoints:

```cmd
py -3 -m venv .venv-webscraper
.venv-webscraper\Scripts\python.exe -m pip install -U pip
.venv-webscraper\Scripts\pip.exe install -r webscraper\requirements.txt
call .venv-webscraper\Scripts\activate.bat
python -m webscraper.smoke_test
python -m webscraper.ultimate_scraper --help
```

## Default handle behavior (no prompts)
By default the scraper now reads handles from `./123NET Admin.csv` and scrapes **all** eligible handles.

```cmd
python -m webscraper
```

Single-handle debug override:

```cmd
python -m webscraper --handle I11
```

Alternate CSV path:

```cmd
python -m webscraper --handles-csv "E:\DevTools\freepbx-tools\webscraper\123NET Admin.csv"
```

Status filter usage (defaults are `production_billed production`):

```cmd
python -m webscraper --status production_billed production
```

## Run (interactive)
Run with a visible browser so you can log in if needed:

```cmd
python -m webscraper.ultimate_scraper --show --handles KPM --out webscraper/output
```

## Attach to an existing Edge session (remote debugging, CMD-friendly)
Attach mode requires you to launch Edge with a remote debugging port first and log in manually.

```cmd
msedge.exe --remote-debugging-port=9222
python -m webscraper.ultimate_scraper --handles KPM --attach 9222 --attach-host 127.0.0.1 --no-profile-launch --scrape-ticket-details
```

Notes:
- `--attach` is port-based. If you accidentally pass `host:port` (for example `--attach 127.0.0.1:9222`), the CLI now auto-splits host and port for you.
- `--attach-debugger host:port` is still supported for compatibility.
- Ticket persistence defaults to `webscraper/output/tickets.sqlite`; override with `--db <path>` if needed.


## CMD doctor helper

Use the CMD doctor to validate common local setup issues:

```cmd
scripts\doctor_cmd.bat
scripts\doctor_cmd.bat --attach 9222 --attach-host 127.0.0.1
```

It checks Edge path detection, optional attach-port reachability, `ticket-ui/package.json`, and core Python dependencies.

## Auth orchestration (PowerShell examples)
The scraper now tries profile auth first, then programmatic login, then cookie injection.

Profile auth (Edge profile directory):
```powershell
$env:SCRAPER_AUTH_ORCHESTRATION = "1"
$env:EDGE_PROFILE_DIR = "E:\\DevTools\\freepbx-tools\\webscraper\\edge_profile"
python -m webscraper.ultimate_scraper --handles KPM --out webscraper/output
```

Programmatic creds (env vars only):
```powershell
$env:SCRAPER_AUTH_ORCHESTRATION = "1"
$env:SCRAPER_USERNAME = "<username>"
$env:SCRAPER_PASSWORD = "<password>"
python -m webscraper.ultimate_scraper --handles KPM --out webscraper/output
```

Manual cookies (JSON or Netscape format):
```powershell
$env:SCRAPER_AUTH_ORCHESTRATION = "1"
$env:SCRAPER_COOKIE_FILES = "webscraper\\cookies.json,webscraper\\cookies_netscape_format.txt"
python -m webscraper.ultimate_scraper --handles KPM --out webscraper/output
```

Notes:
- Default URL is `https://noc.123.net/customers`. If navigation fails, the script will prompt for an alternate URL (e.g., IP-based). You can also navigate manually in the opened Chrome window, then press Enter to continue.
- After completing any login/MFA, the script verifies the page has content and proceeds.

## Using a handles file
Supply many handles from a file (one per line; `#` comments allowed):

```cmd
python -m webscraper.ultimate_scraper --show --handles-file customer_handles.txt --out webscraper/output
```

## Outputs
The `--out` directory will include:
- `first_page.html` and `first_page_summary.json`: initial page snapshot and parsed summary
- `debug_html_<HANDLE>.html` and `debug_log_<HANDLE>.txt`: per-handle artifacts
- `debug_dropdown_items_<HANDLE>.txt`: dropdown suggestion capture
- `debug_post_search_page<N>_<HANDLE>.html`: post-search page snapshots (with pagination)
- `scrape_results_<HANDLE>.json`: aggregated results (matching rows, ticket links, ticket details)
- `ticket_<HANDLE>_<ID>.html`: raw ticket pages
- `selenium_cookies.json`: cookies captured after initial navigation/login

## Security note (profiles & cookies)
- Browser profile folders and cookies are sensitive and must never be committed.
- The scraper expects local browser profiles for authentication.

## Live cookie export (Chrome remote debugging)
Use Chrome DevTools Protocol to grab authenticated cookies from an already logged-in Chrome session.

1) Start Chrome with remote debugging and a dedicated profile:

```cmd
chrome.exe --remote-debugging-port=9222 --user-data-dir=webscraper\\chrome_profile
```

2) Log in manually to `https://secure.123.net` in the opened Chrome window.

3) Export cookies:

```cmd
python -m webscraper.chrome_cookies_live --out webscraper/output/live_cookies.json
```

4) Run the scraper using those cookies:

```cmd
python -m webscraper.ultimate_scraper --cookie-file webscraper/output/live_cookies.json --out webscraper/output
```

## Troubleshooting
- If no search input is found, the script dumps all form inputs to the debug log to help selector tuning.
- If Search click is blocked by an alert or auth step, you’ll be prompted to complete it once and continue.
- If ChromeDriver errors occur, upgrade Selenium (`pip install -U selenium`) which uses Selenium Manager to locate/download the driver automatically.

## Configuration
Selector and behavior tuning lives in `webscraper/ultimate_scraper_config.py`. The scraper imports these selectors and optional XPath fallbacks automatically.

Environment overrides:
- `SCRAPER_URL`, `SCRAPER_OUT`, `SCRAPER_HANDLES`, `SCRAPER_HEADLESS=1` can override CLI/defaults if desired.

## Non-interactive (headless)
If your environment does not require interactive login, run without `--show`:

```cmd
python -m webscraper.ultimate_scraper --handles KPM --out webscraper/output
```

## Module-based entrypoints
Run these from the repo root to avoid import errors:

```cmd
python -m webscraper.run_discovery --help
python -m webscraper.smoke_test
python -m webscraper.ultimate_scraper --help
```

If headless navigation fails due to auth, switch back to `--show` and complete login manually.

## Ticket History SQLite + API + UI Quick Start (Windows)

1. Install deps:
   - `python -m pip install -r webscraper/requirements.txt`
   - `python -m pip install -r webscraper/requirements_api.txt`
2. Run a scrape that persists tickets to SQLite:
   - `python scripts/scrape_all_handles.py --handles KPM WS7 --db webscraper/output/tickets.sqlite --out webscraper/output/scrape_runs --auth-profile-only --profile-dir "E:/DevTools/freepbx-tools/webscraper/edge_profile_tmp" --profile-name "Default" --show`
3. Start full pipeline from CMD:
   - `python scripts\run_ticket_pipeline.py --handles KPM WS7 --attach-debugger 127.0.0.1:9222 --no-profile-launch`
   - or launcher: `scripts\run_ticket_pipeline.bat --handles KPM WS7 --attach-debugger 127.0.0.1:9222 --no-profile-launch`

4. Start API + UI together (single command, CMD/PowerShell):
   - `python webscraper/dev_server.py --ticket-stack`

5. Or run each service manually:
   - API: `python -m webscraper.ticket_api.app --db webscraper/output/tickets.sqlite --port 8787`
   - UI: `cd webscraper\ticket-ui && set TICKET_API_PROXY_TARGET=http://127.0.0.1:8787 && npm.cmd run dev`

### Ticket API examples

Run a scrape job for one handle (async job response):

```bash
curl -X POST http://127.0.0.1:8787/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"handle":"KPM","mode":"latest","limit":20}'
```

Poll job status:

```bash
curl "http://127.0.0.1:8787/api/scrape/<jobId>"
```

List handle metadata for dropdowns:

```bash
curl "http://127.0.0.1:8787/api/handles?limit=500"
```

Query tickets with filtering, paging, and sorting:

```bash
curl "http://127.0.0.1:8787/api/tickets?handle=KPM&q=router&status=open&page=1&pageSize=50&sort=newest"
```

### PowerShell `npm.ps1` execution-policy workaround
If PowerShell prints `npm.ps1 cannot be loaded because running scripts is disabled`, use one of these:
- Run npm through `npm.cmd` directly:
  - `& "$env:ProgramFiles\nodejs\npm.cmd" install`
  - `& "$env:ProgramFiles\nodejs\npm.cmd" run dev`
- Or use a bypass for just this shell:
  - `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

The pipeline scripts already prefer `npm.cmd` so they work without changing global policy.

## Ticket stack quick run (Windows + Git Bash)

### Run full stack (recommended)

```bash
cd webscraper/ticket-ui
npm install
npm run dev:stack
```

This command starts both services and automatically sets `TICKET_API_PROXY_TARGET=http://127.0.0.1:8787` for Next rewrites.

### Run UI only

```bash
cd webscraper/ticket-ui
npm run dev:ui
```

### Run API only

```bash
python -m webscraper.ticket_api.app --reload
```

### Optional legacy combined runner

```bash
python webscraper/dev_server.py --ticket-stack
```

### Scraper subprocess path used by API jobs

When `POST /api/scrape` is called, the API launches:
- `scripts/scrape_all_handles.py`

The resolved command string is recorded in job logs and job result metadata.

## Ticket stack local runbook (API + Next UI)

Start API:

```bash
python -m webscraper.ticket_api.app --reload --port 8787 --db webscraper/output/tickets.sqlite
```

Start UI:

```bash
cd webscraper/ticket-ui
npm install
npm run dev:local-api
```

PowerShell alternative:

```powershell
npm run dev:local-api:ps
```

### Quick verification checklist

- `curl http://127.0.0.1:8787/health`
- Open `http://127.0.0.1:3000` and verify the handle dropdown is populated from `/api/handles/all`.
- Start a scrape job in the UI, observe status + logs until completed/failed.
- Verify API ticket results for a handle:
  - `curl "http://127.0.0.1:8787/api/handles/<HANDLE>/tickets?page=1&pageSize=20"`

## Ticket stack quickstart (Windows)

Use the repo-root helper scripts for end-to-end validation (DB -> API -> UI -> scrape job -> job status).

### One-command PowerShell flow

From repo root:

```powershell
cd E:\DevTools\freepbx-tools
.\scripts\test_ticket_stack.ps1
```

This script will:
- ensure DB indexes (`webscraper.ticket_api.db.ensure_indexes`),
- start API on `127.0.0.1:8787`,
- start Next.js UI with `TICKET_API_PROXY_TARGET=http://127.0.0.1:8787`,
- run `curl.exe` smoke tests,
- submit `POST /api/scrape` with valid JSON and poll `/api/scrape/{jobId}`.

### One-command CMD flow

```cmd
scripts\test_ticket_stack.cmd
```

Smoke-only mode (assumes API/UI already running):

```cmd
scripts\test_ticket_stack.cmd --smoke-only
```

### Reliable POST /api/scrape command generation

```powershell
python scripts\print_scrape_curl.py --handle KPM --mode latest --limit 5
```

This prints a Windows-safe `curl.exe` command with correctly escaped JSON payload.

## Diagnostics / Debugging

- DB path source of truth: `webscraper/lib/db_path.py` (`TICKETS_DB_PATH` preferred; fallback is absolute `webscraper/output/tickets.sqlite`).
- On API startup, logs now print absolute DB path, active SQLite PRAGMA values (`WAL`, `synchronous=NORMAL`, `busy_timeout=5000`), and `DB OK: handles=X tickets=Y`.
- Debug endpoints:
  - `GET /api/debug/db`
  - `GET /api/debug/last-run`
- Scrape jobs are serialized through a single in-memory queue (single active scraper process) and stream progress via SSE:
  - `GET /api/scrape/{jobId}/events`
- Artifact paths are predictable per job/handle:
  - `webscraper/output/artifacts/<jobId>/<handle>/tickets_list.json`
  - `webscraper/output/artifacts/<jobId>/<handle>/debug.log`
- To avoid WSL/Windows confusion, run API + scraper in one environment, or explicitly set `TICKETS_DB_PATH` to an absolute path that both processes can reach.
- Quick DB sanity command:
  - `scripts/db_sanity.sh`

## Diagnostics-first scrape verification (WSL + PowerShell)

WSL bash:

```bash
python -m webscraper.ultimate_scraper --handles KPM --db webscraper/output/tickets.sqlite --out webscraper/output/scrape_runs/dev_test --show --save-html
sqlite3 webscraper/output/tickets.sqlite "select last_status, count(*) from handles group by last_status;"
sqlite3 webscraper/output/tickets.sqlite "select count(*) from tickets;"
find webscraper/output/scrape_runs/dev_test -name "diag_KPM_*" -print
python -m webscraper.scripts.doctor --db webscraper/output/tickets.sqlite --output webscraper/output
```

Windows PowerShell:

```powershell
python -m webscraper.ultimate_scraper --handles KPM --db webscraper/output/tickets.sqlite --out webscraper/output/scrape_runs/dev_test --show --save-html
sqlite3 webscraper/output/tickets.sqlite "select last_status, count(*) from handles group by last_status;"
sqlite3 webscraper/output/tickets.sqlite "select count(*) from tickets;"
rg --files webscraper/output/scrape_runs/dev_test | rg "diag_KPM_"
python -m webscraper.scripts.doctor --db webscraper/output/tickets.sqlite --output webscraper/output
```

Per-handle diagnostics are written as:
- `diag_<HANDLE>_after_load.json`
- `diag_<HANDLE>_extract_counts.json`
- `page_<HANDLE>_empty.html` (when parsing returns no tickets)

The scraper also writes `tickets_all.json` on every run (including empty runs), and prints one-line status per handle with deterministic failure reason.

## Repository layout (current)

- `src/webscraper/` - Python package source.
- `scripts/` - local run/dev helper scripts.
  - `scripts/debug/` - ad-hoc manual debug scripts (not part of the test suite).
- `configs/handles/handles_master.txt` - canonical handle list.
- `configs/settings.example.yaml` - sample runtime settings.
- `docs/ARCHITECTURE.md` - full module map and data-flow reference.
- `docs/artifacts_contract.md` - run artifact contract.
- `docs/reviews/` - code review and remediation documents.
- `var/` - runtime state + generated artifacts (gitignored):
  - `var/profiles/` browser profiles
  - `var/cookies/` cookie files
  - `var/db/` sqlite databases
  - `var/runs/` scrape run artifacts
  - `var/discovery/` discovery artifacts/db

## Local API run

```bash
python -m webscraper.ticket_api.app --host 127.0.0.1 --port 8787
```

## Credentials/cookies placement

Put local cookie exports in `var/cookies/` (for example `var/cookies/cookies.json`).
Do not commit runtime cookie files.

## Output location

Scrape output is written to `var/runs/<run_id>/` and the latest run id is tracked in `var/runs/latest.txt`.

## Bulk scrape pipeline (Ticket History UI)

- Handles are discovered automatically from `https://secure.123.net/cgi-bin/web_interface/admin/vpbx.cgi` (no static `handles.txt` dependency).
- SQLite source of truth: `webscraper/var/db/tickets.sqlite`.
- Required environment variables before starting API/job:
  - `VPBX_BASE_URL=https://secure.123.net`
  - `VPBX_USERNAME=<username>`
  - `VPBX_PASSWORD=<password>`
- If env vars are missing, `POST /api/scrape/start` returns a clear setup error and logs an error event.

Start full scrape from UI:
- Open the Ticket History page and click **Scrape / Re-scrape** (calls `POST /api/scrape/start` with `{"mode":"all","refresh_handles":true}`).

Start full scrape via curl:

```bash
curl -sS -X POST "http://127.0.0.1:8787/api/scrape/start" \
  -H "Content-Type: application/json" \
  -d '{"mode":"all","rescrape":true,"refresh_handles":true}'
```

Start a single-handle scrape via curl:

```bash
curl -sS -X POST "http://127.0.0.1:8787/api/scrape/start" \
  -H "Content-Type: application/json" \
  -d '{"mode":"one","handle":"KPM","rescrape":true,"refresh_handles":false}'
```

Check progress and event feed:

```bash
curl -sS "http://127.0.0.1:8787/api/scrape/status?job_id=<JOB_ID>"
curl -sS "http://127.0.0.1:8787/api/events/latest?limit=50"
```

Verify DB totals from health endpoint:

```bash
curl -sS "http://127.0.0.1:8787/api/health"
```

Look for `stats.total_tickets`, `stats.total_handles`, and `last_updated_utc`.

## Ticket API auth import quick checks

`python-multipart` is required for file uploads (`/api/auth/import-file`). Verify with:

```bash
python -m webscraper.ticket_api.app --doctor
python -m webscraper_manager doctor --quiet
```

Import pasted cookies (JSON/header/netscape auto-detect), then verify status and auth:

```bash
curl -sS -X POST "http://127.0.0.1:8787/api/auth/import-text" \
  -H "Content-Type: application/json" \
  -d '{"text":"Cookie: sid=abc123; csrftoken=xyz","format":"auto"}'

curl -sS "http://127.0.0.1:8787/api/auth/status"

curl -sS -X POST "http://127.0.0.1:8787/api/auth/validate" \
  -H "Content-Type: application/json" \
  -d '{"targets":["secure.123.net","noc-tickets.123.net"],"timeoutSeconds":10}'
```

Expected: `cookie_count > 0` and `domains` populated in `/api/auth/status`.
