import sqlite3

from fastapi.testclient import TestClient

from webscraper.ticket_api import app as appmod
from webscraper.ticket_api import auth_store


def test_ensure_columns_idempotent(tmp_path):
    db_file = tmp_path / "tickets.sqlite"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE auth_cookies(
                name TEXT,
                value TEXT,
                domain TEXT,
                path TEXT,
                secure INTEGER,
                httponly INTEGER,
                expires INTEGER,
                updated_at INTEGER,
                PRIMARY KEY(name, domain, path)
            )
            """
        )

    auth_store.ensure_columns(str(db_file), auth_store.REQUIRED_COLUMNS)
    auth_store.ensure_columns(str(db_file), auth_store.REQUIRED_COLUMNS)

    with sqlite3.connect(db_file) as conn:
        cols = {str(row[1]).lower() for row in conn.execute("PRAGMA table_info(auth_cookies)").fetchall()}

    assert "httponly" in cols
    assert "samesite" in cols
    assert "hostonly" in cols
    assert "session" in cols


def test_auth_status_returns_200_when_db_path_unavailable(tmp_path, monkeypatch):
    missing_parent = tmp_path / "missing" / "tickets.sqlite"
    monkeypatch.setenv("TICKETS_DB", str(missing_parent))
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["cookie_count"] == 0
    assert payload["domains"] == []


def test_normalize_cookie_and_reject_invalid(tmp_path):
    db_file = str(tmp_path / "tickets.sqlite")
    stats = auth_store.upsert_cookies(
        db_file,
        [
            {
                "name": "sid",
                "value": "abc",
                "domain": "secure.123.net",
                "path": "/",
                "secure": True,
                "httpOnly": "true",
                "hostOnly": 1,
                "session": "0",
                "expires": "123.5",
                "sameSite": "Lax",
            },
            {"name": "", "value": "bad", "domain": "secure.123.net"},
            {"name": "missing", "value": None, "domain": "secure.123.net"},
        ],
    )

    assert stats["accepted"] == 1
    assert stats["rejected"] == 2

    with sqlite3.connect(db_file) as conn:
        row = conn.execute('SELECT secure, "httpOnly", hostOnly, session, expires, sameSite FROM auth_cookies WHERE name=?', ("sid",)).fetchone()

    assert row == (1, 1, 1, 0, 123.5, "Lax")
