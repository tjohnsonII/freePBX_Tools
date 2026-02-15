#!/usr/bin/env python3
"""Batch scrape many handles and persist ticket history to SQLite."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webscraper.db import finish_run, init_db, record_artifact, start_run, upsert_handle, upsert_tickets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch handle scraper with SQLite persistence")
    parser.add_argument("--handles-file", default="customer_handles.txt")
    parser.add_argument("--db", default=os.path.join("webscraper", "output", "tickets.sqlite"))
    parser.add_argument("--out", default=os.path.join("webscraper", "output", "scrape_runs"))
    parser.add_argument("--batch-size", type=int, default=25)

    parser.add_argument("--profile-dir")
    parser.add_argument("--profile-name")
    parser.add_argument("--auth-profile-only", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--rate-limit", type=float)
    parser.add_argument("--max-tickets", type=int)
    parser.add_argument("--scrape-ticket-details", action="store_true")
    parser.add_argument("--save-html", action="store_true")
    parser.add_argument("--save-screenshot", action="store_true")
    parser.add_argument("--dump-dom-on-fail", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--phase-logs", action="store_true")
    return parser.parse_args()


def read_handles(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    handles = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return handles


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_scraper_cmd(args: argparse.Namespace, batch_handles: list[str], batch_out: Path) -> list[str]:
    cmd = [sys.executable, "-m", "webscraper.ultimate_scraper", "--handles", *batch_handles, "--out", str(batch_out)]
    passthrough_flags = {
        "--profile-dir": args.profile_dir,
        "--profile-name": args.profile_name,
        "--rate-limit": args.rate_limit,
        "--max-tickets": args.max_tickets,
    }
    for flag, value in passthrough_flags.items():
        if value is not None:
            cmd.extend([flag, str(value)])

    for flag in [
        "--auth-profile-only",
        "--show",
        "--scrape-ticket-details",
        "--save-html",
        "--save-screenshot",
        "--dump-dom-on-fail",
        "--resume",
        "--phase-logs",
    ]:
        if getattr(args, flag.lstrip("-").replace("-", "_")):
            cmd.append(flag)
    return cmd


def _artifact_type(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return ext or "file"


def _load_ticket_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def process_batch_output(db_path: str, run_id: str, batch_out: Path, batch_handles: list[str]) -> tuple[set[str], set[str]]:
    successes: set[str] = set()
    failures: set[str] = set()

    all_path = batch_out / "tickets_all.json"
    all_data: dict[str, list[dict[str, Any]]] = {}
    if all_path.exists():
        try:
            all_data = json.loads(all_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Failed to parse {all_path}: {exc}")

    for handle in batch_handles:
        handle_tickets = all_data.get(handle, [])
        ticket_root = batch_out / "tickets" / handle
        detail_rows: list[dict[str, Any]] = []

        if ticket_root.exists():
            for ticket_json in ticket_root.glob("*/ticket.json"):
                payload = _load_ticket_json(ticket_json)
                if payload:
                    detail_rows.append(payload)

        rows_to_store = detail_rows if detail_rows else handle_tickets
        upsert_tickets(db_path, run_id, handle, rows_to_store)

        if handle in all_data:
            upsert_handle(db_path, handle, "success")
            successes.add(handle)
        else:
            upsert_handle(db_path, handle, "failed", "handle missing from tickets_all.json")
            failures.add(handle)

        if ticket_root.exists():
            for artifact in ticket_root.glob("*/*"):
                if not artifact.is_file():
                    continue
                ticket_id = artifact.parent.name
                record_artifact(
                    db_path=db_path,
                    run_id=run_id,
                    handle=handle,
                    ticket_id=ticket_id,
                    artifact_type=_artifact_type(artifact),
                    path=str(artifact),
                )

    if all_path.exists():
        record_artifact(db_path, run_id, "_batch", "_batch", "json", str(all_path))

    return successes, failures


def main() -> int:
    args = parse_args()
    handles = read_handles(args.handles_file)
    if not handles:
        print("[ERROR] No handles found.")
        return 1

    init_db(args.db)
    run_id = start_run(args.db, vars(args))

    root_out = Path(args.out) / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    root_out.mkdir(parents=True, exist_ok=True)

    total_successes: set[str] = set()
    total_failures: set[str] = set()

    try:
        for i, batch in enumerate(chunks(handles, max(1, args.batch_size)), start=1):
            batch_out = root_out / f"batch_{i:03d}"
            batch_out.mkdir(parents=True, exist_ok=True)
            cmd = build_scraper_cmd(args, batch, batch_out)
            print(f"[INFO] Running batch {i} ({len(batch)} handles)")
            proc = subprocess.run(cmd, text=True, capture_output=True)
            if proc.stdout:
                print(proc.stdout)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)

            successes, failures = process_batch_output(args.db, run_id, batch_out, batch)
            total_successes.update(successes)
            total_failures.update(failures)

            if proc.returncode != 0:
                err = f"scraper exit code {proc.returncode}"
                for handle in set(batch) - successes:
                    upsert_handle(args.db, handle, "failed", err)
                    total_failures.add(handle)

    finally:
        finish_run(args.db, run_id)

    if total_successes and not total_failures:
        return 0
    if total_successes and total_failures:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
