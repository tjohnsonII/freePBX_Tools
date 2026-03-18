# Verified webscraper E2E review

This document records a code-backed runtime/DB/UI review for `webscraper/`.

## Scope
- Included: `webscraper/` only.
- Excluded: `traceroute-visualizer-main/` and other apps.

## Highlights
- Active CLI path is `webscraper.ultimate_scraper -> webscraper.cli.main -> webscraper.ultimate_scraper_legacy.main`.
- API is FastAPI (`webscraper.ticket_api.app`) default `127.0.0.1:8787`.
- UI is Next.js (`webscraper/ticket-ui`) default `127.0.0.1:3000`, with rewrite proxy controlled by `TICKET_API_PROXY_TARGET`.
- Primary SQLite schema for ticket history is in `webscraper/db.py`.
- Ticket API query logic is in `webscraper/ticket_api/db.py`.

## Consolidation direction
- Authoritative runtime target should be package modules (`webscraper/cli`, `webscraper/scrape`, `webscraper/browser`, `webscraper/auth`, `webscraper/db.py`).
- Keep `ultimate_scraper.py` as compatibility shim.
- Move remaining nested logic out of `ultimate_scraper_legacy.py` incrementally, then retire it once call-sites migrate.
