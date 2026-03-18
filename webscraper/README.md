# webscraper

Operational scraper workspace for FreePBX ticket/history collection.

## Active components

- **Python package (active runtime):** `webscraper/src/webscraper/`
  - Primary runtime entrypoint: `python -m webscraper.ultimate_scraper`
  - Scrape orchestration shim: `webscraper.scrape.runner`
  - Ticket API: `webscraper.ticket_api.app`
- **API/UI dev stack:**
  - API: `python -m webscraper.dev_server --ticket-stack`
  - UI: `webscraper/ticket-ui/` (Next.js)
- **Tests:** `webscraper/tests/`

## Structure highlights

- `src/webscraper/scrape/` — active scrape package.
- `src/webscraper/scraping/` — deprecated compatibility shim for old imports.
- `scripts/debug/` — ad-hoc/manual debug scripts (not package API).
- `docs/reviews/` — audit/review/remediation docs moved from root.
- `src/webscraper/legacy/` — quarantined legacy/transitional modules.

## Run the backend API

From repo root:

```bash
python -m webscraper.ticket_api.app
```

Or run combined API + UI helper:

```bash
python -m webscraper.dev_server --ticket-stack
```

## Run the scraper

```bash
python -m webscraper.ultimate_scraper --help
```

## Run tests

```bash
pytest -q webscraper/tests
```

## Config locations

- Runtime config: `src/webscraper/config.py`
- Selenium selector/runtime defaults: `src/webscraper/ultimate_scraper_config.py`
- Host selector hints: `src/webscraper/site_selectors.py`
- Legacy static config (compat only): `src/webscraper/webscraper_config.py`

## Architecture docs

- API/auth contracts: `docs/auth_api_changelog.md`, `docs/artifacts_contract.md`
- Reviews/remediation notes: `docs/reviews/`

## Notes on `legacy/`

`src/webscraper/legacy/` contains behavior-preserving legacy/transitional implementations.
New work should target non-legacy modules first; legacy modules remain to avoid breaking imports/workflows.
