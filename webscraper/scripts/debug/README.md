# Debug / Ad-hoc Scripts

These scripts are **not part of the importable package**. They are one-off
diagnostic tools run manually during development or troubleshooting.

## Scripts

| File | Purpose |
|------|---------|
| `_selenium_smoke.py` | Smoke-test: open Edge with a profile and navigate to `example.com` to verify WebDriver works. |
| `_cookie_test_pause.py` | Manual session pause: open Edge with a profile, navigate to the portal login page, pause for login, then print cookie names. |
| `_cookie_dump_pause.py` | Cookie dump: same as above but also exports cookies via Chrome DevTools Protocol and writes `cookie_dump.json`, `after_login.png`, `after_login.html` to `var/debug/` (gitignored). |

## Usage

Run these directly with Python **from the repo root** (they expect
`EDGE_PROFILE_DIR` to be set):

```cmd
set EDGE_PROFILE_DIR=E:\DevTools\freepbx-tools\webscraper\var\profiles\edge
python webscraper\scripts\debug\_selenium_smoke.py
```

> **Note**: These scripts write output to `webscraper/output/` (gitignored) and
> may require a live browser session. They are **not** run as part of the test
> suite.
