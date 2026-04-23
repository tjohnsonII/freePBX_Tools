from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from webscraper.lib.db_path import get_tickets_db_path
from webscraper.ticket_api import db


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize/upgrade ticket KB SQLite schema")
    parser.add_argument("--db", default="", help="Override SQLite path")
    args = parser.parse_args()

    db_path = Path(args.db).resolve() if args.db else Path(get_tickets_db_path()).resolve()
    db.ensure_indexes(str(db_path))

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    tables = [row[0] for row in rows]
    print(f"Initialized database: {db_path}")
    print("Tables:")
    for table in tables:
        print(f" - {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
