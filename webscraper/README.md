# Ultimate Scraper – Quickstart

This scraper drives Chrome via Selenium to search customer handles, capture page HTML, enumerate ticket links, and save structured JSON outputs. It’s designed to run interactively (visible browser) so you can complete any VPN/SSO/MFA steps.

## Prerequisites
- Windows with Google Chrome installed
- Python 3.8+ available on PATH (`python --version`)

Install packages:

```cmd
pip install selenium beautifulsoup4 lxml
```

## Quick Start (cmd-only, domain-locked Windows)
From repo root (no PowerShell), use direct venv executables:

```cmd
py -3 -m venv .venv-webscraper
.venv-webscraper\Scripts\python.exe -m pip install -U pip
.venv-webscraper\Scripts\pip.exe install -r webscraper\requirements.txt
.venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py
.venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help
```

## Run (interactive)
Run with a visible browser so you can log in if needed:

```cmd
python -m webscraper.ultimate_scraper --show --handles KPM --out webscraper/output
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
python -m webscraper._smoke_test
python -m webscraper.ultimate_scraper --help
```

If headless navigation fails due to auth, switch back to `--show` and complete login manually.
