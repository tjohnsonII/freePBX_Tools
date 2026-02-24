# Webscraper Artifacts Contract

## Run root
- Every scrape run writes to `var/runs/<run_id>/`.
- `var/runs/latest.txt` stores the most recent run id.

## Required aggregate file
- `tickets_all.json` must be present at either:
  - `var/runs/<run_id>/tickets_all.json`, or
  - `var/runs/<run_id>/batch_*/tickets_all.json` for batched runs.
- API consumers should resolve latest with `var/runs/latest.txt` then read `<run_id>/tickets_all.json` when present.

## `tickets_all.json` payload
- Object keyed by handle (`{"KPM": [...], "WS7": [...]}`), or
- Handle envelope shape (`{"handle": "KPM", "tickets": [...]}`) for single-handle outputs.
- Ticket rows should include `ticket_id`/`ticket_num`, `status`, and timestamp fields when available.

## Per-handle artifacts
Within `var/runs/<run_id>/<handle>/` or nested batch directories:
- `debug_log.txt`
- `handle_page.html`
- `handle_page.png`
- `tickets_list.json`
- optional per-ticket folders containing `ticket.json`, `ticket.html`, `ticket.png`.
