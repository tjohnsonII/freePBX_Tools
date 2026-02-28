from __future__ import annotations

import sqlite3
import time
from typing import Any


TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS auth_cookies(
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    domain TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '/',
    secure INTEGER DEFAULT 0,
    "httpOnly" INTEGER DEFAULT 0,
    hostOnly INTEGER DEFAULT 0,
    session INTEGER DEFAULT 0,
    expires REAL,
    sameSite TEXT,
    updated_at INTEGER,
    source TEXT,
    created_utc TEXT,
    PRIMARY KEY(name, domain, path)
)
'''


REQUIRED_COLUMNS: dict[str, str] = {
    "name": "TEXT",
    "value": "TEXT",
    "domain": "TEXT",
    "path": "TEXT",
    "secure": "INTEGER",
    "httpOnly": "INTEGER",
    "hostOnly": "INTEGER",
    "session": "INTEGER",
    "expires": "REAL",
    "sameSite": "TEXT",
    "updated_at": "INTEGER",
    "source": "TEXT",
    "created_utc": "TEXT",
}

LEGACY_COLUMN_ALIASES: dict[str, set[str]] = {
    "httpOnly": {"httponly"},
    "sameSite": {"samesite"},
}


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace("\"", "\"\"")}"'


def _normalize_column_name(column_name: str) -> str:
    return str(column_name or "").strip().lower()


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(auth_cookies)").fetchall()]


def _column_exists(existing_columns: list[str], target_name: str) -> bool:
    existing = {_normalize_column_name(name) for name in existing_columns}
    aliases = LEGACY_COLUMN_ALIASES.get(target_name, set())
    wanted = {_normalize_column_name(target_name), *{_normalize_column_name(alias) for alias in aliases}}
    return any(name in existing for name in wanted)


def ensure_columns(db_path: str, desired_columns_dict: dict[str, str]) -> None:
    with sqlite3.connect(db_path) as conn:
        existing_columns = _columns(conn)
        for column_name, column_type in desired_columns_dict.items():
            if _column_exists(existing_columns, column_name):
                continue
            try:
                conn.execute(f"ALTER TABLE auth_cookies ADD COLUMN {_quote_identifier(column_name)} {column_type}")
                existing_columns.append(column_name)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise


def ensure_table(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(TABLE_SQL)
    ensure_columns(db_path, REQUIRED_COLUMNS)


def _to_bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None:
        return 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on"} else 0


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_cookie(cookie: dict[str, Any], now_ts: int | None = None) -> dict[str, Any] | None:
    now = int(now_ts or time.time())
    name = str(cookie.get("name") or "").strip()
    value = str(cookie.get("value") or "")
    if not name or value == "":
        return None

    domain = str(cookie.get("domain") or "").strip()
    path = str(cookie.get("path") or "/") or "/"
    same_site_raw = cookie.get("sameSite", cookie.get("samesite", cookie.get("same_site")))
    same_site = str(same_site_raw).strip() if same_site_raw not in (None, "") else None

    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "secure": _to_bool_int(cookie.get("secure")),
        "httpOnly": _to_bool_int(cookie.get("httpOnly", cookie.get("httponly", cookie.get("http_only")))),
        "hostOnly": _to_bool_int(cookie.get("hostOnly", cookie.get("hostonly"))),
        "session": _to_bool_int(cookie.get("session")),
        "expires": _to_float_or_none(cookie.get("expires", cookie.get("expiry", cookie.get("expirationDate")))),
        "sameSite": same_site,
        "updated_at": int(cookie.get("updated_at") or now),
    }


def upsert_cookies(db_path: str, cookies: list[dict[str, Any]], *, source: str = "none", imported_at: int | None = None) -> dict[str, int]:
    ensure_table(db_path)
    now = int(imported_at or time.time())
    accepted = 0
    rejected = 0
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for cookie in cookies:
        normalized = normalize_cookie(cookie, now)
        if not normalized:
            rejected += 1
            continue
        key = (normalized["domain"], normalized["path"], normalized["name"])
        deduped[key] = normalized

    with sqlite3.connect(db_path) as conn:
        for item in deduped.values():
            conn.execute(
                '''
                INSERT INTO auth_cookies(name, value, domain, path, secure, "httpOnly", hostOnly, session, expires, sameSite, updated_at, source, created_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, domain, path)
                DO UPDATE SET
                    value=excluded.value,
                    secure=excluded.secure,
                    "httpOnly"=excluded."httpOnly",
                    hostOnly=excluded.hostOnly,
                    session=excluded.session,
                    expires=excluded.expires,
                    sameSite=excluded.sameSite,
                    updated_at=excluded.updated_at,
                    source=excluded.source,
                    created_utc=excluded.created_utc
                ''',
                (
                    item["name"],
                    item["value"],
                    item["domain"],
                    item["path"],
                    item["secure"],
                    item["httpOnly"],
                    item["hostOnly"],
                    item["session"],
                    item["expires"],
                    item["sameSite"],
                    item["updated_at"],
                    source,
                    str(now),
                ),
            )
            accepted += 1

    return {"accepted": accepted, "rejected": rejected}


def replace_cookies(db_path: str, cookies: list[dict[str, Any]], *, source: str = "none", imported_at: int | None = None) -> dict[str, int]:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM auth_cookies")
    return upsert_cookies(db_path, cookies, source=source, imported_at=imported_at)


def load_cookies(db_path: str) -> list[dict[str, Any]]:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT name, value, domain, path, secure, "httpOnly" AS httpOnly, expires, sameSite, updated_at FROM auth_cookies ORDER BY updated_at DESC'
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
            "sameSite": r["sameSite"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def clear_cookies(db_path: str) -> None:
    ensure_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM auth_cookies")


def get_status(db_path: str) -> dict[str, Any]:
    try:
        ensure_table(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT COUNT(*) AS count, MAX(updated_at) AS last_imported, MAX(source) AS source FROM auth_cookies").fetchone()
            domains = conn.execute("SELECT domain, COUNT(*) AS count FROM auth_cookies GROUP BY domain ORDER BY domain").fetchall()
        count = int(row["count"]) if row and row["count"] is not None else 0
        return {
            "ok": True,
            "reason": None,
            "cookie_count": count,
            "count": count,
            "domains": [str(r["domain"]) for r in domains],
            "domain_counts": [{"domain": str(r["domain"]), "count": int(r["count"])} for r in domains],
            "last_imported": int(row["last_imported"]) if row and row["last_imported"] is not None else None,
            "source": str(row["source"] or "none") if row else "none",
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "cookie_count": 0,
            "count": 0,
            "domains": [],
            "domain_counts": [],
            "last_imported": None,
            "source": "none",
        }


def status(db_path: str) -> dict[str, Any]:
    return get_status(db_path)
