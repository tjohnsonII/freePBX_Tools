from fastapi.testclient import TestClient

from webscraper.db import init_db, start_run, upsert_handle, upsert_tickets
from webscraper.ticket_api import app as appmod
from webscraper.ticket_api import db as ticket_db


class _NoopThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        return None


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


def test_scrape_batch_queues_jobs(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod.threading, "Thread", _NoopThread)

    client = TestClient(appmod.app)
    response = client.post("/api/scrape-batch", json={"handles": ["ABC", "XYZ"], "mode": "latest", "limit": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert len(payload["jobIds"]) == 2


def test_list_tickets_paging_is_stable(tmp_path):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)

    page1 = ticket_db.list_tickets(db_path, handle="ABC", page=1, page_size=2, sort="newest")
    page2 = ticket_db.list_tickets(db_path, handle="ABC", page=2, page_size=2, sort="newest")

    assert [row["ticket_id"] for row in page1["items"]] == ["102", "101"]
    assert [row["ticket_id"] for row in page2["items"]] == ["100"]
