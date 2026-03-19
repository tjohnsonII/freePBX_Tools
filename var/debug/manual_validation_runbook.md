# Manual Validation Runbook (ticket UI auth + handles)

## 1) Start services

```bash
python scripts/run_all_web_apps.py
```

Confirm:
- manager backend: `http://127.0.0.1:8787/api/health`
- manager frontend: `http://127.0.0.1:3004`
- ticket API: `http://127.0.0.1:8788/api/health`
- ticket UI: `http://127.0.0.1:3005`

## 2) Open manager frontend

- Browse to `http://127.0.0.1:3004`
- Verify dashboard loads and no readiness regression is shown.

## 3) Open ticket UI

- Browse to `http://127.0.0.1:3005`
- Verify banner shows `Proxy: http://127.0.0.1:8788`

## 4) Sync cookies from Chrome or Edge

- In ticket UI auth section, click **Sync from Chrome** or **Sync from Edge**.
- Confirm response message shows imported cookie count.

## 5) Run Validate Auth

- Click **Validate Auth**.
- Expected: no 405 error.
- Confirm validation payload now reports debug fields:
  - `authenticated`
  - `validation_mode`
  - `source`
  - `browser`
  - `profile`
  - `cookie_count`
  - `domains`
  - `required_cookie_names_present`
  - `missing_required_cookie_names`
  - `validation_probe_url`
  - `validation_http_status`
  - `validation_reason`

## 6) Confirm authenticated=true

- UI should show authenticated state and no paused-worker banner.

## 7) Confirm handles populate

- Handle dropdown should load names.
- Handles table should render rows (matching ticket API inventory from `/api/health total_handles`).

## 8) Scrape a single test handle

- Select one handle.
- Click **Scrape Selected Handle**.
- Confirm a job id is created and status/events progress updates.
