#!/usr/bin/env bash
set -euo pipefail

TICKETS_DB_PATH="${TICKETS_DB_PATH:-webscraper/output/tickets.sqlite}"
export TICKETS_DB_PATH

python -m uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8787 --reload
