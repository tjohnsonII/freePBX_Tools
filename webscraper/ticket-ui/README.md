# ticket-ui

Next.js UI for browsing ticket/handle data from the local ticket API.

## Run

From repo root:

```bash
cd webscraper/ticket-ui
npm install
npm run dev
```

Optional API proxy target (used by Next rewrites for /api/*):

```bash
set TICKET_API_PROXY_TARGET=http://127.0.0.1:8787
npm run dev
```

Or call API directly from the browser (bypass rewrite):

```bash
set NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787
npm run dev
```

The app expects the scraper/API SQLite DB at `webscraper/output/tickets.sqlite` unless your API is configured otherwise.

## Run API + UI together

From repo root:

```bash
python webscraper/dev_server.py --ticket-stack
```

This launches the FastAPI backend on `127.0.0.1:8787` and the Next.js UI on `127.0.0.1:3000`.
