# Ultimate Scraper – Quickstart

This scraper drives Chrome via Selenium to search customer handles, capture page HTML, enumerate ticket links, and save structured JSON outputs. It’s designed to run interactively (visible browser) so you can complete any VPN/SSO/MFA steps.

## Prerequisites
- Windows with Google Chrome installed
- Python 3.8+ available on PATH (`python --version`)

Install packages:

```powershell
pip install selenium beautifulsoup4 lxml
```

## Run (interactive)
Run with a visible browser so you can log in if needed:

```powershell
python webscraper/ultimate_scraper.py --show --handles KPM --out webscraper/output
```

Notes:
- Default URL is `https://noc.123.net/customers`. If navigation fails, the script will prompt for an alternate URL (e.g., IP-based). You can also navigate manually in the opened Chrome window, then press Enter to continue.
- After completing any login/MFA, the script verifies the page has content and proceeds.

## Using a handles file
Supply many handles from a file (one per line; `#` comments allowed):

```powershell
python webscraper/ultimate_scraper.py --show --handles-file customer_handles.txt --out webscraper/output
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

```powershell
python webscraper/ultimate_scraper.py --handles KPM --out webscraper/output
```

If headless navigation fails due to auth, switch back to `--show` and complete login manually.
