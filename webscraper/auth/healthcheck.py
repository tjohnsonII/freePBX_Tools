from __future__ import annotations

from typing import Tuple

from selenium.webdriver.common.by import By

from webscraper import login_heuristics

from .types import AuthContext


def _page_text(driver) -> str:
    try:
        return (driver.find_element(By.TAG_NAME, "body").text or "").lower()
    except Exception:
        return ""


def _has_login_form(driver, selectors: list[str]) -> bool:
    try:
        for sel in selectors:
            try:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    try:
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if password_inputs:
            return True
        forms = driver.find_elements(By.CSS_SELECTOR, "form")
        return bool(forms) and bool(password_inputs)
    except Exception:
        return False


def _contains_marker(text: str, markers: list[str]) -> bool:
    for marker in markers:
        if marker and marker.lower() in text:
            return True
    return False


def is_authenticated(driver, ctx: AuthContext) -> Tuple[bool, str]:
    target_url = ctx.auth_check_url or ctx.base_url
    try:
        driver.get(target_url)
    except Exception as exc:
        return False, f"navigation_failed: {type(exc).__name__}"

    current_url = ""
    try:
        current_url = driver.current_url or ""
    except Exception:
        current_url = target_url

    lowered_url = current_url.lower()
    if any(token in lowered_url for token in ("login", "signin", "sign-in", "auth", "sso")):
        return False, "redirected_to_login_url"

    try:
        if not login_heuristics.ensure_authenticated(driver, target_url):
            return False, "login_heuristics_detected_login_page"
    except Exception:
        pass

    body_text = _page_text(driver)
    if any(token in body_text for token in ("unauthorized", "forbidden", "access denied", "sign in", "log in")):
        return False, "page_text_indicates_auth_required"

    login_form_selectors = ctx.login_form_selectors or [
        "input[type='password']",
        "input[name*='user' i]",
        "input[name*='pass' i]",
        "form[action*='login' i]",
    ]
    if _has_login_form(driver, login_form_selectors):
        return False, "login_form_detected"

    if ctx.logged_in_selectors:
        for sel in ctx.logged_in_selectors:
            try:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    return True, "logged_in_selector_present"
            except Exception:
                continue

    if _contains_marker(body_text, ctx.logged_in_markers):
        return True, "logged_in_marker_present"

    if ctx.login_markers and _contains_marker(body_text, ctx.login_markers):
        return False, "login_marker_present"

    if "login" in lowered_url:
        return False, "login_url_detected"

    return True, "no_login_markers_detected"
