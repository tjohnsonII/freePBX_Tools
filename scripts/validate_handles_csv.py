#!/usr/bin/env python3
"""Validate handle extraction and dedupe rules for the handles CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scrape_all_handles import _status_rank, load_handles_from_csv, parse_handles_values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate handles CSV parsing rules")
    parser.add_argument("--handles-csv", default="./123NET Admin.csv", help="Path to handles CSV")
    parser.add_argument(
        "--status",
        nargs="+",
        default=["production_billed", "production"],
        help="Allowed Status.1 values (comma and/or whitespace separated)",
    )
    return parser.parse_args()


def compute_expected_handles(rows: list[dict[str, str]], statuses: set[str]) -> list[str]:
    winners: dict[str, tuple[int, int]] = {}
    for idx, row in enumerate(rows, start=1):
        handle = (row.get("Handle") or "").strip().upper()
        if not handle:
            continue
        status = (row.get("Status.1") or "").strip().lower()
        if statuses and status not in statuses:
            continue
        candidate = (_status_rank(status), idx)
        current = winners.get(handle)
        if current is None or candidate[0] > current[0] or (candidate[0] == current[0] and idx < current[1]):
            winners[handle] = candidate
    return sorted(winners)


def main() -> int:
    args = parse_args()
    csv_path = Path(args.handles_csv)
    if not csv_path.exists():
        print(f"[ERROR] Handles CSV not found: {csv_path}")
        return 1

    statuses = {s.strip().lower() for s in parse_handles_values(args.status) if s.strip()}
    handles = load_handles_from_csv(str(csv_path), statuses)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    expected = compute_expected_handles(rows, statuses)
    dedupe_ok = handles == expected

    print(f"total rows: {len(rows)}")
    print(f"total unique handles returned: {len(handles)}")
    print(f"dedupe/status-preference check: {'PASS' if dedupe_ok else 'FAIL'}")
    print("first 20 handles:")
    for item in handles[:20]:
        print(f"- {item}")
    return 0 if dedupe_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
