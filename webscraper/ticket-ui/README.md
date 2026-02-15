# ticket-ui

Next.js UI for browsing ticket/handle data from the local ticket API.

## Run

From repo root:

```bash
cd webscraper/ticket-ui
npm install
npm run dev
```

Optional API override:

```bash
set NEXT_PUBLIC_TICKET_API_BASE=http://127.0.0.1:8787
npm run dev
```

The app expects the scraper/API SQLite DB at `webscraper/output/tickets.sqlite` unless your API is configured otherwise.
