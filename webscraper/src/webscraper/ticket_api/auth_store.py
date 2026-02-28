from __future__ import annotations

import sqlite3
import time
from typing import Any


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS auth_cookies(
    name TEXT,
    value TEXT,
    domain TEXT,
    path TEXT,
    secure INTEGER,
    httpOnly INTEGER,
    expires INTEGER,
    updated_at INTEGER,
    PRIMARY KEY(name, domain, path)
)
"""


REQUIRED_COLUMNS: dict[str, str] = {
    "name": "TEXT",
    "value": "TEXT",
    "domain": "TEXT",
    "path": "TEXT",
    "secure": "INTEGER",
    "httpOnly": "INTEGER",
    "expires": "INTEGER",
    "updated_at": "INTEGER",
}


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(auth_cookies)").fetchall()]


def _has_column(conn: sqlite3.Connection, column_name: str) -> bool:
    return column_name in _columns(conn)


def ensure_table(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(TABLE_SQL)
        cols = _columns(conn)
        for name, col_type in REQUIRED_COLUMNS.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE auth_cookies ADD COLUMN {name} {col_type}")
        # backward compatibility with existing schema
        if "http_only" not in cols and not _has_column(conn, "http_only"):
            conn.execute("ALTER TABLE auth_cookies ADD COLUMN http_only INTEGER")
        if "source" not in cols and not _has_column(conn, "source"):
            conn.execute("ALTER TABLE auth_cookies ADD COLUMN source TEXT")
        if "created_utc" not in cols and not _has_column(conn, "created_utc"):
            conn.execute("ALTER TABLE auth_cookies ADD COLUMN created_utc TEXT")


def replace_cookies(db_path: str, cookies: list[dict[str, Any]], *, source: str = "none", imported_at: int | None = None) -> None:
    ensure_table(db_path)
    now = int(imported_at or time.time())
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("DELETE FROM auth_cookies")
        for cookie in cookies:
            conn.execute(
                """
                INSERT INTO auth_cookies(name, value, domain, path, secure, httpOnly, http_only, expires, updated_at, source, created_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, domain, path)
                DO UPDATE SET
                    value=excluded.value,
                    secure=excluded.secure,
                    httpOnly=excluded.httpOnly,
                    http_only=excluded.http_only,
                    expires=excluded.expires,
                    updated_at=excluded.updated_at,
                    source=excluded.source,
                    created_utc=excluded.created_utc
                """,
                (
                    str(cookie.get("name") or ""),
                    str(cookie.get("value") or ""),
                    str(cookie.get("domain") or ""),
                    str(cookie.get("path") or "/"),
                    1 if cookie.get("secure") else 0,
                    1 if cookie.get("httpOnly") else 0,
                    1 if cookie.get("httpOnly") else 0,
                    cookie.get("expires"),
                    int(cookie.get("updated_at") or now),
                    source,
                    str(now),
                ),
            )


def load_cookies(db_path: str) -> list[dict[str, Any]]:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, value, domain, path, secure, COALESCE(httpOnly, http_only, 0) AS httpOnly, expires, updated_at FROM auth_cookies ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "name": str(r["name"] or ""),
            "value": str(r["value"] or ""),
            "domain": str(r["domain"] or ""),
            "path": str(r["path"] or "/"),
            "secure": bool(r["secure"]),
            "httpOnly": bool(r["httpOnly"]),
            "expires": r["expires"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def clear_cookies(db_path: str) -> None:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM auth_cookies")


def status(db_path: str) -> dict[str, Any]:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) AS count, MAX(updated_at) AS last_imported, MAX(source) AS source FROM auth_cookies").fetchone()
        domains = conn.execute("SELECT domain, COUNT(*) AS count FROM auth_cookies GROUP BY domain ORDER BY domain").fetchall()
    count = int(row["count"]) if row and row["count"] is not None else 0
    return {
        "cookie_count": count,
        "domains": [str(r["domain"]) for r in domains],
        "domain_counts": [{"domain": str(r["domain"]), "count": int(r["count"])} for r in domains],
        "last_imported": int(row["last_imported"]) if row and row["last_imported"] is not None else None,
        "source": str(row["source"] or "none") if row else "none",
    }
