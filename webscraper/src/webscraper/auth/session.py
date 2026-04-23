from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from .cookie_jar import get_cookiejar

LOGGER = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def build_authenticated_session(domain: str = "secure.123.net", prefer_browser: str = "chrome"):  # type: ignore[return]
    import requests
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


def summarize_driver_cookies(driver: object, domains: list[str] | None = None) -> dict[str, object]:
    """Return a summary of cookies held by the Selenium driver.

    Args:
        driver: A Selenium WebDriver instance.
        domains: Optional list of domain strings to filter cookies by.
            Each cookie whose ``domain`` field ends with any entry in this list
            (case-insensitive, leading dot ignored) is included.  When *None*
            (the default), all cookies are included – preserving prior behaviour.
    """
    all_cookies = list(getattr(driver, "get_cookies", lambda: [])() or [])

    if domains is not None:
        # Normalise filter tokens: strip leading dots, lower-case
        filter_suffixes = [d.strip().lstrip(".").lower() for d in domains if d and d.strip()]
        def _domain_matches(cookie: dict) -> bool:  # noqa: E301
            raw = str(cookie.get("domain") or "").strip().lstrip(".").lower()
            return any(raw == s or raw.endswith("." + s) or s.endswith("." + raw) for s in filter_suffixes)
        cookies = [c for c in all_cookies if isinstance(c, dict) and _domain_matches(c)]
    else:
        cookies = [c for c in all_cookies if isinstance(c, dict)]

    names = sorted({str(cookie.get("name")) for cookie in cookies if cookie.get("name")})
    found_domains = sorted(
        {
            str(cookie.get("domain") or "").strip().lstrip(".").lower()
            for cookie in cookies
            if str(cookie.get("domain") or "").strip()
        }
    )
    session_like = [name for name in names if any(marker in name.lower() for marker in ("sess", "session", "sid", "auth", "token", "php"))]
    return {
        "count": len(cookies),
        "domains": found_domains,
        "names": names,
        "session_like_names": session_like,
    }


def selenium_driver_to_requests_session(driver: object, base_url: str):  # type: ignore[return]
    import requests
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
