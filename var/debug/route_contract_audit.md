# Route/Method Contract Audit (ticket UI + manager backend + ticket API)

Date: 2026-03-19

## Frontend calls discovered (ticket UI)

| Frontend call | Source file | Function | Path | Method | Expected response shape |
|---|---|---|---|---|---|
| Load auth status | `webscraper/ticket-ui/app/page.tsx` | `loadAuthStatus` | `/api/auth/status` | GET | `{ cookie_count, domains, source, authenticated, ... }` |
| Validate Auth | `webscraper/ticket-ui/app/page.tsx` | `runValidate` | `/api/auth/validate?domain=...&timeout_seconds=...` | GET | `{ authenticated, reason, checks[], cookie_count, domains }` |
| Launch Login (isolated) | `webscraper/ticket-ui/app/page.tsx` | `launchLoginIsolated` | `/api/auth/launch-browser` | POST | `{ ok, started, browser, profile_dir, command?, error? }` |
| Seed Auth | `webscraper/ticket-ui/app/page.tsx` | `launchLoginSeeded` | `/api/auth/seed` | POST | `{ ok, mode_used, details?, next_step_if_failed? }` |
| Sync from Chrome / Edge | `webscraper/ticket-ui/lib/authBrowserSync.ts` | `syncAuthFromBrowser` | `/api/auth/import_from_browser` (+ aliases) | POST | `{ status, imported_count, domain, message?, detail? }` |
| Handles list (names) | `webscraper/ticket-ui/app/page.tsx` | `loadHandles` | `/api/handles/all?q=&limit=` | GET | `{ items: string[], count }` |
| Handles table | `webscraper/ticket-ui/app/page.tsx` | `loadHandles` | `/api/handles?limit=&offset=` | GET | `{ items: HandleRow[] }` |
| Scrape selected | `webscraper/ticket-ui/app/page.tsx` | `startScrapeSelected` | `/api/scrape/start` | POST | `{ job_id }` |

## Backend routes discovered

### Manager backend (8787)
- Base: `webscraper_manager/api/server.py`.
- Auth routes in `webscraper_manager/api/routes/auth.py`:
  - `GET /api/auth/status`
  - `POST /api/auth/validate` (POST only)
  - `POST /api/auth/seed`
  - `POST /api/auth/sync/chrome`
  - `POST /api/auth/sync/edge`
  - no `/api/auth/launch-browser`
- DB/handles routes in `webscraper_manager/api/routes/db.py`:
  - `GET /api/db/handles` (not `/api/handles`)

### Ticket API (8788)
- Base: `webscraper/src/webscraper/ticket_api/app.py`.
- Auth routes:
  - `GET/POST /api/auth/validate`
  - `POST /api/auth/launch-browser`
  - `POST /api/auth/launch`
  - `POST /api/auth/import_from_browser` (+ alias paths)
  - `GET /api/auth/status`
  - `POST /api/auth/seed`
- Handle routes:
  - `GET /api/handles/all`
  - `GET /api/handles`
  - `GET /api/handles/{handle}/tickets`

## Route mismatch table (root causes)

| Frontend call | Routed target before fix | Actual implemented handler | Mismatch type | Impact |
|---|---|---|---|---|
| `GET /api/auth/validate` | manager backend `:8787` via ticket-ui proxy default | manager backend only had `POST /api/auth/validate`; ticket API supports GET | wrong base URL + wrong method | 405 Method Not Allowed |
| `POST /api/auth/launch-browser` | manager backend `:8787` | manager backend has no launch route; ticket API has it | wrong base URL + missing route | 404 Not Found |
| `GET /api/handles/all` and `GET /api/handles` | manager backend `:8787` | manager backend has `/api/db/handles` only; ticket API has `/api/handles*` | wrong base URL + missing route | handles not loaded |
| Browser sync endpoints | manager backend `:8787` | browser sync routes exist in ticket API `:8788` | wrong base URL | sync appears partial/stale in UI |

## Fix direction implemented

- Normalized ticket UI proxy defaults to `http://127.0.0.1:8788` (ticket API source of truth).
- Launcher now injects `TICKET_API_PROXY_TARGET` and `NEXT_PUBLIC_TICKET_API_PROXY_TARGET` using the configured `--api-host/--api-port`, preventing stale `8787` defaults.
- Kept manager backend untouched for manager UI responsibilities.
