from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
EXPECTED_COOKIE_NAMES = ["PHPSESSID", "session", "sessionid", "auth", "sso", "JSESSIONID"]

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


def _default_edge_user_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return str(Path(local_app_data) / "Microsoft" / "Edge" / "User Data")
    return str(Path.home() / ".config" / "microsoft-edge")


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


def _build_edge_options(headless: bool, user_data_dir: str, profile_dir: str, user_agent: str | None) -> EdgeOptions:
    options = EdgeOptions()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_dir}")
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


def _build_edge_driver(options: EdgeOptions) -> webdriver.Edge:
    edgedriver_path = os.environ.get("MSEDGEDRIVER_PATH", "").strip() or os.environ.get("EDGEDRIVER_PATH", "").strip()
    if edgedriver_path:
        return webdriver.Edge(service=EdgeService(executable_path=edgedriver_path), options=options)
    return webdriver.Edge(options=options)


def _cookie_is_auth(cookie: dict[str, object]) -> bool:
    name = str(cookie.get("name") or "")
    domain = str(cookie.get("domain") or "").lower()
    return (domain.endswith(".123.net") or domain.endswith("secure.123.net")) and name in EXPECTED_COOKIE_NAMES


def _auth_marker_present(driver: webdriver.Chrome | webdriver.Edge) -> bool:
    current_url = str(driver.current_url or "").lower()
    if "secure.123.net" not in current_url:
        return False
    html = str(driver.page_source or "").lower()
    return "logout" in html or is_authenticated_html(html)


def _wait_for_authentication(driver: webdriver.Chrome | webdriver.Edge, timeout_s: int = 300) -> list[dict[str, object]]:
    deadline = time.time() + timeout_s
    last_cookies: list[dict[str, object]] = []
    while time.time() < deadline:
        last_cookies = driver.get_cookies() or []
        if any(_cookie_is_auth(cookie) for cookie in last_cookies if isinstance(cookie, dict)):
            return last_cookies
        if _auth_marker_present(driver):
            return last_cookies
        time.sleep(1)

    print("Login in the opened browser. Press ENTER here after you are fully logged in.")
    input()
    return driver.get_cookies() or []


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
    browser: str | None = None,
) -> requests.Session:
    selected_browser = (browser or os.environ.get("WEBSCRAPER_BROWSER") or "edge").strip().lower()
    if selected_browser not in {"edge", "chrome"}:
        selected_browser = "edge"
    env_user_data = os.environ.get("EDGE_USER_DATA_DIR", "").strip() if selected_browser == "edge" else os.environ.get("CHROME_USER_DATA_DIR", "").strip()
    chrome_user_data_dir = chrome_user_data_dir or env_user_data or (_default_edge_user_data_dir() if selected_browser == "edge" else _default_chrome_user_data_dir())
    chrome_profile_dir = os.environ.get("EDGE_PROFILE_DIR" if selected_browser == "edge" else "CHROME_PROFILE_DIR", chrome_profile_dir).strip() or "Default"
    requested_ua = user_agent or os.environ.get("USER_AGENT", "").strip() or None
    binary = os.environ.get("EDGE_PATH", "").strip() if selected_browser == "edge" else os.environ.get("CHROME_PATH", "").strip()
    if selected_browser == "edge":
        options = _build_edge_options(
            headless=headless,
            user_data_dir=chrome_user_data_dir,
            profile_dir=chrome_profile_dir,
            user_agent=requested_ua,
        )
        if binary:
            options.binary_location = binary
        driver_path = os.environ.get("MSEDGEDRIVER_PATH", "").strip() or os.environ.get("EDGEDRIVER_PATH", "").strip() or "<auto>"
        print(f"[AUTH] browser=edge binary=\"{binary or '<auto>'}\"")
        print(f"[AUTH] driver=msedgedriver path=\"{driver_path}\"")
        print(f"[AUTH] user_data_dir=\"{chrome_user_data_dir}\" profile=\"{chrome_profile_dir}\"")
        driver = _build_edge_driver(options)
    else:
        options = _build_options(
            headless=headless,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_dir=chrome_profile_dir,
            user_agent=requested_ua,
        )
        if binary:
            options.binary_location = binary
        driver_path = os.environ.get("CHROMEDRIVER_PATH", "").strip() or "<auto>"
        print(f"[AUTH] browser=chrome binary=\"{binary or '<auto>'}\"")
        print(f"[AUTH] driver=chromedriver path=\"{driver_path}\"")
        print(f"[AUTH] user_data_dir=\"{chrome_user_data_dir}\" profile=\"{chrome_profile_dir}\"")
        driver = _build_driver(options)

    selenium_cookies: list[dict[str, object]] = []
    selenium_ua = requested_ua
    try:
        driver.get(url)
        selenium_cookies = _wait_for_authentication(driver, timeout_s=300)
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
