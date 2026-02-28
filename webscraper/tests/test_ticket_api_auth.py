from pathlib import Path

import pytest
from fastapi import HTTPException

from webscraper.ticket_api.app import (
    _detect_browser_path,
    _sanitize_profile_name,
    map_batch_mode,
)
from webscraper.ticket_api.auth import (
    dedupe_and_filter_expired,
    parse_cookies,
    parse_cookies_from_cookie_header,
    parse_cookies_from_json,
    parse_cookies_from_netscape,
)


def test_mode_mapping_latest_to_incremental():
    assert map_batch_mode("latest") == "incremental"
    assert map_batch_mode("full") == "full"


def test_parse_json_cookie_array():
    cookies = parse_cookies_from_json('[{"name":"sid","value":"x","domain":"secure.123.net"}]')
    assert len(cookies) == 1
    assert cookies[0].domain == "secure.123.net"


def test_parse_json_wrapper_and_playwright():
    wrapper = parse_cookies_from_json('{"cookies":[{"name":"a","value":"1","domain":"123.net"}]}')
    assert len(wrapper) == 1
    playwright = parse_cookies_from_json('{"cookies":[{"name":"sid","value":"x","domain":"secure.123.net"}],"origins":[]}')
    assert len(playwright) == 1


def test_parse_netscape_cookie_text_http_only_prefix():
    payload = """# Netscape HTTP Cookie File
#HttpOnly_.secure.123.net\tTRUE\t/\tTRUE\t2730000000\tsid\tabc
"""
    cookies = parse_cookies_from_netscape(payload)
    assert len(cookies) == 1
    assert cookies[0].domain == ".secure.123.net"
    assert cookies[0].httpOnly is True


def test_parse_cookie_header_with_default_domain():
    cookies = parse_cookies_from_cookie_header("Cookie: sid=abc; csrftoken=xyz", ".123.net")
    assert len(cookies) == 2
    assert {c.domain for c in cookies} == {".123.net"}


def test_parse_auto_detect_header_without_filename_hint():
    parsed, fmt = parse_cookies("a=b; c=d", "payload.txt", ".123.net")
    assert fmt == "cookie_header"
    assert len(parsed) == 2


def test_drop_expired_and_dedupe_keep_latest():
    cookies = parse_cookies_from_json(
        """[
        {"name":"sid","value":"old","domain":"secure.123.net","path":"/","expires":999},
        {"name":"sid","value":"new","domain":"secure.123.net","path":"/","expires":4102444800},
        {"name":"keep","value":"1","domain":"secure.123.net","path":"/"}
    ]"""
    )
    kept, dropped = dedupe_and_filter_expired(cookies, now_ts=1700000000)
    assert dropped == 1
    assert len(kept) == 2
    sid = [c for c in kept if c.name == "sid"][0]
    assert sid.value == "new"


def test_sanitize_profile_name_replaces_unsafe_chars():
    assert _sanitize_profile_name("ticketing:qa/user") == "ticketing_qa_user"


def test_detect_browser_prefers_chrome_path(monkeypatch, tmp_path):
    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_text("")
    monkeypatch.setenv("CHROME_PATH", str(fake_browser))
    assert _detect_browser_path() == fake_browser


def test_detect_browser_missing_raises_clear_error(monkeypatch):
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setenv("ProgramFiles", str(Path("/tmp/does-not-exist-program-files")))
    monkeypatch.setenv("ProgramFiles(x86)", str(Path("/tmp/does-not-exist-program-files-x86")))
    monkeypatch.setenv("LOCALAPPDATA", str(Path("/tmp/does-not-exist-local-app-data")))

    with pytest.raises(HTTPException) as exc:
        _detect_browser_path()

    assert exc.value.status_code == 500
    assert "CHROME_PATH" in str(exc.value.detail)
