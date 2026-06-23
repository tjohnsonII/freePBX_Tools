# ticket-ui

Next.js 14 frontend for browsing scraped ticket history, managing customer handles, controlling the scraper orchestrator, and querying VPBX / phone-config data. Proxies all `/api` requests to the webscraper Ticket API (port 8788).

---

## Quick Start

```bash
cd webscraper/ticket-ui
npm install
npm run dev
```

Opens at **<http://localhost:3000>** (Next.js default).

Start the ticket API first:

```bash
# From repo root
python -m webscraper.ticket_api.app
```

Or use the combined dev stack (starts both):

```bash
npm run dev:stack
```

---

## Pages

| Route | Purpose |
| ----- | ------- |
| `/` | Home — handle search and navigation |
| `/handles/[handle]` | Per-customer ticket list |
| `/tickets/[ticketId]` | Single ticket detail |
| `/auth` | Cookie and session status |
| `/logs` | Scraper log tail |
| `/noc-queue` | NOC queue — pending and active installs |
| `/phone-configs` | Phone configuration lookup and generator |
| `/site-config` | Site configuration viewer |
| `/vpbx` | VPBX data browser |

---

## API Proxy

All `/api/*` requests are forwarded by the catch-all handler `app/api/[...path]/route.ts`.

```env
# .env.local — override the backend target (default: http://127.0.0.1:8788)
TICKET_API_PROXY_TARGET=http://127.0.0.1:8788
```

At dev start:

```bash
npm run dev:local-api   # sets TICKET_API_PROXY_TARGET=http://127.0.0.1:8788 explicitly
```

---

## Job Status API (Internal)

The UI exposes SSE/polling routes for scraper job tracking:

| Route | Purpose |
| ----- | ------- |
| `GET /api/jobs/status/[jobId]` | Poll a scraper job status |
| `GET /api/jobs/[jobId]/events` | SSE stream of job events |

---

## Key Components

| Component | Purpose |
| --------- | ------- |
| `HandleDropdown` | Searchable dropdown of all customer handles |
| `OrchestrationDashboard` | Scraper worker controls — start, pause, stop |

---

## Project Structure

```text
app/
  page.tsx                          # Home / handle search
  layout.tsx                        # Root layout and nav
  auth/page.tsx                     # Auth / cookie status
  handles/[handle]/page.tsx         # Per-handle ticket list
  tickets/[ticketId]/page.tsx       # Ticket detail view
  logs/page.tsx                     # Log viewer
  noc-queue/page.tsx                # NOC queue
  phone-configs/page.tsx            # Phone config lookup
  site-config/page.tsx              # Site config viewer
  vpbx/page.tsx                     # VPBX browser
  api/
    [...path]/route.ts              # Catch-all proxy to ticket API
    jobs/status/[jobId]/route.ts    # Job status poll
    jobs/[jobId]/events/route.ts    # SSE job events
  components/
    HandleDropdown.tsx
    OrchestrationDashboard.tsx
lib/
  api.ts                            # Shared fetch helpers
next.config.js                      # Proxy target via TICKET_API_PROXY_TARGET
```

---

## Build

```bash
npm run build
npm run start    # production server (Next.js default port 3000)
```
