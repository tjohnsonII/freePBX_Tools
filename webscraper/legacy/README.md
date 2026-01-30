# Legacy scraper scripts

These scripts were moved from the repo root to keep legacy tooling organized under `webscraper/legacy/`.
Each legacy script still has a root-level stub for backward compatibility.

> ⚠️ SENSITIVE DATA WARNING
> Some scripts interact with authenticated systems, cookies, or internal docs.
> **Do not commit** real cookies, tokens, or scrape outputs.

## Scripts

### `ticket_scraper.py`
- **Purpose:** Requests-based ticket scraper that builds per-customer SQLite knowledge bases.
- **Run:** `python webscraper/legacy/ticket_scraper.py --customer <HANDLE> --username <USER> --password <PASS> --output knowledge_base [--export-md]`
- **Auth:** Username/password or optional `--cookie-file`.
- **Outputs:** `knowledge_base/<HANDLE>_tickets.db`, `knowledge_base/<HANDLE>_tickets.json`, optional `knowledge_base/<HANDLE>_knowledge_base.md`.
- **Safe test:** `python webscraper/legacy/ticket_scraper.py --help`

### `ticket_scraper_session.py`
- **Purpose:** Session-cookie based ticket scraper that exports ticket JSON.
- **Run:** `python webscraper/legacy/ticket_scraper_session.py --customer <HANDLE> --cookie-file cookies.json`
- **Auth:** Cookies required (`--cookie-file` or `--interactive`).
- **Outputs:** `knowledge_base/<HANDLE>_tickets_session.json`.
- **Safe test:** `python webscraper/legacy/ticket_scraper_session.py --help`

### `batch_ticket_scrape.py`
- **Purpose:** Batch wrapper that runs `ticket_scraper.py` for a list of handles.
- **Run:** `python webscraper/legacy/batch_ticket_scrape.py --handles-file customer_handles.txt --output-dir knowledge_base`
- **Auth:** `--username/--password`, or `KB_USERNAME`/`KB_PASSWORD` env vars; fallback to `webscraper.ultimate_scraper_config`.
- **Outputs:** `knowledge_base/<HANDLE>_tickets.db` per handle; optional unified DB when `--build` is used.
- **Safe test:** `python webscraper/legacy/batch_ticket_scrape.py --help`

### `scrape_123net_docs.py`
- **Purpose:** Requests/NTLM-based internal doc scraper for secure.123.net.
- **Run:** `python webscraper/legacy/scrape_123net_docs.py --url <URL> --output <DIR> [--depth N] [--post] [--batch <handles.txt>]`
- **Auth:** NTLM by default; may use existing cookies in `cookies.txt` if present.
- **Outputs:** HTML/text files in output directory; optionally `tickets.json` / `all_tickets.json` for batch/post modes.
- **Safe test:** `python webscraper/legacy/scrape_123net_docs.py --help`

### `scrape_123net_docs_selenium.py`
- **Purpose:** Selenium-based internal doc scraper.
- **Run:** TODO/VERIFY (module defines `SeleniumDocScraper` but no CLI entrypoint).
- **Auth:** Interactive login/MFA in browser.
- **Outputs:** HTML files + `_INDEX.md` in output directory (configured in code).
- **Safe test:** TODO/VERIFY (no CLI entrypoint).

### `scrape_vpbx_tables.py`
- **Purpose:** Selenium-based VPBX table scraper with optional detail/comprehensive modes.
- **Run:** `python webscraper/legacy/scrape_vpbx_tables.py [--comprehensive] [--max-details N] [--no-details] --output <DIR>`
- **Auth:** Requires authenticated access to secure.123.net (interactive browser session).
- **Outputs:** `table_data.csv`, `table_data.json`, and detail HTML/TXT files under output directory.
- **Safe test:** `python webscraper/legacy/scrape_vpbx_tables.py --help`

### `scrape_vpbx_tables_comprehensive.py`
- **Purpose:** Legacy comprehensive VPBX table scraper (similar to `scrape_vpbx_tables.py`).
- **Run:** `python webscraper/legacy/scrape_vpbx_tables_comprehensive.py --output <DIR>`
- **Auth:** Requires authenticated access to secure.123.net.
- **Outputs:** `table_data.csv`, `table_data.json`, and detail HTML/TXT files.
- **Safe test:** `python webscraper/legacy/scrape_vpbx_tables_comprehensive.py --help`

### `run_comprehensive_scrape.py`
- **Purpose:** Orchestrates a full VPBX comprehensive scrape via `scrape_vpbx_tables.py`.
- **Run:** `python webscraper/legacy/run_comprehensive_scrape.py`
- **Auth:** Requires authenticated access to secure.123.net (Selenium).
- **Outputs:** `freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive/`.
- **Safe test:** `python webscraper/legacy/run_comprehensive_scrape.py --help` (if available; script is interactive).

### `selenium_to_kb.py`
- **Purpose:** Convert Selenium run artifacts into per-handle SQLite knowledge bases.
- **Run:** `python webscraper/legacy/selenium_to_kb.py --input-dir webscraper/output/kb-run --out-dir knowledge_base`
- **Auth:** None (local parsing only).
- **Outputs:** `knowledge_base/<HANDLE>_tickets.db`, `knowledge_base/<HANDLE>_tickets.json`.
- **Safe test:** Use a temp input dir with a minimal `scrape_results_TEST.json` fixture.

### `extract_browser_cookies.py`
- **Purpose:** Windows-only helper to extract cookies from Chrome/Edge into `cookies.json`.
- **Run:** `python webscraper/legacy/extract_browser_cookies.py`
- **Auth:** Requires local browser login to secure.123.net.
- **Outputs:** `cookies.json` in current directory.
- **Safe test:** `python webscraper/legacy/extract_browser_cookies.py` (manual/interactive).

### `convert_cookies.py`
- **Purpose:** Convert Netscape-format `cookies.txt` to `cookies.json`.
- **Run:** `python webscraper/legacy/convert_cookies.py` (expects `cookies.txt` in CWD).
- **Auth:** None (local file conversion only).
- **Outputs:** `cookies.json` in current directory.
- **Safe test:** Run in a temp folder with a dummy `cookies.txt`.

## Regression runner

Use the PowerShell regression script (no network/auth required):

```
powershell -ExecutionPolicy Bypass -File .\scripts\run_webscraper_regression.ps1
```
