from __future__ import annotations

import json
import os
import re
from typing import Tuple

from selenium.webdriver.common.by import By

from .types import AuthContext

DEFAULT_AUTH_SELECTORS = (
    "input#search_phrase",
    "#index_to_search",
    "#search_results",
    "#submit",
)

DEFAULT_SESSION_COOKIE_NAMES = (
    "session",
    "sessionid",
    "phpsessid",
    "jsessionid",
    "auth",
    "token",
)


def _split_env_list(raw_value: str) -> tuple[str, ...]:
    if not raw_value:
        return ()
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


def _auth_selectors() -> tuple[str, ...]:
    override = _split_env_list(os.environ.get("SCRAPER_AUTH_SUCCESS_SELECTORS", ""))
    return override or DEFAULT_AUTH_SELECTORS


def _session_cookie_names() -> tuple[str, ...]:
    override = _split_env_list(os.environ.get("SCRAPER_AUTH_SESSION_COOKIES", ""))
    return tuple(name.lower() for name in (override or DEFAULT_SESSION_COOKIE_NAMES))


def _page_source(driver) -> str:
    try:
        return (driver.page_source or "").lower()
    except Exception:
        return ""


def _current_url(driver, fallback: str) -> str:
    try:
        return driver.current_url or fallback
    except Exception:
        return fallback


def _has_password_input(driver) -> bool:
    try:
        return bool(driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))
    except Exception:
        return False


def _has_expected_logged_in_elements(driver) -> bool:
    for sel in _auth_selectors():
        try:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                return True
        except Exception:
            continue
    return False


def _has_session_cookie(driver) -> bool:
    try:
        cookies = driver.get_cookies() or []
    except Exception:
        return False
    allowed_names = _session_cookie_names()
    for cookie in cookies:
        name = str(cookie.get("name", "")).strip().lower()
        if name in allowed_names:
            return True
    return False


def _safe_path(ctx: AuthContext, filename: str) -> str:
    root = os.path.abspath(ctx.output_dir or os.getcwd())
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, filename)


def _sanitize_text_snippet(raw_text: str) -> str:
    compact = re.sub(r"\s+", " ", (raw_text or "").strip())
    return compact[:200]


def _write_auth_diagnostics(driver, ctx: AuthContext, auth_check_url: str, final_url: str) -> None:
    title = ""
    page_text = ""
    page_html = ""
    cookies = []
    try:
        title = driver.title or ""
    except Exception:
        pass
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        pass
    try:
        page_html = driver.page_source or ""
    except Exception:
        pass
    try:
        cookies = driver.get_cookies() or []
    except Exception:
        cookies = []

    cookie_names = [str(cookie.get("name", "")).strip() for cookie in cookies if cookie.get("name")]
    report = {
        "auth_check_url": auth_check_url,
        "final_url": final_url,
        "page_title": title,
        "page_text_first_200": _sanitize_text_snippet(page_text),
        "cookie_count": len(cookies),
        "cookie_names": cookie_names,
    }

    report_path = _safe_path(ctx, "auth_failure_diagnostics.json")
    html_path = _safe_path(ctx, "auth_failure_page.html")
    screenshot_path = _safe_path(ctx, "auth_failure_screenshot.png")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(page_html)
    screenshot_written = False
    try:
        screenshot_written = bool(driver.save_screenshot(screenshot_path))
    except Exception:
        screenshot_written = False

    print(f"[AUTH] auth diagnostics report: {report_path}")
    print(f"[AUTH] auth diagnostics html: {html_path}")
    if screenshot_written:
        print(f"[AUTH] auth diagnostics screenshot: {screenshot_path}")
    else:
        print("[AUTH] auth diagnostics screenshot: unavailable")


def _has_enough_dom_content(driver) -> bool:
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        return (len(links) + len(inputs)) >= 5
    except Exception:
        return False


def auth_confirmed_from_page(
    *,
    current_url: str,
    page_source: str,
    has_password_input: bool,
    has_expected_logged_in_elements: bool,
    has_session_cookie: bool,
    has_enough_dom_content: bool,
) -> Tuple[bool, str]:
    lowered_url = (current_url or "").lower()
    in_app_url = ("/cgi-bin/web_interface/admin/" in lowered_url) or ("customers.cgi" in lowered_url)
    if in_app_url and not any(token in lowered_url for token in ("login", "signin", "sign-in", "sso")):
        return True, "authenticated_url_detected"

    if any(token in lowered_url for token in ("login", "signin", "sign-in", "sso")):
        return False, "login_url_detected"

    source = (page_source or "").lower()
    login_markers = ("sign in", "login", "username", "password")
    if any(marker in source for marker in login_markers) and has_password_input:
        return False, "login_markers_present"

    if has_expected_logged_in_elements:
        return True, "expected_logged_in_elements_present"

    if has_session_cookie:
        return True, "session_cookie_present"

    if has_password_input:
        return False, "password_input_present"

    if not any(marker in source for marker in login_markers) and has_enough_dom_content:
        return True, "no_login_markers_and_dom_content_present"

    return False, "auth_not_confirmed"


def is_authenticated(driver, ctx: AuthContext) -> Tuple[bool, str]:
    target_url = ctx.auth_check_url or ctx.base_url
    try:
        driver.get(target_url)
    except Exception as exc:
        return False, f"navigation_failed:{type(exc).__name__}"

    current_url = _current_url(driver, target_url)
    source = _page_source(driver)
    has_password = _has_password_input(driver)
    ok, reason = auth_confirmed_from_page(
        current_url=current_url,
        page_source=source,
        has_password_input=has_password,
        has_expected_logged_in_elements=_has_expected_logged_in_elements(driver),
        has_session_cookie=_has_session_cookie(driver),
        has_enough_dom_content=_has_enough_dom_content(driver),
    )
    if ok:
        return True, reason

    if reason in {"login_url_detected", "login_markers_present", "password_input_present", "auth_not_confirmed"}:
        _write_auth_diagnostics(driver, ctx, target_url, current_url)
    return False, reason
