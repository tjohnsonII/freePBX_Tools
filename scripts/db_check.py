from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webscraper.ticket_api.db import ensure_indexes, explain_list_tickets_plan, get_conn, table_columns


DEFAULT_DB = os.path.join("webscraper", "output", "tickets.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect ticket API DB schema and query plan")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    args = parser.parse_args()

    ensure_indexes(args.db)

    with get_conn(args.db) as conn:
        columns = sorted(table_columns(conn, "tickets"))

    print("tickets columns:")
    for column in columns:
        print(f"- {column}")

    print("\nEXPLAIN QUERY PLAN (list_tickets sample):")
    for row in explain_list_tickets_plan(args.db, sort="newest"):
        print(f"- {row}")


if __name__ == "__main__":
    main()
