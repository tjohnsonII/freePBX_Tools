#!/usr/bin/env bash
# Run the order agent — designed for cron.
# Loads .env, runs --incomplete --batch 5, logs to var/logs/order_agent.log

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO/var/logs/order_agent.log"
PY="$REPO/webscraper/.venv-webscraper/bin/python"

mkdir -p "$(dirname "$LOG")"

if [[ ! -x "$PY" ]]; then
    echo "[order_agent] ERROR: venv python not found: $PY" >> "$LOG"
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$REPO/.env"
set +a

echo "" >> "$LOG"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"

cd "$REPO/webscraper"
"$PY" -m webscraper.ticket_api.order_agent --incomplete --batch 5 --quiet >> "$LOG" 2>&1
echo "[order_agent] exit $?" >> "$LOG"
