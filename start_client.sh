#!/usr/bin/env bash
# Start the webscraper in CLIENT MODE.
# The scraper authenticates via VPN, scrapes 123.net, and sends all data to
# the remote server instead of writing to a local SQLite database.
#
# Required env vars:
#   INGEST_SERVER_URL — base URL of the server  (e.g. http://10.0.0.5:8788)
#   INGEST_API_KEY    — shared secret matching the server's INGEST_API_KEY
#
# Optional:
#   WEBSCRAPER_PORT   — local port for this client's trigger API  (default 8789)

set -euo pipefail
cd "$(dirname "$0")"

: "${INGEST_SERVER_URL:?Set INGEST_SERVER_URL to the server base URL (e.g. http://10.0.0.5:8788)}"
: "${INGEST_API_KEY:?Set INGEST_API_KEY to the shared secret}"

export CLIENT_MODE=1
export WEBSCRAPER_PORT="${WEBSCRAPER_PORT:-8789}"

echo "[client] Starting webscraper in CLIENT MODE"
echo "[client] Sending scraped data to: $INGEST_SERVER_URL"
echo "[client] Local trigger API on port: $WEBSCRAPER_PORT"

exec python -m uvicorn webscraper.ticket_api.app:app \
    --host 0.0.0.0 \
    --port "$WEBSCRAPER_PORT" \
    --app-dir webscraper/src
