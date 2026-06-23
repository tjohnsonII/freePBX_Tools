# Manager UI

Next.js 14 dashboard for managing all 123 Hosted Tools server services.

**Port:** 3004 (production) | **Stack:** Next.js 14, React 18, Tailwind CSS, TypeScript

---

## What It Does

Single-pane-of-glass for everything running on the server:

| Page | Route | Purpose |
|------|-------|---------|
| Dashboard | `/dashboard` | Service status overview — health cards, control panel, live logs, port/process tables, event feed, scraper stats |
| Services | `/services` | Start / stop / restart individual services |
| Auth | `/auth` | Chrome scraper session status and authentication flow |
| Handles | `/handles` | Browse customer handles, trigger per-handle scrapes |
| Tickets | `/tickets` | Ticket pipeline status and job history |
| Logs | `/logs` | Live log streaming from any service |
| System | `/system` | CPU, memory, disk usage, ports, running processes |
| Database | `/database` | SQLite table browser and query runner |

---

## Dashboard Cards

| Card | Data Source |
| ---- | ----------- |
| API Health | `GET /api/health` |
| Scraper Worker | `GET /api/status/summary` → `worker.paused` |
| Database | `GET /api/db/summary` → `tickets_count` |
| DB Integrity | `GET /api/db/integrity` |

---

## Key Components

| Component | Purpose |
| --------- | ------- |
| `ControlPanel` | Start / pause / stop scraper worker buttons |
| `StatusCard` | Colour-coded health indicator tile |
| `LogViewer` | Live-tailing log viewer (WebSocket or polling) |
| `EventFeed` | Recent events from the event bus JSONL log |
| `WebscraperStatus` | Live scraper stats — queue depth, rate, errors |
| `PortTable` | Which ports are listening and by which process |
| `ProcessTable` | Running process list from the manager API |
| `DataPreviewTable` | Generic key-value table for DB summary data |
| `DebugReportButton` | One-click `GET /api/debug/report` dump |

---

## Development

```bash
cd manager-ui

# Install deps
npm ci

# Dev server (hot reload — NOT for production use)
npm run dev -- --port 3004

# Production build
npm run build

# Production server (requires build first)
npm run start -- --port 3004 --hostname 127.0.0.1
```

The dev server (`npm run dev`) is for local development only. On the server, always use `npm run build` + `npm run start` — or just let `FULL_START.sh` handle it.

---

## API Connection

All browser-side fetches go to `NEXT_PUBLIC_API_BASE`. This must be set before the build:

```bash
# Set automatically by FULL_START.sh before each build
echo "NEXT_PUBLIC_API_BASE=https://manager-api.123hostedtools.com" > manager-ui/.env.local
```

For local dev, override:

```bash
echo "NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787" > manager-ui/.env.local
```

All API calls proxy through `lib/api.ts → getJson()`, which prepends `/api` and relies on Next.js route handlers in `app/api/[...path]/route.ts` to forward requests to the webscraper_manager.

---

## App Structure

```
manager-ui/
├── app/
│   ├── layout.tsx                    # Root layout (nav, theme)
│   ├── page.tsx                      # / → redirect to /dashboard
│   ├── dashboard/page.tsx            # Main overview page
│   ├── services/page.tsx             # Service management
│   ├── auth/page.tsx                 # Auth session management
│   ├── handles/[handle]/page.tsx     # Per-handle detail
│   ├── tickets/page.tsx              # Ticket browser
│   ├── logs/page.tsx                 # Log tail viewer
│   ├── system/page.tsx               # Ports and processes
│   ├── database/page.tsx             # DB stats and integrity
│   └── api/[...path]/route.ts        # Catch-all proxy to webscraper_manager
├── components/                       # Shared UI components
├── lib/
│   └── api.ts                        # getJson() fetch helper
├── public/                           # Static assets
├── package.json
├── next.config.mjs
├── tailwind.config.ts
└── tsconfig.json
```

---

## Build Notes

`FULL_START.sh` rebuilds Manager UI automatically when source changes using an MD5 hash of all `.ts`, `.tsx`, and `.css` files. If source is unchanged, the build is skipped (saves ~60 seconds).

Force a rebuild:

```bash
sudo ./FULL_START.sh --force-rebuild
```

Or clear the hash file manually:

```bash
rm manager-ui/.src_hash
sudo ./FULL_START.sh
```

---

## Backend API

Manager UI talks to the **Manager API** (`webscraper_manager/`) on port 8787. The API is documented in `webscraper_manager/` and the route list is in `docs/ARCHITECTURE.md`.
