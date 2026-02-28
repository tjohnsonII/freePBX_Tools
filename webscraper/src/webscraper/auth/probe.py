from __future__ import annotations

import logging
from typing import Any

import requests

TARGET_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
LOGIN_MARKERS = (
    "name=\"username\"",
    "name='username'",
    "type=\"password\"",
    "type='password'",
    "login",
    "sign in",
)
SUCCESS_MARKERS = ("administration", "account search")

LOGGER = logging.getLogger(__name__)


def _detect_login_page(url: str, body_lower: str) -> bool:
    if "login" in (url or "").lower():
        return True
    return any(marker in body_lower for marker in LOGIN_MARKERS)


def _detect_logged_in(body_lower: str) -> bool:
    return any(marker in body_lower for marker in SUCCESS_MARKERS)


def _probe_session(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=30, allow_redirects=True)
    body_lower = response.text.lower() if isinstance(response.text, str) else ""
    detected_login = _detect_login_page(response.url, body_lower)
    detected_ok = _detect_logged_in(body_lower)
    ok = bool(response.status_code == 200 and detected_ok and not detected_login)

    cookie_names = sorted(session.cookies.keys())
    cookie_domains = sorted({str(cookie.domain or "").lstrip(".").lower() for cookie in session.cookies if getattr(cookie, "domain", None)})
    LOGGER.info(
        "Auth probe (requests): status=%s ok=%s login_page=%s detected_ok=%s cookie_count=%s cookie_names=%s domains=%s",
        response.status_code,
        ok,
        detected_login,
        detected_ok,
        len(cookie_names),
        cookie_names,
        cookie_domains,
    )

    return {
        "ok": ok,
        "status_code": int(response.status_code),
        "detected_login_page": detected_login,
        "detected_ok": detected_ok,
        "cookie_names": cookie_names,
        "cookie_domains": cookie_domains,
        "url": response.url,
        "notes": "authenticated content detected" if ok else "login markers or missing admin markers detected",
    }


def _probe_driver(driver: Any, url: str) -> dict[str, Any]:
    driver.get(url)
    current_url = getattr(driver, "current_url", url)
    html = getattr(driver, "page_source", "") or ""
    body_lower = html.lower()
    detected_login = _detect_login_page(current_url, body_lower)
    detected_ok = _detect_logged_in(body_lower)

    status_code = 200 if html else 0
    ok = bool(status_code == 200 and detected_ok and not detected_login)

    raw_cookies = [cookie for cookie in (driver.get_cookies() or []) if isinstance(cookie, dict)]
    cookie_names = sorted([str(cookie.get("name")) for cookie in raw_cookies if cookie.get("name")])
    cookie_domains = sorted({str(cookie.get("domain") or "").lstrip(".").lower() for cookie in raw_cookies if cookie.get("domain")})
    session_like_names = [name for name in cookie_names if any(marker in name.lower() for marker in ("sess", "session", "sid", "auth", "token", "php"))]
    LOGGER.info(
        "Auth probe (selenium): status=%s ok=%s login_page=%s detected_ok=%s cookie_count=%s cookie_names=%s domains=%s session_like=%s",
        status_code,
        ok,
        detected_login,
        detected_ok,
        len(raw_cookies),
        cookie_names,
        cookie_domains,
        session_like_names,
    )

    return {
        "ok": ok,
        "status_code": status_code,
        "detected_login_page": detected_login,
        "detected_ok": detected_ok,
        "cookie_names": cookie_names,
        "cookie_domains": cookie_domains,
        "session_like_names": session_like_names,
        "url": current_url,
        "notes": "authenticated content detected" if ok else "login markers or missing admin markers detected",
    }


def probe_auth(client: requests.Session | Any, url: str = TARGET_URL) -> dict[str, Any]:
    """Probe authenticated access with either a requests.Session or a Selenium driver."""
    if isinstance(client, requests.Session):
        return _probe_session(client, url)
    if hasattr(client, "get") and hasattr(client, "page_source") and hasattr(client, "get_cookies"):
        return _probe_driver(client, url)
    raise TypeError("probe_auth expects a requests.Session or Selenium WebDriver-like object")
