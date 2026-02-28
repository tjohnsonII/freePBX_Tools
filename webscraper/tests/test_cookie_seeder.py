from __future__ import annotations

from webscraper.auth import cookie_seeder


def test_normalize_domains_defaults() -> None:
    assert cookie_seeder.normalize_domains([]) == ["secure.123.net", "123.net"]


def test_seed_auto_falls_back_to_cdp(monkeypatch) -> None:
    def fake_disk(*args, **kwargs):
        raise cookie_seeder.CookieSeedError("DB_LOCKED", "locked")

    def fake_cdp(*args, **kwargs):
        return cookie_seeder.SeedResult(mode_used="cdp", cookies=[{"name": "a", "value": "b", "domain": "secure.123.net"}], details={})

    monkeypatch.setattr(cookie_seeder, "seed_from_disk", fake_disk)
    monkeypatch.setattr(cookie_seeder, "seed_from_cdp", fake_cdp)

    result = cookie_seeder.seed_auto(profile_dir="/tmp/none", domains=["secure.123.net"])
    assert result.mode_used == "cdp"
    assert result.details["fallback_reason"] == "DB_LOCKED"


def test_auth_doctor_reports_missing_port(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHROME_PATH", str(tmp_path / "missing-chrome.exe"))
    monkeypatch.setenv("CHROME_USER_DATA_DIR", str(tmp_path / "user-data"))

    report = cookie_seeder.auth_doctor(cdp_port=6553)
    checks = {item["check"]: item["ok"] for item in report["checks"]}

    assert checks["CHROME_PATH exists"] is False
    assert checks["CDP port 6553 listening"] is False
    assert report["ok"] is False


def test_import_cookies_auto_prefers_disk(monkeypatch) -> None:
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
