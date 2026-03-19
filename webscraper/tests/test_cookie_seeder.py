from __future__ import annotations

import json

from webscraper.auth import cookie_seeder


def test_normalize_domains_defaults() -> None:
    assert cookie_seeder.normalize_domains([]) == ["secure.123.net", "123.net"]


def test_seed_auto_falls_back_to_cdp(monkeypatch) -> None:
    def fake_disk(*args, **kwargs):
        raise cookie_seeder.CookieSeedError("DB_LOCKED", "locked")

    def fake_cdp(*args, **kwargs):
        return cookie_seeder.SeedResult(mode_used="cdp", cookies=[{"name": "a", "value": "b", "domain": "secure.123.net"}], details={})

    monkeypatch.setattr(cookie_seeder, "_select_auto_source", lambda *_args, **_kwargs: ("disk", {"cdp_reachable": False}))
    monkeypatch.setattr(cookie_seeder, "seed_from_disk", fake_disk)
    monkeypatch.setattr(cookie_seeder, "seed_from_cdp", fake_cdp)

    result = cookie_seeder.seed_auto(profile_dir="/tmp/none", domains=["secure.123.net"])
    assert result.mode_used == "cdp"
    assert result.details["fallback_reason"] == "DB_LOCKED"


def test_seed_auto_prefers_cdp_when_debug_chrome_reachable(monkeypatch) -> None:
    monkeypatch.setattr(cookie_seeder, "_select_auto_source", lambda *_args, **_kwargs: ("cdp", {"cdp_reachable": True, "cdp_port": 9222}))
    monkeypatch.setattr(
        cookie_seeder,
        "seed_from_cdp",
        lambda *_args, **_kwargs: cookie_seeder.SeedResult(
            mode_used="cdp",
            cookies=[{"name": "sid", "value": "ok", "domain": "secure.123.net"}],
            details={"cdp_port": 9222},
        ),
    )
    disk_called = {"called": False}
    monkeypatch.setattr(cookie_seeder, "seed_from_disk", lambda *_args, **_kwargs: disk_called.update({"called": True}))

    result = cookie_seeder.seed_auto(profile_dir="/tmp/none", domains=["secure.123.net"])

    assert result.mode_used == "cdp"
    assert result.details["auto_selected_source"] == "cdp"
    assert disk_called["called"] is False


def test_auth_doctor_reports_missing_port(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHROME_PATH", str(tmp_path / "missing-chrome.exe"))
    monkeypatch.setenv("CHROME_USER_DATA_DIR", str(tmp_path / "user-data"))

    report = cookie_seeder.auth_doctor(cdp_port=6553)
    checks = {item["check"]: item["ok"] for item in report["checks"]}

    assert checks["CHROME_PATH exists"] is False
    assert checks["CDP port 6553 listening"] is False
    assert report["ok"] is False


def test_cdp_json_version_check_success(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"}).encode("utf-8")

    monkeypatch.setattr(cookie_seeder.urllib_request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    ok, error = cookie_seeder._cdp_json_version_ok(9222)
    assert ok is True
    assert error is None


def test_import_cookies_auto_prefers_disk(monkeypatch) -> None:
    monkeypatch.setattr(cookie_seeder, "_select_auto_source", lambda *_args, **_kwargs: ("disk", {"cdp_reachable": False}))
    monkeypatch.setattr(
        cookie_seeder,
        "seed_from_disk",
        lambda *args, **kwargs: cookie_seeder.SeedResult(
            mode_used="disk",
            cookies=[{"name": "sid", "value": "ok", "domain": "secure.123.net"}],
            details={"profile": "Default"},
        ),
    )

    result = cookie_seeder.import_cookies_auto(profile_dir="/tmp/none", domains=["secure.123.net"])

    assert result["method_used"] == "disk"
    assert result["imported_count"] == 1
    assert result["warnings"] == []


def test_import_cookies_auto_falls_back_to_cdp_when_disk_locked(monkeypatch) -> None:
    monkeypatch.setattr(cookie_seeder, "_select_auto_source", lambda *_args, **_kwargs: ("disk", {"cdp_reachable": False}))
    def fake_disk(*args, **kwargs):
        raise cookie_seeder.CookieSeedError("DB_LOCKED", "locked")

    monkeypatch.setattr(cookie_seeder, "seed_from_disk", fake_disk)
    monkeypatch.setattr(
        cookie_seeder,
        "seed_from_cdp",
        lambda *args, **kwargs: cookie_seeder.SeedResult(
            mode_used="cdp",
            cookies=[{"name": "sid", "value": "ok", "domain": "secure.123.net"}],
            details={"cdp_port": 9222},
        ),
    )

    result = cookie_seeder.import_cookies_auto(profile_dir="/tmp/none", domains=["secure.123.net"])

    assert result["method_used"] == "cdp"
    assert result["imported_count"] == 1
    assert any("switched to CDP" in warning for warning in result["warnings"])


def test_import_cookies_auto_transitions_from_paste_to_cdp(monkeypatch) -> None:
    monkeypatch.setattr(cookie_seeder, "_select_auto_source", lambda *_args, **_kwargs: ("cdp", {"cdp_reachable": True, "cdp_port": 9222}))
    monkeypatch.setattr(
        cookie_seeder,
        "seed_from_cdp",
        lambda *_args, **_kwargs: cookie_seeder.SeedResult(
            mode_used="cdp",
            cookies=[{"name": "sid", "value": "ok", "domain": "secure.123.net"}],
            details={"cdp_port": 9222},
        ),
    )

    result = cookie_seeder.import_cookies_auto(profile_dir="/tmp/none", domains=["secure.123.net"])

    assert result["method_used"] == "cdp"
    assert result["details"]["attempted_sources"][0]["source"] == "cdp_debug_chrome"


def test_browser_user_data_dir_uses_edge_and_chrome_roots(monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")

    chrome_root = cookie_seeder.browser_user_data_dir("chrome")
    edge_root = cookie_seeder.browser_user_data_dir("edge")

    assert "Google" in str(chrome_root) and "Chrome" in str(chrome_root) and "User Data" in str(chrome_root)
    assert "Microsoft" in str(edge_root) and "Edge" in str(edge_root) and "User Data" in str(edge_root)


def test_resolve_profile_dir_prefers_requested_then_default(tmp_path) -> None:
    root = tmp_path / "User Data"
    (root / "Default").mkdir(parents=True)
    (root / "Profile 1").mkdir()

    resolved = cookie_seeder.resolve_profile_dir("edge", "Profile 1", user_data_dir=root)
    assert resolved == root / "Profile 1"

    fallback = cookie_seeder.resolve_profile_dir("edge", "Profile 9", user_data_dir=root)
    assert fallback == root / "Default"


def test_cookie_db_candidates_ordering(tmp_path) -> None:
    profile_dir = tmp_path / "Profile 1"
    expected = [profile_dir / "Network" / "Cookies", profile_dir / "Cookies"]
    assert cookie_seeder.cookie_db_candidates(profile_dir) == expected


def test_launch_debug_chrome_includes_remote_allow_origins(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeProc:
        pid = 444

    def fake_popen(command):
        captured["command"] = command
        return FakeProc()

    monkeypatch.setattr(cookie_seeder.subprocess, "Popen", fake_popen)
    cookie_seeder.launch_debug_chrome(
        chrome_path=tmp_path / "chrome.exe",
        user_data_dir=tmp_path / "debug-profile",
        profile_name="Default",
        port=9222,
    )
    command = list(captured["command"])
    assert "--remote-debugging-port=9222" in command
    assert "--remote-allow-origins=http://127.0.0.1:9222" in command
    assert "--remote-allow-origins=*" in command


def test_cdp_availability_no_browser(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(cookie_seeder.urllib_request, "urlopen", boom)
    availability = cookie_seeder.cdp_availability(9222, check_ws=True)
    assert availability["status"] == "no_browser"
    assert availability["json_version_ok"] is False
    assert availability["ws_connectable"] is False


def test_cdp_availability_detects_ws_origin_rejection(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"}).encode("utf-8")

    monkeypatch.setattr(cookie_seeder.urllib_request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    def fail_ws(*_args, **_kwargs):
        raise RuntimeError(
            "Handshake status 403 Forbidden - Rejected an incoming WebSocket connection from the http://127.0.0.1:9222 origin. "
            "Use the command line flag --remote-allow-origins=http://127.0.0.1:9222"
        )

    monkeypatch.setattr(cookie_seeder, "create_connection", fail_ws)
    availability = cookie_seeder.cdp_availability(9222, check_ws=True)
    assert availability["status"] == "ws_origin_rejected"
    assert availability["json_version_ok"] is True
    assert availability["ws_connectable"] is False


def test_cdp_availability_success(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"}).encode("utf-8")

    class FakeWs:
        def close(self):
            return None

    monkeypatch.setattr(cookie_seeder.urllib_request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(cookie_seeder, "create_connection", lambda *_args, **_kwargs: FakeWs())
    availability = cookie_seeder.cdp_availability(9222, check_ws=True)
    assert availability["status"] == "ok"
    assert availability["json_version_ok"] is True
    assert availability["ws_connectable"] is True
