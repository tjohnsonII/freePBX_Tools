from fastapi.testclient import TestClient

from webscraper.db import init_db, start_run, upsert_handle, upsert_tickets
from webscraper.ticket_api import app as appmod
from webscraper.ticket_api import db as ticket_db


def _seed_db(db_path: str) -> None:
    init_db(db_path)
    ticket_db.ensure_indexes(db_path)
    run_id = start_run(db_path, {})
    upsert_handle(db_path, "ABC", "success")
    upsert_handle(db_path, "XYZ", "success")
    upsert_tickets(
        db_path,
        run_id,
        "ABC",
        [
            {
                "ticket_id": "100",
                "title": "Alpha 1",
                "status": "open",
                "updated_utc": "2024-06-01T00:00:00Z",
                "created_utc": "2024-05-01T00:00:00Z",
            },
            {
                "ticket_id": "101",
                "title": "Alpha 2",
                "status": "closed",
                "updated_utc": "2024-06-02T00:00:00Z",
                "created_utc": "2024-05-02T00:00:00Z",
            },
            {
                "ticket_id": "102",
                "title": "Alpha 3",
                "status": "open",
                "updated_utc": "2024-06-02T00:00:00Z",
                "created_utc": "2024-05-03T00:00:00Z",
            },
        ],
    )


def test_handles_summary_endpoint_returns_expected_shape(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/api/handles/summary?q=A&limit=10&offset=0")
    assert response.status_code == 200

    payload = response.json()
    assert payload
    first = payload[0]
    assert set(first.keys()) == {"handle", "last_scrape_utc", "ticket_count", "open_count", "updated_latest_utc"}
    assert first["handle"] == "ABC"


def test_list_tickets_paging_is_stable(tmp_path):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)

    page1 = ticket_db.list_tickets(db_path, handle="ABC", page=1, page_size=2, sort="newest")
    page2 = ticket_db.list_tickets(db_path, handle="ABC", page=2, page_size=2, sort="newest")

    assert [row["ticket_id"] for row in page1["items"]] == ["102", "101"]
    assert [row["ticket_id"] for row in page2["items"]] == ["100"]


def test_handles_all_endpoint_returns_strings(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/api/handles/all?q=A&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == ["ABC"]
    assert payload["count"] == 1


def test_health_endpoint(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["db_exists"] is True
    assert payload["version"]
    assert payload["total_tickets"] == 3


def test_logs_enabled_and_tail_endpoints(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setenv("SCRAPER_ENABLE_LOG_API", "1")

    log_file = appmod.LOG_DIR / "test-ticket-api.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    enabled = client.get("/api/logs/enabled")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    listed = client.get("/api/logs/list")
    assert listed.status_code == 200
    assert any(item["name"] == "test-ticket-api.log" for item in listed.json()["items"])

    tail = client.get("/api/logs/tail", params={"name": "test-ticket-api.log", "lines": 2})
    assert tail.status_code == 200
    assert tail.json()["lines"] == ["line-2", "line-3"]

    log_file.unlink(missing_ok=True)


def test_system_status_endpoint(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/api/system/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_health"] == "ok"
    assert "db_counts" in payload
    assert payload["db_counts"]["tickets"] >= 0
