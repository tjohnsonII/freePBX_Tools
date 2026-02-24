from __future__ import annotations

import argparse
from webscraper.paths import tickets_db_path, runs_dir
import sqlite3
from pathlib import Path


def find_newest_run_dir(scrape_runs_root: Path) -> Path | None:
    if not scrape_runs_root.exists():
        return None
    dirs = [p for p in scrape_runs_root.rglob("*") if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick doctor checks for ticket scraper DB + output artifacts")
    parser.add_argument("--db", default=str(tickets_db_path()))
    parser.add_argument("--output", default=str(runs_dir()))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    output_root = Path(args.output).resolve()
    print(f"DB path: {db_path}")
    if not db_path.exists():
        print("[FAIL] DB file not found")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    handles_count = conn.execute("SELECT COUNT(*) c FROM handles").fetchone()["c"]
    tickets_count = conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
    print(f"counts: handles={handles_count} tickets={tickets_count}")

    print("last 10 handles:")
    for row in conn.execute(
        "SELECT handle,last_status,last_error,last_started_utc,last_finished_utc,last_run_id FROM handles ORDER BY COALESCE(last_finished_utc,last_scrape_utc) DESC LIMIT 10"
    ).fetchall():
        print(
            f"  - {row['handle']} status={row['last_status'] or '-'} error={row['last_error'] or '-'} "
            f"started={row['last_started_utc'] or '-'} finished={row['last_finished_utc'] or '-'} run={row['last_run_id'] or '-'}"
        )

    print("last 5 runs:")
    for row in conn.execute("SELECT run_id,started_utc,finished_utc,failure_reason FROM runs ORDER BY started_utc DESC LIMIT 5").fetchall():
        print(
            f"  - {row['run_id']} started={row['started_utc'] or '-'} finished={row['finished_utc'] or '-'} "
            f"failure_reason={row['failure_reason'] or '-'}"
        )

    newest = find_newest_run_dir(output_root / "scrape_runs")
    print(f"newest scrape_run dir: {newest if newest else '-'}")
    if newest:
        has_tickets_all = (newest / "tickets_all.json").exists()
        print(f"contains tickets_all.json: {has_tickets_all}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
