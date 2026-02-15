# ticket-ui

Next.js UI for browsing ticket/handle data and launching scraper jobs through the local Ticket API.

## Dev run (local API default)

```bash
cd webscraper/ticket-ui
npm install
npm run dev:local-api
```

This script assumes the API is at `http://127.0.0.1:8787` and sets:
- `TICKET_API_PROXY_TARGET=http://127.0.0.1:8787` (Next rewrite target)
- `NEXT_PUBLIC_TICKET_API_PROXY_TARGET=http://127.0.0.1:8787` (shown in UI diagnostics)

## API proxy behavior

`next.config.js` rewrites `/api/*` to `${TICKET_API_PROXY_TARGET}/api/*`.

To point the UI at another API host:

```bash
TICKET_API_PROXY_TARGET=http://127.0.0.1:9000 NEXT_PUBLIC_TICKET_API_PROXY_TARGET=http://127.0.0.1:9000 npm run dev
```

Optional direct browser API base (bypasses rewrites):

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787 npm run dev
```

## UI features

- Searchable handle dropdown backed by `GET /api/handles/all`.
- Run scrape button posts `POST /api/scrape`.
- Live job status/log polling via `GET /api/scrape/{jobId}`.
- Connectivity banner with API/proxy diagnostics for common “Failed to fetch” issues.
