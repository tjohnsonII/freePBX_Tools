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

4. Start API manually (CMD):
   - `set TICKETS_DB=E:\DevTools\freepbx-tools\webscraper\output\tickets.sqlite`
   - `python -m uvicorn webscraper.ticket_api.app:app --port 8787`

5. Start UI manually in CMD:
   - `cd webscraper\ticket-ui`
   - `set NEXT_PUBLIC_TICKET_API_BASE=http://127.0.0.1:8787`
   - `npm.cmd install`
   - `npm.cmd run dev`

### PowerShell `npm.ps1` execution-policy workaround
If PowerShell prints `npm.ps1 cannot be loaded because running scripts is disabled`, use one of these:
- Run npm through `npm.cmd` directly:
  - `& "$env:ProgramFiles\nodejs\npm.cmd" install`
  - `& "$env:ProgramFiles\nodejs\npm.cmd" run dev`
- Or use a bypass for just this shell:
  - `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

The pipeline scripts already prefer `npm.cmd` so they work without changing global policy.
