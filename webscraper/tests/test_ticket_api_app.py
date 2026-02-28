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




def test_scrape_handles_endpoint_queues_single_batch_job(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod.threading, "Thread", _NoopThread)

    client = TestClient(appmod.app)
    response = client.post("/api/scrape/handles", json={"handles": ["abc", "ABC", "XYZ"], "mode": "normal"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["queued"] == ["ABC", "XYZ"]

    job = ticket_db.get_scrape_job(db_path, payload["job_id"])
    assert job is not None
    assert job["mode"] == "selected"
    assert job["handles"] == ["ABC", "XYZ"]


def test_scrape_handles_endpoint_rejects_invalid(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    empty = client.post("/api/scrape/handles", json={"handles": [], "mode": "normal"})
    assert empty.status_code == 400

    invalid = client.post("/api/scrape/handles", json={"handles": ["ABC", "BAD-HANDLE"], "mode": "normal"})
    assert invalid.status_code == 400
    detail = invalid.json()["detail"]
    assert detail["invalid_handles"] == ["BAD-HANDLE"]


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


def test_health_includes_db_flags(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["db_exists"] is True
    assert payload["version"]
    assert payload["stats"]["tickets"] == 3


def test_auth_cookie_endpoints_localhost(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")

    missing_file = client.post("/api/auth/import-file", data={})
    assert missing_file.status_code == 400
    assert "detail" in missing_file.json()

    bad_ext = client.post(
        "/api/auth/import-file",
        files={"file": ("cookies.csv", b"name,value", "text/csv")},
    )
    assert bad_ext.status_code == 400
    assert "parsed 0 cookies" in bad_ext.json()["detail"].lower()

    unmatched = client.post(
        "/api/auth/import-file",
        files={"file": ("cookies.json", b'[{"name":"sid","value":"x","domain":"example.com"}]', "application/json")},
    )
    assert unmatched.status_code == 400
    assert "No secure.123.net cookies found" in unmatched.json()["detail"]

    valid = client.post(
        "/api/auth/import-file",
        files={"file": ("cookies.json", b'[{"name":"sid","value":"x","domain":"secure.123.net"}]', "application/json")},
    )
    assert valid.status_code == 200
    payload = valid.json()
    assert payload["ok"] is True
    assert payload["cookie_count"] == 1
    assert payload["source"] == "file"

    status_response = client.get("/api/auth/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["cookie_count"] >= 1
    assert status_payload["last_imported"]
    assert status_payload["source"] == "file"

    paste_response = client.post("/api/auth/import-text", json={"text": "Cookie: sid=abc; csrftoken=def"})
    assert paste_response.status_code == 400
    assert "No secure.123.net cookies found" in paste_response.json()["detail"]

    paste_valid = client.post(
        "/api/auth/import-text",
        json={"text": '[{"name":"sid2","value":"y","domain":"secure.123.net"}]', "format": "json"},
    )
    assert paste_valid.status_code == 200
    assert paste_valid.json()["source"] == "paste"

    clear_response = client.post("/api/auth/clear", json={})
    assert clear_response.status_code == 200
    assert clear_response.json()["ok"] is True


def test_auth_cookie_endpoints_reject_non_localhost(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: False)

    client = TestClient(appmod.app)
    assert client.post("/api/auth/import-file", files={"file": ("cookies.json", b"[]", "application/json")}).status_code == 403
    assert client.get("/api/auth/status").status_code == 403
    assert client.post("/api/auth/clear", json={}).status_code == 403
    assert client.post("/api/auth/import-text", json={"text": "Cookie: sid=abc", "format": "header"}).status_code == 403


def test_auth_doctor_endpoint_reports_multipart_and_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app)
    response = client.get("/api/auth/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["multipart_installed"] is True
    assert payload["db_exists"] is True
    assert payload["auth_cookie_table_ready"] is True


def test_auth_import_rejects_wrong_domain(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/auth/import",
        json={"text": '[{"name":"sid","value":"x","domain":".webextension.org"}]'},
    )

    assert response.status_code == 400
    assert "No secure.123.net cookies found" in response.json()["detail"]


def test_auth_seed_endpoint_auto_mode(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    monkeypatch.setattr(
        appmod,
        "seed_auto",
        lambda **kwargs: appmod.seed_from_cdp(9222, ["secure.123.net"]),
    )
    monkeypatch.setattr(
        appmod,
        "seed_from_cdp",
        lambda cdp_port, domains: appmod.SeedResult(
            mode_used="cdp",
            cookies=[{"name": "sid", "value": "abc", "domain": ".secure.123.net", "path": "/"}],
            details={"cdp_port": 9222},
        ),
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    launch = client.post(
        "/api/auth/seed",
        json={
            "mode": "auto",
            "chrome_profile_dir": "Profile 1",
            "seed_domains": ["secure.123.net"],
            "cdp_port": 9222,
        },
    )
    assert launch.status_code == 200
    launch_payload = launch.json()
    assert launch_payload["ok"] is True
    assert launch_payload["mode_used"] == "cdp"
    assert launch_payload["cookie_count"] == 1


def test_chrome_profiles_endpoint_returns_preferred_profile_1(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "list_chrome_profile_dirs", lambda: ["Default", "Profile 1", "Profile 2"])

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/chrome_profiles")
    assert response.status_code == 200
    payload = response.json()
    assert payload["profiles"] == ["Default", "Profile 1", "Profile 2"]
    assert payload["preferred"] == "Profile 1"


def test_launch_debug_chrome_endpoint(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_text("")
    monkeypatch.setenv("CHROME_PATH", str(fake_browser))

    monkeypatch.setattr(appmod, "_detect_browser_path", lambda: fake_browser)
    monkeypatch.setattr(appmod, "launch_debug_chrome", lambda **kwargs: type("P", (), {"pid": 1234})())

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch_debug_chrome", json={"cdp_port": 9222, "profile_name": "Default"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
