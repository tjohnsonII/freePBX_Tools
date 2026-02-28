from fastapi.testclient import TestClient

from webscraper.db import init_db, start_run, upsert_handle, upsert_tickets
from webscraper.auth.chrome_cookies import SeededProfileResult
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
    assert "must include secure.123.net" in unmatched.json()["detail"]

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
    assert "must include secure.123.net" in paste_response.json()["detail"]

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
    assert "must include secure.123.net" in response.json()["detail"]


def test_launch_seeded_and_import_from_profile_endpoints(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_text("")
    monkeypatch.setenv("CHROME_PATH", str(fake_browser))

    seeded_dir = tmp_path / "seeded_profile"

    def _fake_seed_isolated_profile(*, var_root, chrome_profile_dir=None, seed_domains=None):
        return SeededProfileResult(
            temp_profile_dir=str(seeded_dir),
            cookie_db_path=str(seeded_dir / "Default" / "Network" / "Cookies"),
            seeded_domains=["secure.123.net"],
            domain_counts={".secure.123.net": 2},
        )

    monkeypatch.setattr(appmod, "seed_isolated_profile", _fake_seed_isolated_profile)
    popen_calls = []
    monkeypatch.setattr(appmod.subprocess, "Popen", lambda command: popen_calls.append(command))

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    launch = client.post(
        "/api/auth/launch_seeded",
        json={
            "target_url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
            "chrome_profile_dir": "Default",
            "seed_domains": ["secure.123.net"],
        },
    )
    assert launch.status_code == 200
    launch_payload = launch.json()
    assert launch_payload["ok"] is True
    assert launch_payload["seeded_domains"] == ["secure.123.net"]
    assert popen_calls

    monkeypatch.setattr(
        appmod,
        "load_cookies_from_profile",
        lambda profile_dir, seed_domains: ([{"name": "sid", "value": "abc", "domain": ".secure.123.net", "path": "/"}], {".secure.123.net": 1}),
    )

    imported = client.post(
        "/api/auth/import_from_profile",
        json={"temp_profile_dir": str(seeded_dir), "seed_domains": ["secure.123.net"]},
    )
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["ok"] is True
    assert payload["cookie_count"] == 1
    assert ".secure.123.net" in payload["domains"]
