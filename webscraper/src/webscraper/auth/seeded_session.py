from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"

_AUTH_MARKERS = (
    "administration",
    "account search",
    "customers",
    "logout",
    "sign out",
)
_LOGIN_MARKERS = (
    '<input type="password"',
    "<input type='password'",
    "name=\"password\"",
    "name='password'",
    "login",
    "sign in",
)


def _default_chrome_user_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return str(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    return str(Path.home() / ".config" / "google-chrome")


def _build_options(headless: bool, chrome_user_data_dir: str, chrome_profile_dir: str, user_agent: str | None) -> Options:
    options = Options()
    options.add_argument(f"--user-data-dir={chrome_user_data_dir}")
    options.add_argument(f"--profile-directory={chrome_profile_dir}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    if headless:
        options.add_argument("--headless=new")
    return options


def _build_driver(options: Options) -> webdriver.Chrome:
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "").strip()
    if chromedriver_path:
        return webdriver.Chrome(service=Service(executable_path=chromedriver_path), options=options)
    return webdriver.Chrome(options=options)


def is_authenticated_html(html: str) -> bool:
    body = (html or "").lower()
    if not body.strip():
        return False
    if any(marker in body for marker in _LOGIN_MARKERS):
        return False
    return any(marker in body for marker in _AUTH_MARKERS)


def seed_requests_session_with_selenium(
    url: str,
    headless: bool = False,
    chrome_user_data_dir: str | None = None,
    chrome_profile_dir: str = "Default",
    user_agent: str | None = None,
) -> requests.Session:
    chrome_user_data_dir = (
        chrome_user_data_dir
        or os.environ.get("CHROME_USER_DATA_DIR", "").strip()
        or _default_chrome_user_data_dir()
    )
    chrome_profile_dir = os.environ.get("CHROME_PROFILE_DIR", chrome_profile_dir).strip() or "Default"
    requested_ua = user_agent or os.environ.get("USER_AGENT", "").strip() or None

    options = _build_options(
        headless=headless,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_profile_dir=chrome_profile_dir,
        user_agent=requested_ua,
    )

    driver = _build_driver(options)
    selenium_cookies: list[dict[str, object]] = []
    selenium_ua = requested_ua
    try:
        driver.get(url)
        time.sleep(2)
        selenium_cookies = driver.get_cookies() or []
        cookie_names = sorted(
            str(cookie.get("name"))
            for cookie in selenium_cookies
            if isinstance(cookie, dict) and cookie.get("name")
        )
        LOGGER.info("Seeded auth via Selenium. Cookie names: %s", cookie_names)
        if not selenium_ua:
            selenium_ua = str(driver.execute_script("return navigator.userAgent") or "").strip() or None
    finally:
        driver.quit()

    session = requests.Session()
    referer = url
    session.headers.update(
        {
            "User-Agent": selenium_ua or requests.utils.default_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer,
            "Connection": "keep-alive",
        }
    )

    for cookie in selenium_cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        cookie_kwargs = {"path": str(cookie.get("path") or "/")}
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            cookie_kwargs["domain"] = domain
        session.cookies.set(name=str(name), value=str(value), **cookie_kwargs)

    LOGGER.info("Built seeded requests.Session with cookie names: %s", sorted(session.cookies.keys()))
    return session
