from __future__ import annotations

import os
from pathlib import Path


def get_tickets_db_path() -> str:
    explicit = os.environ.get("TICKETS_DB_PATH") or os.environ.get("TICKETS_DB")
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    repo_root = Path(__file__).resolve().parents[2]
    return str((repo_root / "webscraper" / "output" / "tickets.sqlite").resolve())
