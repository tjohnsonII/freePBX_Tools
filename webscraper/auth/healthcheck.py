from __future__ import annotations

from typing import Tuple

from selenium.webdriver.common.by import By

from .types import AuthContext


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
    selectors = [
        "input#search_phrase",
        "#index_to_search",
        "#search_results",
        "#submit",
    ]
    for sel in selectors:
        try:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                return True
        except Exception:
            continue
    return False


def _has_enough_dom_content(driver) -> bool:
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        return (len(links) + len(inputs)) >= 5
    except Exception:
        return False


def is_authenticated(driver, ctx: AuthContext) -> Tuple[bool, str]:
    target_url = ctx.auth_check_url or ctx.base_url
    try:
        driver.get(target_url)
    except Exception as exc:
        return False, f"navigation_failed:{type(exc).__name__}"

    current_url = _current_url(driver, target_url)
    lowered_url = current_url.lower()
    if any(token in lowered_url for token in ("login", "signin", "sign-in", "sso")):
        return False, "login_url_detected"

    source = _page_source(driver)
    login_markers = ("sign in", "login", "username", "password")
    if any(marker in source for marker in login_markers):
        if _has_password_input(driver):
            return False, "login_markers_present"

    if _has_expected_logged_in_elements(driver):
        return True, "expected_logged_in_elements_present"

    if _has_password_input(driver):
        return False, "password_input_present"

    if not any(marker in source for marker in login_markers) and _has_enough_dom_content(driver):
        return True, "no_login_markers_and_dom_content_present"

    return False, "auth_not_confirmed"
