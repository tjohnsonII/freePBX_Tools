# ticket-ui

Next.js UI for browsing ticket/handle data and launching scraper jobs through the local Ticket API.

## Run full stack (API + UI)

```bash
cd webscraper/ticket-ui
npm install
npm run dev:stack
```

`dev:stack` starts:
- FastAPI backend: `python -m webscraper.ticket_api.app --host 127.0.0.1 --port 8787 --reload`
- Next.js UI: `next dev` on `127.0.0.1:3000`

The stack runner sets `TICKET_API_PROXY_TARGET=http://127.0.0.1:8787` automatically so Next rewrites `/api/*` to the backend.

## Run UI only

```bash
cd webscraper/ticket-ui
npm run dev:ui
```

## Run API only

```bash
python -m webscraper.ticket_api.app --reload
```

## API proxy behavior

`next.config.js` rewrites `/api/*` to `${TICKET_API_PROXY_TARGET}/api/*`.

To point the UI at another API host:

```bash
TICKET_API_PROXY_TARGET=http://127.0.0.1:9000 npm run dev:ui
```

Optional direct browser API base (bypasses rewrites):

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787 npm run dev:ui
```

## UI features

- Searchable handle dropdown backed by `GET /api/handles/all`.
- Run scrape button posts `POST /api/scrape`.
- Live job status/log polling via `GET /api/scrape/{jobId}`.
- Top-of-page API health banner based on `GET /api/health`.
