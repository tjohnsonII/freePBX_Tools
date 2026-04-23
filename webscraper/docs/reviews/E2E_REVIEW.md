# Webscraper E2E Review (CLI → Scraper → DB → API → UI)

## Scope and entrypoints

Validated entrypoints inside `webscraper/`:
- `webscraper/ultimate_scraper.py` (module wrapper)
- `webscraper/cli/main.py` (CLI parser/delegation)
- `webscraper/ultimate_scraper_legacy.py` (legacy-compatible implementation)
- `webscraper/ticket_api/app.py` (FastAPI app + scrape job runner)
- `webscraper/ticket_api/db.py` (API query/index layer)
- `webscraper/db.py` (schema + persistence)
- `webscraper/ticket-ui/*` (Next.js UI)

## E2E flow diagram

```text
CLI/UI command
  ├─ CLI: python -m webscraper.ultimate_scraper ...
  └─ UI: POST /api/scrape
         ↓
  webscraper/ticket_api/app.py::_run_scrape_job
         ↓ launches
  scripts/scrape_all_handles.py
         ↓ writes
  SQLite (webscraper/output/tickets.sqlite) via webscraper/db.py
         ↓ read/query
  webscraper/ticket_api/db.py endpoints in app.py
         ↓ proxied via Next rewrite
  webscraper/ticket-ui (handles dropdown, tickets, job logs)
```

## Local runbook (Windows + Git Bash)

1) API:
- `python -m webscraper.ticket_api.app --reload --port 8787 --db webscraper/output/tickets.sqlite`

2) UI:
- `cd webscraper/ticket-ui`
- `npm install`
- `npm run dev:local-api`

3) Combined (optional):
- `python webscraper/dev_server.py --ticket-stack`

## Next rewrite confirmation

`ticket-ui/next.config.js` rewrites `/api/:path*` to `${TICKET_API_PROXY_TARGET}/api/:path*`. The new UI script `dev:local-api` sets `TICKET_API_PROXY_TARGET=http://127.0.0.1:8787` and exposes the same target for diagnostics.

## Backend changes and query/index findings

Implemented:
- New endpoint: `GET /api/handles/all?q=&limit=500`
- Index coverage in `ensure_indexes()` for:
  - `(handle, updated_utc DESC)`
  - `(handle, status, updated_utc DESC)`
  - `(handle, created_utc DESC)`
  - `(status, updated_utc DESC)`
  - `(ticket_id)` and `(handle, ticket_id)`
- `list_tickets()` query shaping improved for sorting and time range filters to better align with index usage.
- Added `explain_list_tickets_plan()` helper for `EXPLAIN QUERY PLAN` verification in code.

## API error and job runner hardening

Implemented:
- `/health` now reports API version, DB path, existence flag, and aggregate DB stats.
- `_run_scrape_job()` now logs the resolved command string.
- Early missing-script failure is explicit.
- Timeout/failure returns normalized result fields (`errorType`, `exitCode`, `logTail`).
- DB job state updates are centralized in `finally` so terminal status is consistently persisted.

## UI improvements delivered

- Searchable handle dropdown now uses `/api/handles/all`.
- Single “Run scrape” action supports mode (`latest`/`full`) and limit.
- Polling status/log tail (`/api/scrape/{jobId}`) continues until completion/failure.
- “Failed to fetch” UX now distinguishes network/timeout/http and shows API startup guidance + `/health` link.

## Known fragilities

1) FTS availability is optional (SQLite build dependent); fallback LIKE search still scans more data for broad queries.
2) Subprocess scrape execution still depends on local environment/auth constraints for Selenium.
3) Handle summary endpoint still computes aggregate counts each call (acceptable for moderate dataset sizes, but can be materialized later if dataset grows).

## Recommended cleanup sequence

1. Add API-level tests for `/api/handles/all` and scrape failure payload shape.
2. Add UI integration test for job polling and error banner states.
3. Consider materialized per-handle summary table refreshed after scrape completion.
4. Add optional structured job logs table (instead of in-memory `JOB_LOGS`) for crash resilience.
