from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import requests

from .cookie_jar import get_cookiejar

LOGGER = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def build_authenticated_session(domain: str = "secure.123.net", prefer_browser: str = "chrome") -> requests.Session:
    session = requests.Session()
    cookie_jar = get_cookiejar(domain=domain, browser=prefer_browser)
    session.cookies.update(cookie_jar)

    user_agent = os.environ.get("USER_AGENT", _DEFAULT_UA)
    referer = f"https://{domain}/cgi-bin/web_interface/admin/customers.cgi"
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": referer,
        }
    )

    cookie_names = sorted(session.cookies.keys())
    LOGGER.info("Built authenticated requests session with cookie names: %s", cookie_names)
    return session


def summarize_driver_cookies(driver: object) -> dict[str, object]:
    cookies = list(getattr(driver, "get_cookies", lambda: [])() or [])
    names = sorted({str(cookie.get("name")) for cookie in cookies if isinstance(cookie, dict) and cookie.get("name")})
    domains = sorted(
        {
            str(cookie.get("domain") or "").strip().lstrip(".").lower()
            for cookie in cookies
            if isinstance(cookie, dict) and str(cookie.get("domain") or "").strip()
        }
    )
    session_like = [name for name in names if any(marker in name.lower() for marker in ("sess", "session", "sid", "auth", "token", "php"))]
    return {
        "count": len(cookies),
        "domains": domains,
        "names": names,
        "session_like_names": session_like,
    }


def selenium_driver_to_requests_session(driver: object, base_url: str) -> requests.Session:
    session = requests.Session()
    cookies = list(getattr(driver, "get_cookies", lambda: [])() or [])
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name:
            continue
        domain = str(cookie.get("domain") or "").strip().lstrip(".")
        path = str(cookie.get("path") or "/") or "/"
        session.cookies.set(name, value, domain=domain or None, path=path)

    parsed = urlparse(base_url)
    host = parsed.netloc or "secure.123.net"
    referer = f"{parsed.scheme or 'https'}://{host}/cgi-bin/web_interface/admin/customers.cgi"
    user_agent = os.environ.get("USER_AGENT", _DEFAULT_UA)
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": referer,
        }
    )
    return session
