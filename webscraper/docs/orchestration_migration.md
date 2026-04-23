# Webscraper orchestration migration notes

## What changed

The webscraper stack now has one authoritative backend orchestration model for browser attach/auth/scrape/persist visibility.

### New orchestration lifecycle

`detect browser -> seed auth -> validate auth -> run scrape -> persist tickets -> expose results`

All steps now flow through a single orchestrator service (`webscraper.ticket_api.orchestration.WebScraperOrchestrator`) and produce structured state/job updates.

### New API surface

- `GET /api/system/status`
- `POST /api/browser/detect`
- `POST /api/auth/seed`
- `POST /api/auth/validate`
- `POST /api/scrape/run`
- `POST /api/scrape/run-e2e`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/db/status`

### Job model

Each orchestrated scrape job now includes:

- `job_id`
- `created_at`
- `started_at`
- `completed_at`
- `current_state`
- `current_step`
- `records_found`
- `records_written`
- `error_message`

### Legacy paths retained for compatibility

Old auth/scrape endpoints are still present where needed, and the orchestration dashboard consumes the explicit control-plane status/job APIs for observability.

## Startup/launcher changes

`webscraper/scripts/dev_ticket_stack.py` now treats `/api/system/status` as API readiness for the orchestrated stack, making startup validation align with operational control-plane health.

## Troubleshooting flow

1. Load dashboard and verify `backend_health` + `browser_status`.
2. Run `Detect Browser`; if unavailable, fix browser runtime/debug target first.
3. Run `Seed Auth` then `Validate Auth`.
4. Run `Run End-to-End` and inspect per-step output.
5. If failed, use:
   - `GET /api/system/status` for `last_error`
   - `GET /api/jobs` and `GET /api/jobs/{job_id}` for job-level diagnostics.
