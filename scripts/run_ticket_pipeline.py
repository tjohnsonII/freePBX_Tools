#!/usr/bin/env python3
"""Run scraper -> DB check -> API startup helper for ticket UI workflows."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ticket scrape pipeline and start API")
    parser.add_argument("--db", default=os.path.join("webscraper", "output", "tickets.sqlite"))
    parser.add_argument("--out", default=os.path.join("webscraper", "output", "scrape_runs"))
    parser.add_argument("--handles", nargs="+")
    parser.add_argument("--handles-file")
    parser.add_argument("--attach-debugger")
    parser.add_argument("--no-profile-launch", action="store_true")
    parser.add_argument("--api-port", type=int, default=8787)
    parser.add_argument("--skip-scrape", action="store_true")
    return parser.parse_args()


def run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print(f"[PIPELINE] Running: {subprocess.list2cmdline(cmd)}")
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def db_check(db_path: str) -> tuple[int, int, int]:
    with sqlite3.connect(db_path) as conn:
        handles = conn.execute("select count(*) from handles").fetchone()[0]
        tickets = conn.execute("select count(*) from tickets").fetchone()[0]
        runs = conn.execute("select count(*) from runs").fetchone()[0]
    print(f"[DB] handles={handles} tickets={tickets} runs={runs}")
    return handles, tickets, runs


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)

    if not args.skip_scrape:
        scrape_cmd = [sys.executable, "scripts/scrape_all_handles.py", "--db", args.db, "--out", args.out]
        if args.handles:
            scrape_cmd.extend(["--handles", *args.handles])
        elif args.handles_file:
            scrape_cmd.extend(["--handles-file", args.handles_file])
        else:
            print("[ERROR] --handles or --handles-file is required unless --skip-scrape is used")
            return 2

        if args.attach_debugger:
            scrape_cmd.extend(["--attach-debugger", args.attach_debugger])
        if args.no_profile_launch:
            scrape_cmd.append("--no-profile-launch")

        if run_cmd(scrape_cmd) != 0:
            return 1

    _handles, tickets, _runs = db_check(args.db)
    if tickets <= 0:
        print("[WARN] tickets=0; API/UI can still start but no data is currently available.")

    env = os.environ.copy()
    env["TICKETS_DB"] = str(Path(args.db).resolve())
    api_cmd = [sys.executable, "-m", "uvicorn", "webscraper.ticket_api.app:app", "--port", str(args.api_port)]
    print("[PIPELINE] Starting API server...")
    print(f"[PIPELINE] UI: cd webscraper\\ticket-ui && set NEXT_PUBLIC_TICKET_API_BASE=http://127.0.0.1:{args.api_port} && npm.cmd run dev")
    print(f"[PIPELINE] Open UI at: http://127.0.0.1:3000")
    print(f"[PIPELINE] API docs: http://127.0.0.1:{args.api_port}/docs")
    return run_cmd(api_cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
