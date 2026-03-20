from datetime import datetime, timedelta, timezone

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
    assert "No target-domain cookies found" in unmatched.json()["detail"]["error"]

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
    assert paste_response.status_code == 200
    assert paste_response.json()["ok"] is True

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


def test_auth_import_rejects_non_target_domain(tmp_path, monkeypatch):
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
    assert "No target-domain cookies found" in response.json()["detail"]["error"]




def test_auth_import_accepts_parent_domain_cookie(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/auth/import",
        json={"text": '[{"name":"sid","value":"x","domain":".123.net","path":"/"}]'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["cookie_count"] >= 1


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

def test_auth_seed_endpoint_auto_mode(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    monkeypatch.setattr(
        appmod,
        "import_cookies_auto",
        lambda **kwargs: {
            "method_used": "cdp",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".secure.123.net", "path": "/"}],
            "warnings": [],
            "details": {"cdp_port": 9222},
        },
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
    assert launch_payload["active_source"] == "cdp_debug_chrome"
    assert launch_payload["last_import_method_attempted"] == "seed_auto"


def test_auth_seed_endpoint_reports_ws_origin_rejection(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    def raise_origin_rejected(*_args, **_kwargs):
        raise appmod.CookieSeedError(
            "CDP_WS_ORIGIN_REJECTED",
            "Chrome CDP websocket origin rejected on port 9222",
            details={"cdp_port": 9222},
        )

    monkeypatch.setattr(appmod, "seed_from_cdp", raise_origin_rejected)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/auth/seed",
        json={"mode": "cdp", "seed_domains": ["secure.123.net"], "cdp_port": 9222},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["details"]["error_code"] == "CDP_WS_ORIGIN_REJECTED"
    assert "origin" in payload["next_step_if_failed"].lower()
    assert "remote-allow-origins" in payload["next_step_if_failed"]


def test_auth_seed_cdp_mode_imports_from_live_session(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(
        appmod,
        "_cdp_diag",
        lambda *_args, **_kwargs: {"json_version_ok": True, "status": "ok", "error": None},
    )
    monkeypatch.setattr(
        appmod,
        "seed_from_cdp",
        lambda *_args, **_kwargs: appmod.SeedResult(
            mode_used="cdp",
            cookies=[{"name": "PHPSESSID", "value": "live", "domain": "secure.123.net", "path": "/"}],
            details={"source": "cdp_debug_chrome"},
        ),
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/seed", json={"mode": "cdp", "seed_domains": ["secure.123.net"], "cdp_port": 9222})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode_used"] == "cdp"
    assert payload["cookie_count"] == 1
    assert payload["source"] == "seed_cdp"


def test_chrome_profiles_endpoint_returns_preferred_profile_1(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "list_browser_profiles", lambda browser: ["Default", "Profile 1", "Profile 2"])

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
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {
            "cdp_port": 9222,
            "json_version_ok": True,
            "ws_connectable": True,
            "status": "ok",
            "error": None,
            "websocket_debugger_url": "ws://127.0.0.1:9222/devtools/browser/test",
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch_debug_chrome", json={"cdp_port": 9222, "profile_name": "Default"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["details"]["cdp_validation"]["status"] == "ok"


def test_launch_debug_chrome_endpoint_surfaces_ws_origin_rejection(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_text("")
    monkeypatch.setenv("CHROME_PATH", str(fake_browser))
    monkeypatch.setattr(appmod, "_detect_browser_path", lambda: fake_browser)
    monkeypatch.setattr(appmod, "launch_debug_chrome", lambda **kwargs: type("P", (), {"pid": 1234})())
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {
            "cdp_port": 9222,
            "json_version_ok": True,
            "ws_connectable": False,
            "status": "ws_origin_rejected",
            "error": "403 Forbidden remote-allow-origins",
            "websocket_debugger_url": "ws://127.0.0.1:9222/devtools/browser/test",
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch_debug_chrome", json={"cdp_port": 9222, "profile_name": "Default"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "origin rejection" in payload["warning"].lower()
    assert "remote-allow-origins" in payload["next_step_if_failed"]


def test_launch_debug_chrome_suppresses_duplicate_launch_when_9222_live(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "launch_debug_chrome", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not launch")))
    monkeypatch.setattr(appmod, "_get_cdp_tab_urls", lambda *_args, **_kwargs: ["about:blank"])
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {
            "cdp_port": 9222,
            "json_version_ok": True,
            "ws_connectable": True,
            "status": "ok",
            "error": None,
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch_debug_chrome", json={"cdp_port": 9222, "profile_name": "Default"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["details"]["already_running"] is True


def test_launch_debug_chrome_reports_target_tab_already_open(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "launch_debug_chrome", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not launch")))
    monkeypatch.setattr(
        appmod,
        "_get_cdp_tab_urls",
        lambda *_args, **_kwargs: ["https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi?x=1"],
    )
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {
            "cdp_port": 9222,
            "json_version_ok": True,
            "ws_connectable": True,
            "status": "ok",
            "error": None,
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch_debug_chrome", json={"cdp_port": 9222, "profile_name": "Default"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["details"]["already_running"] is True
    assert payload["details"]["target_already_open"] is True


def test_auto_seed_blocked_after_recent_fatal_cdp_failure(monkeypatch):
    now = datetime.now(timezone.utc)
    with appmod.AUTO_SEED_STATE_LOCK:
        appmod.AUTO_SEED_STATE["cdp_attach_failed"] = True
        appmod.AUTO_SEED_STATE["fatal_cdp_error_at"] = (now - timedelta(seconds=10)).isoformat()
        appmod.AUTO_SEED_STATE["next_seed_attempt_at"] = appmod._now_ts() + 120
        appmod.AUTO_SEED_STATE["auth_seed_in_progress"] = False

    allowed, reason = appmod._can_attempt_auto_seed()
    assert allowed is False
    assert reason in {"fatal_cdp_attach_error", "retry_cooldown"}


def test_auth_force_reset_and_launch_endpoints(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    reset_called = {"count": 0}
    launch_calls: list[bool] = []

    def fake_reset():
        reset_called["count"] += 1
        return {"ok": True, "removed": ["auth_cookies_db"], "warnings": []}

    def fake_launch(*, force_fresh: bool, target_url: str, timeout_seconds: int):
        launch_calls.append(force_fresh)
        profile = str(tmp_path / ("forced-a" if force_fresh else "ticketing"))
        return {
            "ok": True,
            "forced": force_fresh,
            "cookies_saved": force_fresh,
            "profile_dir": profile,
            "cookie_file": str(tmp_path / "cookies.json"),
            "warnings": [],
        }

    monkeypatch.setattr(appmod.AUTH_MANAGER, "clear_auth_state", fake_reset)
    monkeypatch.setattr(appmod.AUTH_MANAGER, "launch_login", fake_launch)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")

    reset_response = client.post("/api/auth/force-reset", json={})
    assert reset_response.status_code == 200
    assert reset_response.json()["ok"] is True
    assert reset_called["count"] == 1

    launch_reuse = client.post("/api/auth/launch?force=false", json={})
    assert launch_reuse.status_code == 200
    assert launch_reuse.json()["forced"] is False

    launch_force = client.post("/api/auth/launch?force=true", json={})
    assert launch_force.status_code == 200
    assert launch_force.json()["forced"] is True
    assert launch_force.json()["cookies_saved"] is True
    assert launch_calls == [False, True]


def test_force_relogin_sanity_flow_uses_unique_profile_dirs(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    cookie_file = tmp_path / "cookies.json"
    launch_counter = {"n": 0}

    def fake_reset():
        if cookie_file.exists():
            cookie_file.unlink()
        return {"ok": True, "removed": [str(cookie_file)], "warnings": []}

    def fake_launch(*, force_fresh: bool, target_url: str, timeout_seconds: int):
        launch_counter["n"] += 1
        profile_dir = tmp_path / f"forced-{launch_counter['n']}"
        if force_fresh:
            cookie_file.write_text('[{"name":"sid","value":"abc","domain":"secure.123.net"}]', encoding="utf-8")
        return {
            "ok": True,
            "forced": force_fresh,
            "cookies_saved": force_fresh,
            "profile_dir": str(profile_dir),
            "cookie_file": str(cookie_file),
            "warnings": ([] if force_fresh else ["login_required"]),
        }

    monkeypatch.setattr(appmod.AUTH_MANAGER, "clear_auth_state", fake_reset)
    monkeypatch.setattr(appmod.AUTH_MANAGER, "launch_login", fake_launch)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")

    reset = client.post("/api/auth/force-reset", json={})
    assert reset.status_code == 200
    assert cookie_file.exists() is False

    launch_without_force = client.post("/api/auth/launch?force=false", json={})
    assert launch_without_force.status_code == 200
    assert launch_without_force.json()["cookies_saved"] is False

    first_force = client.post("/api/auth/launch?force=true", json={})
    second_force = client.post("/api/auth/launch?force=true", json={})
    assert first_force.status_code == 200
    assert second_force.status_code == 200
    assert cookie_file.exists() is True
    assert first_force.json()["profile_dir"] != second_force.json()["profile_dir"]


def test_auth_browser_import_routes_exist(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(
        appmod,
        "seed_from_disk",
        lambda *_args, **_kwargs: appmod.SeedResult(
            mode_used="disk",
            cookies=[{"name": "sid", "value": "x", "domain": "secure.123.net", "path": "/"}],
            details={"profile_name": "Default"},
        ),
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    for route in [
        "/api/auth/import_from_browser",
        "/api/auth/sync_from_browser",
        "/api/auth/import-from-browser",
        "/api/auth/import-browser",
        "/api/auth/sync-from-browser",
    ]:
        ok = client.post(route, json={"browser": "chrome", "profile": "Default", "domain": "secure.123.net"})
        assert ok.status_code == 200
        bad = client.post(route, json={"browser": 123})
        assert bad.status_code in {200, 422}


def test_auth_seed_overwrites_paste_source_with_cdp(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_is_cdp_available", lambda *_args, **_kwargs: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    imported = client.post("/api/auth/import", json={"text": '[{"name":"sid","value":"old","domain":"secure.123.net"}]'})
    assert imported.status_code == 200
    assert imported.json()["source"] == "paste"

    monkeypatch.setattr(
        appmod,
        "import_cookies_auto",
        lambda **kwargs: {
            "method_used": "cdp",
            "cookies": [{"name": "sid", "value": "new", "domain": ".secure.123.net", "path": "/"}],
            "warnings": [],
            "details": {"cdp_port": 9222},
        },
    )

    launch = client.post(
        "/api/auth/seed",
        json={"mode": "auto", "chrome_profile_dir": "Profile 1", "seed_domains": ["secure.123.net"], "cdp_port": 9222},
    )
    assert launch.status_code == 200
    payload = launch.json()
    assert payload["source"] == "seed_cdp"
    assert payload["active_source"] == "cdp_debug_chrome"
    assert payload["last_import_result"]["overwritten_from"] == "paste"


def test_import_from_browser_query_params_override_payload(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    captured: dict[str, object] = {}

    def fake_seed_from_disk(profile_dir, domains, *, profile_name=None, browser="chrome"):
        captured["profile_dir"] = profile_dir
        captured["domains"] = domains
        captured["profile_name"] = profile_name
        captured["browser"] = browser
        return appmod.SeedResult(
            mode_used="disk",
            cookies=[{"name": "sid", "value": "x", "domain": "secure.123.net", "path": "/"}],
            details={},
        )

    monkeypatch.setattr(appmod, "seed_from_disk", fake_seed_from_disk)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/auth/import_from_browser?browser=edge&profile=Profile%201&domain=secure.123.net",
        json={"browser": "chrome", "profile": "Default", "domain": "123.net"},
    )
    assert response.status_code == 200
    assert captured["browser"] == "edge"
    assert captured["profile_name"] == "Profile 1"


def test_import_from_browser_prefers_disk_over_cdp_when_cdp_live(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {
            "cdp_port": 9222,
            "json_version_ok": True,
            "ws_connectable": True,
            "status": "ok",
            "error": None,
        },
    )

    called = {"disk": 0, "cdp": 0}

    def fake_disk(*_args, **_kwargs):
        called["disk"] += 1
        return appmod.SeedResult(
            mode_used="disk",
            cookies=[{"name": "sid", "value": "x", "domain": "secure.123.net", "path": "/"}],
            details={},
        )

    def fake_cdp(*_args, **_kwargs):
        called["cdp"] += 1
        return appmod.SeedResult(mode_used="cdp", cookies=[], details={})

    monkeypatch.setattr(appmod, "seed_from_disk", fake_disk)
    monkeypatch.setattr(appmod, "seed_from_cdp", fake_cdp)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/auth/import_from_browser",
        json={"browser": "chrome", "profile": "Profile 1", "domain": "secure.123.net"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["method_used"] == "disk"
    assert called["disk"] == 1
    assert called["cdp"] == 0


def test_browser_detect_with_explicit_chrome(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "list_browser_profiles", lambda browser: ["Default"] if browser == "chrome" else [])
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {"json_version_ok": True, "status": "ok", "error": None},
    )
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {
            "tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80}],
            "secure_tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80}],
            "preferred_tab": {"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80},
            "cookies": [{"name": "sid", "value": "x", "domain": "secure.123.net", "path": "/"}],
            "cookie_names": ["sid"],
            "cookie_error": None,
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/browser/detect", json={"browser": "chrome", "cdp_port": 9222})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["browser"] == "chrome"
    assert payload["data"]["status"] == "ready"


def test_browser_detect_defaults_to_chrome_when_omitted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    seen: dict[str, str] = {}

    def fake_profiles(browser: str):
        seen["browser"] = browser
        return []

    monkeypatch.setattr(appmod, "list_browser_profiles", fake_profiles)
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {"json_version_ok": False, "status": "no_browser", "error": "down"},
    )
    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/browser/detect", json={})
    assert response.status_code == 200
    assert seen["browser"] == "chrome"
    assert response.json()["data"]["status"] == "no_debug_browser_running"


def test_browser_detect_rejects_invalid_browser_name(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "list_browser_profiles", lambda browser: (_ for _ in ()).throw(ValueError(f"Unsupported browser '{browser}'")))

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/browser/detect", json={"browser": "firefox"})
    assert response.status_code == 400
    assert "Unsupported browser" in response.json()["detail"]


def test_browser_detect_reports_missing_authenticated_session(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "list_browser_profiles", lambda _browser: ["Default"])
    monkeypatch.setattr(
        appmod,
        "cdp_availability",
        lambda *_args, **_kwargs: {"json_version_ok": True, "status": "ok", "error": None},
    )
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {
            "tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80}],
            "secure_tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80}],
            "preferred_tab": {"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80},
            "cookies": [],
            "cookie_names": [],
            "cookie_error": None,
        },
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/browser/detect", json={"browser": "chrome"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "no_authenticated_secure_session"
    assert payload["data"]["authenticated_session"] is False
    assert payload["data"]["unauthenticated_reason"] == "no_cookies_returned"


def test_inspect_live_secure_session_prefers_secure_tab_over_about_blank(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"id": "1", "type": "page", "url": "about:blank", "title": "New Tab"},
                {"id": "2", "type": "page", "url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers"},
            ]

    monkeypatch.setattr(appmod.requests, "get", lambda *_args, **_kwargs: _Resp())
    monkeypatch.setattr(
        appmod,
        "_inspect_target_session_via_cdp",
        lambda **_kwargs: {
            "cookies": [{"name": "PHPSESSID", "value": "x", "domain": "secure.123.net", "path": "/"}],
            "cookie_names": ["PHPSESSID"],
            "cookie_domains": ["secure.123.net:/"],
            "candidate_auth_cookie_names": ["PHPSESSID"],
            "auth_cookie_candidate_present": True,
            "final_document_url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
            "document_title": "Customers",
            "dom_login_marker_detected": False,
            "authenticated_probe_ok": True,
            "cookie_error": None,
            "cookie_inspection_context": "target:2",
            "decision_tree": [{"step": "cookie_inspection", "result": "ok", "reason": "cookies=1 auth_candidates=1"}],
        },
    )
    result = appmod._inspect_live_secure_session(9222)
    assert result["preferred_tab"]["url"].startswith("https://secure.123.net")
    assert result["cookie_names"] == ["PHPSESSID"]
    assert result["authenticated_probe_ok"] is True
    assert result["auth_cookie_present"] is True


def test_auth_validate_returns_reasons_when_missing(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/validate?domain=secure.123.net")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert isinstance(payload.get("reasons"), list)
    assert payload["reasons"]


def test_validate_auth_reports_no_secure_tab_found(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_is_cdp_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {"tabs": [{"url": "about:blank", "title": "New Tab", "matched_domain": False}], "secure_tabs": [], "preferred_tab": None, "cookies": [], "cookie_names": [], "cookie_error": None},
    )

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["reason"] == "no_secure_tab_found"
    assert payload["secure_tab_found"] is False


def test_validate_auth_reports_secure_tab_found_but_not_logged_in(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_is_cdp_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {
            "tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True}],
            "secure_tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True}],
            "preferred_tab": {"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True},
            "cookies": [],
            "cookie_names": [],
            "cookie_error": None,
        },
    )
    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["reason"] == "no_cookies_returned"
    assert payload["secure_tab_found"] is True


def test_validate_auth_imports_live_cookies_and_runs_request_test(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_is_cdp_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {
            "tabs": [
                {"url": "about:blank", "title": "New Tab", "matched_domain": False, "score": -100},
                {"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80},
            ],
            "secure_tabs": [{"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80}],
            "preferred_tab": {"url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi", "title": "Customers", "matched_domain": True, "score": 80},
            "cookies": [{"name": "PHPSESSID", "value": "abc", "domain": "secure.123.net", "path": "/"}],
            "cookie_names": ["PHPSESSID"],
            "cookie_domains": ["secure.123.net:/"],
            "cookie_error": None,
            "auth_cookie_present": True,
            "authenticated_probe_ok": True,
            "unauthenticated_reason": "authenticated",
            "debug": {"decision_tree": [{"step": "authenticated_probe", "result": "ok", "reason": "post_login_url_and_dom_checks_passed"}]},
        },
    )

    class _Resp:
        status_code = 200
        url = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
        text = "<html>customers account search</html>"

    monkeypatch.setattr(appmod.requests, "get", lambda *_args, **_kwargs: _Resp())

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["secure_tab_found"] is True
    assert payload["cookie_import_succeeded"] is True
    assert payload["authenticated_request_test_succeeded"] is True
    assert payload["authenticated"] is True


def test_derive_unauthenticated_reason_cookie_candidates_missing():
    reason = appmod._derive_unauthenticated_reason(
        secure_tab_found=True,
        cookie_error=None,
        cookie_count=3,
        auth_cookie_present=False,
        dom_login_marker_detected=False,
        authenticated_probe_ok=False,
    )
    assert reason == "cookies_returned_but_no_auth_cookie_candidate"


def test_auth_detect_debug_returns_decision_tree(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_is_cdp_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        appmod,
        "_inspect_live_secure_session",
        lambda *_args, **_kwargs: {
            "secure_tabs": [{"id": "2"}],
            "cookies": [{"name": "PHPSESSID", "value": "x", "domain": "secure.123.net", "path": "/"}],
            "cookie_names": ["PHPSESSID"],
            "cookie_domains": ["secure.123.net:/"],
            "auth_cookie_present": True,
            "authenticated_probe_ok": True,
            "unauthenticated_reason": "authenticated",
            "debug": {"decision_tree": [{"step": "authenticated_probe", "result": "ok", "reason": "post_login_url_and_dom_checks_passed"}]},
        },
    )
    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/detect_debug")
    assert response.status_code == 200
    payload = response.json()
    assert payload["secure_tab_detected"] is True
    assert payload["authenticated_probe_ok"] is True
    assert payload["debug"]["decision_tree"]


def test_auth_validate_response_includes_debug_fields(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/auth/validate?domain=secure.123.net")
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "authenticated",
        "validation_mode",
        "source",
        "browser",
        "profile",
        "cookie_count",
        "domains",
        "required_cookie_names_present",
        "missing_required_cookie_names",
        "validation_probe_url",
        "validation_http_status",
        "validation_reason",
    ):
        assert key in payload


def test_launch_login_browser_route_exists_without_404(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)
    monkeypatch.setattr(appmod, "_is_localhost_request", lambda request: True)
    monkeypatch.setattr(appmod, "_detect_browser_path", lambda: tmp_path / "browser.exe")
    monkeypatch.setattr(appmod.subprocess, "Popen", lambda *args, **kwargs: object())

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.post("/api/auth/launch-browser", json={"url": "https://secure.123.net"})
    assert response.status_code == 200
    payload = response.json()
    assert "ok" in payload
    assert "profile_dir" in payload


def test_handles_endpoint_shape_matches_ticket_ui_expectations(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tickets.sqlite")
    _seed_db(db_path)
    monkeypatch.setenv("TICKETS_DB", db_path)

    client = TestClient(appmod.app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/handles?limit=50&offset=0")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("items"), list)
    assert payload["items"], "Expected at least one handle row"
    first = payload["items"][0]
    assert "handle" in first
