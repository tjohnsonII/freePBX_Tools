"""Handle loading utilities for batch scraping."""

from __future__ import annotations

import csv
from pathlib import Path


MIN_HANDLE_COUNT = 500


def load_handles_from_csv(csv_path: str) -> list[str]:
    """Load handles from a CSV that contains a `Handle` column.

    Handles are normalized by stripping whitespace, dropping blanks, and
    de-duplicating while preserving first-seen order. Handles are normalized to
    uppercase to keep matching and persistence consistent.
    """

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Handles CSV not found: {path}")

    loaded: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "Handle" not in (reader.fieldnames or []):
            raise ValueError(f"CSV is missing required column 'Handle': {path}")

        for row in reader:
            raw_handle = (row.get("Handle") or "").strip()
            if not raw_handle:
                continue
            normalized = raw_handle.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            loaded.append(normalized)

    print(f"Loaded {len(loaded)} handles from CSV")
    if len(loaded) < MIN_HANDLE_COUNT:
        raise RuntimeError(
            f"Refusing to continue: loaded {len(loaded)} handles from {path}, expected at least {MIN_HANDLE_COUNT}"
        )
    return loaded

