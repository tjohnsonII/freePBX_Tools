from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

LOGIN_HINTS = (
    "login",
    "signin",
    "sign-in",
    "sso",
    "auth",
    "oauth",
    "keycloak",
)


def start_driver(
    profile_dir: Path,
    chrome_path: Optional[str],
    chromedriver_path: Optional[str],
) -> webdriver.Chrome:
    profile_dir = profile_dir.expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if chrome_path:
        options.binary_location = chrome_path

    if chromedriver_path:
        service = Service(executable_path=chromedriver_path)
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)


def wait_for_document_ready(driver: webdriver.Chrome, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = str(driver.execute_script("return document.readyState") or "")
            if state == "complete":
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for readyState=complete after {timeout}s")


def looks_like_login(url: str, title: str, html: Optional[str] = None) -> bool:
    haystack = f"{url} {title} {(html or '')}".lower()
    return any(hint in haystack for hint in LOGIN_HINTS)


def ensure_authenticated(
    driver: webdriver.Chrome,
    timeout: int = 300,
    login_hints: list[str] | tuple[str, ...] = LOGIN_HINTS,
) -> None:
    deadline = time.monotonic() + timeout
    hints = tuple(h.lower() for h in login_hints)
    while time.monotonic() < deadline:
        current_url = driver.current_url or ""
        title = driver.title or ""
        html = ""
        try:
            html = driver.page_source
        except Exception:
            html = ""
        looks_login = looks_like_login(current_url, title, html=html) or any(h in f"{current_url} {title} {html}".lower() for h in hints)
        if not looks_login:
            wait_for_document_ready(driver, timeout=30)
            return
        print(
            f"AUTH REQUIRED: Please login in the opened browser window. Waiting up to {timeout} seconds..."
        )
        print(f"[AUTH] login-like page detected url={current_url!r} title={title!r}")
        time.sleep(2)

    raise TimeoutError(f"Authentication was not completed within {timeout} seconds")


def goto_with_auth(driver: webdriver.Chrome, url: str, timeout: int = 300) -> None:
    driver.get(url)
    wait_for_document_ready(driver, timeout=30)
    page_source: Optional[str]
    try:
        page_source = driver.page_source
    except Exception:
        page_source = None

    if looks_like_login(driver.current_url or "", driver.title or "", html=page_source):
        ensure_authenticated(driver, timeout=timeout)
        driver.get(url)
        wait_for_document_ready(driver, timeout=30)
