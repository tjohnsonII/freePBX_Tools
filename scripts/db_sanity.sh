#!/usr/bin/env bash
set -euo pipefail
DB_PATH="${TICKETS_DB_PATH:-${TICKETS_DB:-$(python - <<'PY'
from webscraper.lib.db_path import get_tickets_db_path
print(get_tickets_db_path())
PY
)}}"
ABS_DB="$(python - <<PY
from pathlib import Path
print(Path(r'''$DB_PATH''').expanduser().resolve())
PY
)"
echo "DB absolute path: $ABS_DB"
python - <<PY
import sqlite3
from pathlib import Path
p=r'''$ABS_DB'''
Path(p).parent.mkdir(parents=True, exist_ok=True)
conn=sqlite3.connect(p)
print("Tables:")
for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    print(" -", name)
for table in ["handles","tickets","ticket_artifacts","runs","scrape_jobs"]:
    try:
        c=conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"count[{table}]={c}")
    except Exception:
        print(f"count[{table}]=N/A")
print("Last 5 handles:")
try:
    for row in conn.execute("SELECT handle,last_status,last_error,last_scrape_utc FROM handles ORDER BY last_scrape_utc DESC LIMIT 5"):
        print(row)
except Exception:
    print("N/A")
print("Last 5 tickets:")
try:
    for row in conn.execute("SELECT ticket_id,handle,status,updated_utc FROM tickets ORDER BY updated_utc DESC LIMIT 5"):
        print(row)
except Exception:
    print("N/A")
PY
