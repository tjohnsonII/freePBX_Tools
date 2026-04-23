"""Handle loading utilities for batch scraping."""

from __future__ import annotations

import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CSV_PATH = BASE_DIR / "123NET Admin.csv"
HANDLES_TXT = BASE_DIR / "var" / "handles.txt"
_HANDLES_CANDIDATES = [
    BASE_DIR / "configs" / "handles" / "handles_master.txt",
    BASE_DIR / "configs" / "handles.txt",
]


def _extract_handles_from_csv(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle_file:
        reader = csv.DictReader(handle_file)
        fieldnames = reader.fieldnames or []
        handle_column = next((col for col in fieldnames if "handle" in col.lower()), None)
        if not handle_column:
            return []

        return sorted({row.get(handle_column, "").strip().upper() for row in reader if row.get(handle_column, "").strip()})


def _load_from_txt(path: Path) -> list[str]:
    return [
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_handles() -> list[str]:
    if CSV_PATH.exists():
        return _extract_handles_from_csv(CSV_PATH)

    if HANDLES_TXT.exists():
        return _load_from_txt(HANDLES_TXT)

    for candidate in _HANDLES_CANDIDATES:
        if candidate.exists():
            return _load_from_txt(candidate)

    return []


def load_handles_from_csv(csv_path: str) -> list[str]:
    """Backward-compatible explicit CSV loader."""

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Handles CSV not found: {path}")
    handles = _extract_handles_from_csv(path)
    if not handles:
        raise ValueError(f"CSV is missing a handle column or values: {path}")
    return handles
