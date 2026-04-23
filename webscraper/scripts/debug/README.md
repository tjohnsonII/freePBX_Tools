# Debug Scripts

These scripts are **developer diagnostics only**. They are not part of the importable `webscraper` package API.

## Scripts

- `cookie_test_pause.py`
  - Opens Edge with `EDGE_PROFILE_DIR`, navigates to customer page, pauses for manual login, then prints cookie count/names.
- `cookie_dump_pause.py`
  - Same login flow, then captures Selenium cookies + CDP cookies and writes artifacts to `webscraper/output/`.
- `selenium_smoke.py`
  - Minimal Selenium startup smoke check using `EDGE_PROFILE_DIR`.

## How to run

From repo root:

```bash
python webscraper/scripts/debug/cookie_test_pause.py
python webscraper/scripts/debug/cookie_dump_pause.py
python webscraper/scripts/debug/selenium_smoke.py
```

## Required environment

- `EDGE_PROFILE_DIR` must point to an existing Edge user-data/profile directory.
- Selenium + Edge WebDriver requirements must already be installed (`webscraper/requirements.txt`).

## Notes

- These scripts can write local artifacts (HTML/screenshots/JSON) under `webscraper/output/`.
- Do not commit generated artifacts, cookies, or profile data.
