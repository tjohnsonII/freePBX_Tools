# Auth + Scraping API Changelog

## Canonical auth endpoints
- `POST /api/auth/import_from_browser`
- `POST /api/auth/sync_from_browser`
- `GET /api/auth/validate?domain=...`
- `GET /api/auth/status`

## Backward-compatible aliases
- `POST /api/auth/import-from-browser` -> `import_from_browser`
- `POST /api/auth/import-browser` -> `import_from_browser`
- `POST /api/auth/sync-from-browser` -> `sync_from_browser`

## Environment variables
- `WEBSCRAPER_LOGS_ENABLED` (logs API toggle; defaults on in dev/test/local env names)
- `CHROME_DEBUG_PORT` (preferred CDP port)
- `CHROME_USER_DATA_DIR` (Chrome user data path for disk import)

## Run stack + seed auth
1. Start API on `:8787`.
2. Start Next.js UI on `:3004`.
3. On Auth page, click browser import/sync or call `POST /api/auth/import_from_browser`.
4. Verify with `GET /api/auth/validate?domain=secure.123.net`.
5. Run doctor: `python -m webscraper.scripts.doctor --auth-e2e --api-base http://127.0.0.1:8787`.
