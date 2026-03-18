from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

WRITE_LOCK = threading.Lock()


@contextmanager
def get_conn(db_path: str):
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {str(row["name"]) for row in rows}


def build_last_activity_expr(cols: set[str]) -> str:
    priority_columns = ["updated_utc", "created_utc", "opened_utc"]
    qualified = [f"t.{column}" for column in priority_columns if column in cols]
    if not qualified:
        return "MAX(NULL)"
    return f"MAX(COALESCE({', '.join(qualified)}))"
