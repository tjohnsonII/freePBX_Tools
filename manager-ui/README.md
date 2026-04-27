# Manager UI

Next.js 14 dashboard for managing all 123 Hosted Tools server services.

**Port:** 3004 (production) | **Stack:** Next.js 14, React 18, Tailwind CSS, TypeScript

---

## What It Does

Single-pane-of-glass for everything running on the server:

| Page | Route | Purpose |
|------|-------|---------|
| Dashboard | `/dashboard` | Service status overview — all ports, health indicators |
| Services | `/services` | Start / stop / restart individual services |
| Auth | `/auth` | Chrome scraper session status and authentication flow |
| Handles | `/handles` | Browse customer handles, trigger per-handle scrapes |
| Tickets | `/tickets` | Ticket pipeline status and job history |
| Logs | `/logs` | Live log streaming from any service |
| System | `/system` | CPU, memory, disk usage |
| Database | `/database` | SQLite table browser and query runner |

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

---

## App Structure

```
manager-ui/
├── app/
│   ├── layout.tsx        Root layout (nav, theme)
│   ├── page.tsx          / → redirect to /dashboard
│   ├── dashboard/        Service status overview
│   ├── services/         Service management
│   ├── auth/             Auth session management
│   ├── handles/          Handle browser
│   ├── tickets/          Ticket pipeline
│   ├── logs/             Log viewer
│   ├── system/           System health
│   └── database/         DB inspector
├── components/           Shared UI components
├── lib/                  API client utilities
├── public/               Static assets
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
