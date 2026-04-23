from __future__ import annotations

import os
from pathlib import Path

from webscraper.paths import tickets_db_path


def get_tickets_db_path() -> str:
    explicit = os.environ.get("TICKETS_DB_PATH") or os.environ.get("TICKETS_DB")
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    return str(tickets_db_path().resolve())
