from __future__ import annotations

import logging
import os

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
