from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DBInspector:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def summary(self) -> dict[str, Any]:
        exists = self.db_path.exists()
        info: dict[str, Any] = {
            "db_path": str(self.db_path),
            "file_exists": exists,
            "size_bytes": self.db_path.stat().st_size if exists else 0,
            "last_modified": self.db_path.stat().st_mtime if exists else None,
            "handles_count": 0,
            "tickets_count": 0,
            "last_ticket_inserted": None,
            "last_handle_sync": None,
        }
        if not exists:
            return info
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                for table_key, table_name in (("handles_count", "handles"), ("tickets_count", "tickets")):
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                        info[table_key] = int(cur.fetchone()[0])
                    except sqlite3.Error:
                        info[table_key] = 0
        except sqlite3.Error:
            pass
        return info

    def integrity(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"ok": False, "message": "database file missing"}
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            return {"ok": row and row[0] == "ok", "result": row[0] if row else "unknown"}
        except sqlite3.Error as exc:
            return {"ok": False, "message": str(exc)}
