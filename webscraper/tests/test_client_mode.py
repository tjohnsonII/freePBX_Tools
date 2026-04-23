"""Tests for CLIENT_MODE: db_client HTTP proxying and ingest_routes auth."""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_response(json_data, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    if status >= 400:
        from requests import HTTPError
        r.raise_for_status.side_effect = HTTPError(response=r)
    return r


@pytest.fixture()
def ingest_client(tmp_path, monkeypatch):
    """FastAPI TestClient with ingest router registered and a real temp DB."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("INGEST_API_KEY", "secret123")
    monkeypatch.setenv("TICKETS_DB_PATH", db_file)

    from webscraper.ticket_api import db as real_db
    from webscraper.lib.db_path import get_tickets_db_path
    from webscraper.ticket_api import ingest_routes

    real_db.ensure_indexes(db_file)

    app = FastAPI()
    ingest_routes.register(app, real_db, get_tickets_db_path)
    return TestClient(app)


# ── db_client: env config ──────────────────────────────────────────────────────

def test_server_url_default(monkeypatch):
    monkeypatch.delenv("INGEST_SERVER_URL", raising=False)
    from webscraper.ticket_api import db_client
    assert db_client._server_url() == "http://127.0.0.1:8788"


def test_server_url_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://10.0.0.5:8788/")
    from webscraper.ticket_api import db_client
    assert db_client._server_url() == "http://10.0.0.5:8788"


def test_headers_with_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "mysecret")
    from webscraper.ticket_api import db_client
    assert db_client._headers().get("X-Ingest-Key") == "mysecret"


def test_headers_no_key(monkeypatch):
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    from webscraper.ticket_api import db_client
    assert "X-Ingest-Key" not in db_client._headers()


# ── db_client: write operations POST to server ─────────────────────────────────

def test_upsert_tickets_batch_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"inserted": 2})) as mock_post:
        result = db_client.upsert_tickets_batch("_", "ACG", [
            {"ticket_id": "T1", "subject": "test"},
            {"ticket_id": "T2", "subject": "test2"},
        ])

    call_args = mock_post.call_args
    assert "/api/ingest/tickets" in call_args.args[0]
    body = call_args.kwargs["json"]
    assert body["handle"] == "ACG"
    assert len(body["tickets"]) == 2
    assert result == 2


def test_update_handle_progress_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"ok": True})) as mock_post:
        db_client.update_handle_progress("_", "ACG", status="ok", ticket_count=5)

    body = mock_post.call_args.kwargs["json"]
    assert "/api/ingest/handle-progress" in mock_post.call_args.args[0]
    assert body["handle"] == "ACG"
    assert body["ticket_count"] == 5


def test_add_event_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"ok": True})) as mock_post:
        db_client.add_event("_", "2024-01-01Z", "info", "ACG", "test message")

    assert "/api/ingest/event" in mock_post.call_args.args[0]
    body = mock_post.call_args.kwargs["json"]
    assert body["message"] == "test message"
    assert body["level"] == "info"


def test_create_scrape_job_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"ok": True})) as mock_post:
        db_client.create_scrape_job(
            "_", job_id="job-1", handle=None, mode="scrape",
            ticket_limit=None, status="queued", created_utc="2024-01-01Z",
        )

    assert "/api/ingest/job/create" in mock_post.call_args.args[0]
    assert mock_post.call_args.kwargs["json"]["job_id"] == "job-1"


def test_update_scrape_job_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"ok": True})) as mock_post:
        db_client.update_scrape_job(
            "_", "job-1", status="running", progress_completed=5, progress_total=10,
        )

    assert "/api/ingest/job/update" in mock_post.call_args.args[0]
    body = mock_post.call_args.kwargs["json"]
    assert body["job_id"] == "job-1"
    assert body["progress_completed"] == 5


def test_upsert_vpbx_records_posts(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    monkeypatch.setenv("INGEST_API_KEY", "k1")
    from webscraper.ticket_api import db_client

    with patch("requests.post", return_value=_mock_response({"inserted": 1})) as mock_post:
        result = db_client.upsert_vpbx_records("_", [{"handle": "ACG"}], "2024-01-01Z")

    assert "/api/ingest/vpbx/records" in mock_post.call_args.args[0]
    assert result == 1


# ── db_client: read operations proxy to server GET endpoints ──────────────────

def test_get_stats_proxied(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    from webscraper.ticket_api import db_client

    fake = {"db_counts": {"tickets": 42, "handles": 10}}
    with patch("requests.get", return_value=_mock_response(fake)) as mock_get:
        result = db_client.get_stats("_")

    assert "/api/system/status" in mock_get.call_args.args[0]
    assert result == fake


def test_list_tickets_proxied(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    from webscraper.ticket_api import db_client

    fake = {"items": [{"ticket_id": "T1"}], "totalCount": 1, "page": 1, "pageSize": 50}
    with patch("requests.get", return_value=_mock_response(fake)):
        result = db_client.list_tickets("_", handle="ACG")

    assert result["totalCount"] == 1
    assert result["items"][0]["ticket_id"] == "T1"


def test_ensure_indexes_is_noop(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    from webscraper.ticket_api import db_client

    with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
        db_client.ensure_indexes("_")

    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_get_stats_returns_empty_on_failure(monkeypatch):
    monkeypatch.setenv("INGEST_SERVER_URL", "http://unreachable:9999")
    from webscraper.ticket_api import db_client

    # Clear the TTL cache so a cold failure returns {}
    db_client._stats_cache = {}
    db_client._stats_cache_ts = 0.0

    with patch("requests.get", side_effect=ConnectionError("unreachable")):
        result = db_client.get_stats("_")

    assert result == {}


# ── app.py: CLIENT_MODE switch ─────────────────────────────────────────────────

def test_app_uses_db_client_in_client_mode(monkeypatch):
    monkeypatch.setenv("CLIENT_MODE", "1")
    monkeypatch.setenv("INGEST_SERVER_URL", "http://server:8788")
    import webscraper.ticket_api.app as app_mod
    importlib.reload(app_mod)
    assert app_mod.db.__name__ == "webscraper.ticket_api.db_client"


def test_app_uses_real_db_without_client_mode(monkeypatch):
    monkeypatch.delenv("CLIENT_MODE", raising=False)
    import webscraper.ticket_api.app as app_mod
    importlib.reload(app_mod)
    assert app_mod.db.__name__ == "webscraper.ticket_api.db"


# ── ingest_routes: auth enforcement ───────────────────────────────────────────

def test_ingest_rejects_missing_key(ingest_client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "secret123")
    resp = ingest_client.post("/api/ingest/handles", json={"rows": [{"handle": "ACG"}]})
    assert resp.status_code == 403


def test_ingest_rejects_wrong_key(ingest_client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "secret123")
    resp = ingest_client.post(
        "/api/ingest/handles",
        json={"rows": [{"handle": "ACG"}]},
        headers={"X-Ingest-Key": "wrongkey"},
    )
    assert resp.status_code == 403


def test_ingest_accepts_correct_key(ingest_client):
    resp = ingest_client.post(
        "/api/ingest/handles",
        json={"rows": [{"handle": "ACG"}]},
        headers={"X-Ingest-Key": "secret123"},
    )
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1


def test_ingest_localhost_no_key_required(monkeypatch):
    """_require_ingest_auth allows 127.0.0.1 when no key is set."""
    monkeypatch.delenv("INGEST_API_KEY", raising=False)

    from webscraper.ticket_api.ingest_routes import _require_ingest_auth
    from fastapi import Request as _Req

    req = MagicMock(spec=_Req)
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {}

    # Should not raise — localhost is allowed without a key
    _require_ingest_auth(req)


def test_ingest_remote_no_key_is_rejected(monkeypatch):
    """_require_ingest_auth rejects remote hosts when no key is configured."""
    monkeypatch.delenv("INGEST_API_KEY", raising=False)

    from webscraper.ticket_api.ingest_routes import _require_ingest_auth
    from fastapi import HTTPException, Request as _Req

    req = MagicMock(spec=_Req)
    req.client = MagicMock()
    req.client.host = "10.0.0.5"
    req.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        _require_ingest_auth(req)
    assert exc_info.value.status_code == 403


def test_ingest_tickets_roundtrip(ingest_client):
    headers = {"X-Ingest-Key": "secret123"}
    resp = ingest_client.post("/api/ingest/tickets", json={
        "handle": "ACG",
        "tickets": [
            {"ticket_id": "T1", "subject": "Phones down", "status": "open"},
            {"ticket_id": "T2", "subject": "Voicemail full", "status": "closed"},
        ],
    }, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["inserted"] == 2


def test_ingest_handle_progress_roundtrip(ingest_client):
    headers = {"X-Ingest-Key": "secret123"}
    resp = ingest_client.post("/api/ingest/handle-progress", json={
        "handle": "ACG",
        "status": "ok",
        "ticket_count": 5,
    }, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ingest_vpbx_records_roundtrip(ingest_client):
    headers = {"X-Ingest-Key": "secret123"}
    resp = ingest_client.post("/api/ingest/vpbx/records", json={
        "records": [{"handle": "ACG", "name": "ACME Corp", "account_status": "active"}],
        "now_utc": "2024-01-01T00:00:00Z",
    }, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1


def test_ingest_job_create_and_update(ingest_client):
    headers = {"X-Ingest-Key": "secret123"}

    resp = ingest_client.post("/api/ingest/job/create", json={
        "job_id": "job-abc",
        "handle": None,
        "mode": "scrape",
        "ticket_limit": None,
        "status": "queued",
        "created_utc": "2024-01-01T00:00:00Z",
    }, headers=headers)
    assert resp.status_code == 200

    resp = ingest_client.post("/api/ingest/job/update", json={
        "job_id": "job-abc",
        "status": "running",
        "progress_completed": 3,
        "progress_total": 10,
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
