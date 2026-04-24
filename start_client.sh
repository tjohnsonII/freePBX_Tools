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

# Load .env if present (never committed — put INGEST_SERVER_URL and INGEST_API_KEY here)
if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

: "${INGEST_SERVER_URL:?Set INGEST_SERVER_URL in .env or export it (e.g. https://ticket-api.123hostedtools.com)}"
: "${INGEST_API_KEY:?Set INGEST_API_KEY in .env or export it}"

export CLIENT_MODE=1
export WEBSCRAPER_PORT="${WEBSCRAPER_PORT:-8789}"
# Ensure Chrome has a display to open on. :99 is the Xvfb/VNC display started
# by start_services.sh. Don't override if the caller already set DISPLAY.
export DISPLAY="${DISPLAY:-:99}"

# Kill any existing process on the API port
_kill_port() {
  local port="$1"
  local pid=""
  if command -v lsof &>/dev/null; then
    pid=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  elif command -v powershell.exe &>/dev/null; then
    pid=$(powershell.exe -NoProfile -Command "
      \$c = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
      if (\$c) { \$c.OwningProcess | Sort-Object -Unique }
    " 2>/dev/null | tr -d '\r' || true)
  fi
  if [[ -n "$pid" ]]; then
    echo "[client] Port $port in use by PID $pid — stopping it..."
    kill "$pid" 2>/dev/null || taskkill //F //PID "$pid" &>/dev/null || true
    sleep 1
  fi
}
_kill_port "$WEBSCRAPER_PORT"

echo "[client] Starting webscraper in CLIENT MODE"
echo "[client] Sending scraped data to: $INGEST_SERVER_URL"
echo "[client] Local trigger API on port: $WEBSCRAPER_PORT"
echo "[client] Chrome will open on your Windows desktop (no VNC needed)"

exec python -m uvicorn webscraper.ticket_api.app:app \
    --host 0.0.0.0 \
    --port "$WEBSCRAPER_PORT" \
    --app-dir webscraper/src
