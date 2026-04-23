# Webscraper Artifacts Contract

## Run layout

Each scrape run writes to:

```
var/runs/<run_id>/
  run_metadata.json
  handles.json
  tickets_all.json
  handles/<HANDLE>/
    debug_log.txt
    handle_page.html
    handle_page.png
    company_probe.json
    tickets.json
```

Latest run pointer (Windows-safe text pointer, not symlink):

```
var/runs/LATEST_RUN.txt
```

This file contains only `<run_id>`.

## `tickets_all.json` schema

Top-level keys are always present:
- `run_id`
- `generated_utc`
- `source`
- `handles`
- `summary`

`handles` is an object keyed by handle. Each handle entry includes:
- `handle`
- `status` (`ok` or `failed`)
- `error` (string or null)
- `started_utc`
- `finished_utc`
- `artifacts` (paths relative to run root)
- `ticket_count`

`summary` includes:
- `total_handles`
- `ok`
- `failed`

## Guarantees
- `tickets_all.json` is always written for every run (including zero-ticket runs).
- Handles are pre-seeded as `failed` + `error="not started"` and updated incrementally.
- Writes are atomic (`.tmp` file then rename) to avoid partial JSON reads by API/UI.
