# Webscraper Review (Domain-Safe / cmd-only)

## Inventory (current + legacy)

> Notes:
> - Commands below assume repo root, cmd.exe, and a local venv at `.venv-webscraper`.
> - Use direct executables (no PowerShell activation).

| Script | Purpose (1 sentence) | Expected inputs | Outputs | Recommended cmd (Windows cmd) |
| --- | --- | --- | --- | --- |
| `webscraper/_smoke_test.py` | Minimal Selenium smoke test against example.com. | None (uses fixed URL/handle). | `webscraper/test-output/` artifacts. | `.venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py` |
| `webscraper/ultimate_scraper.py` | Primary Selenium scraper (interactive login, per-handle capture). | `--handles`/`--handles-file`, optional cookies, env overrides. | HTML/JSON/debug artifacts, `selenium_cookies.json` in output dir. | `.venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help` |
| `webscraper/run_discovery.py` | Runs Selenium discovery crawl over fixed internal URLs. | Hard-coded URLs; optional `cookies.json` in repo root. | `webscraper/ticket-discovery-output/` artifacts. | TODO/VERIFY (uses fixed internal URLs; edit before running). |
| `webscraper/tickets_discovery.py` | Library for discovery crawl + artifact capture. | Imported by `run_discovery.py`. | Same as `run_discovery.py`. | N/A (module; use `run_discovery.py`). |
| `webscraper/chrome_cookies_live.py` | Extracts cookies via Chrome DevTools Protocol. | Chrome running with `--remote-debugging-port=9222`. | JSON output (stdout or file). | `.venv-webscraper\Scripts\python.exe webscraper\chrome_cookies_live.py --help` |
| `webscraper/extract_chrome_cookies.py` | Extracts cookies from Chrome cookie DB. | Local Chrome profile; optional `--cookies` path. | Netscape/JSON/TXT cookie output file. | `.venv-webscraper\Scripts\python.exe webscraper\extract_chrome_cookies.py --help` |
| `webscraper/login_heuristics.py` | Helpers to detect login/SSO pages in Selenium flows. | Imported by discovery/scraper modules. | None (library). | N/A (module only). |
| `webscraper/scrape_utils.py` | Shared helper utilities for parsing/normalization. | Imported by scrapers. | None (library). | N/A (module only). |
| `webscraper/site_selectors.py` | Per-site selector/keyword mapping used by discovery. | Imported by discovery modules. | None (library). | N/A (module only). |
| `webscraper/ticket_store.py` | SQLite storage helpers for ticket table extraction. | Imported by discovery modules. | SQLite DB under output root. | N/A (module only). |
| `webscraper/ultimate_scraper_config.py` | Configurable paths/selectors for scraper. | Optional CHROME/DRIVER paths, selector overrides. | None (config). | N/A (module only). |
| `webscraper/legacy/*.py` | Legacy scraper stubs (forwarders). | N/A (stubs expect missing legacy impls). | N/A until restored. | `.venv-webscraper\Scripts\python.exe webscraper\legacy\ticket_scraper.py --help` |

## Cookie + driver tooling

- `webscraper/chrome_debug_setup.bat`: launches Chrome with DevTools port 9222 (cmd-only; requires admin for firewall rule).
- `webscraper/chrome_cookies_live.py`: grabs cookies from DevTools via WebSocket.
- `webscraper/extract_chrome_cookies.py`: reads local Chrome cookie DB (Windows).
- `webscraper/chromedriver-win64/chromedriver.exe` + `chromedriver-win64.zip`: bundled driver binaries (may be outdated vs local Chrome).

## Known-good cmd runs (direct venv executables)

```
.venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py
.venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help
.venv-webscraper\Scripts\python.exe webscraper\legacy\ticket_scraper.py --help
.venv-webscraper\Scripts\python.exe webscraper\legacy\scrape_vpbx_tables.py --help
```

## Legacy vs current

- **Current:** scripts in `webscraper/` (smoke test, ultimate scraper, discovery crawler, cookie utilities).
- **Legacy:** stubs in `webscraper/legacy/` currently point to non-existent legacy implementations and require restoration (see risks below).

## What looks broken / risky

- **Legacy forwarders are broken:** `webscraper/legacy/*.py` stubs point to `webscraper/legacy/webscraper/legacy/<script>.py` which does not exist. TODO/VERIFY: restore the real legacy scripts and update the stub paths.
- **`chrome_cookies_live.py` dependency gap:** requires `websocket-client` (not in requirements prior to update) for DevTools WebSocket access.
- **`extract_chrome_cookies.py` decryption:** relies on `win32crypt` (pywin32); without it, encrypted cookies may be unreadable.
- **`run_discovery.py` hard-coded internal URLs:** running on a domain-joined laptop without access will fail or dump empty artifacts; update the URL list before use.
- **Selenium driver availability:** `ultimate_scraper.py` and `tickets_discovery.py` rely on Selenium Manager or `CHROMEDRIVER_PATH` from config; ensure Chrome/driver compatibility.
- **`webscraper/test_all.ps1` is PowerShell-only:** blocked by GPO on domain-joined systems; use cmd tasks or `scripts/test_webscraper_cmd.bat` instead.

## Quick Start on domain-locked Windows (cmd-only)

1. Create venv + install deps:
   ```cmd
   py -3 -m venv .venv-webscraper
   .venv-webscraper\Scripts\python.exe -m pip install -U pip
   .venv-webscraper\Scripts\pip.exe install -r webscraper\requirements.txt
   ```
2. Run smoke test and CLI help:
   ```cmd
   .venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py
   .venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help
   ```
3. Cookie live capture (if needed):
   ```cmd
   webscraper\chrome_debug_setup.bat
   .venv-webscraper\Scripts\python.exe webscraper\chrome_cookies_live.py --help
   ```
4. Optional: run the cmd-only batch runner:
   ```cmd
   scripts\test_webscraper_cmd.bat
   ```

## Tasks (VS Code, cmd-only)

- `webscraper:venv+deps`
- `webscraper:smoke`
- `webscraper:ultimate --help`
- `webscraper:legacy --help`
- `webscraper:cookies live` (runs `webscraper:chrome debug setup` first)
- `Start Everything + CLI` (runs the above in sequence)
