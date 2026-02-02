from __future__ import annotations

import os
from typing import Iterable, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait

from webscraper import site_selectors

from ..healthcheck import is_authenticated
from ..types import AuthContext, StrategyOutcome


def _resolve_edge_binary() -> Optional[str]:
    for env_key in ("EDGE_PATH", "EDGE_BINARY_PATH"):
        candidate = os.environ.get(env_key)
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _build_edge_driver(ctx: AuthContext) -> webdriver.Edge:
    edge_options = EdgeOptions()
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_argument("--ignore-certificate-errors")
    edge_options.add_argument("--allow-insecure-localhost")

    if ctx.user_agent:
        edge_options.add_argument(f"--user-agent={ctx.user_agent}")
    binary_path = _resolve_edge_binary()
    if binary_path:
        edge_options.binary_location = binary_path
    if ctx.headless:
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--no-sandbox")

    driver_path = os.environ.get("EDGEDRIVER_PATH")
    if driver_path and os.path.exists(driver_path):
        service = EdgeService(driver_path)
        return webdriver.Edge(service=service, options=edge_options)
    service = EdgeService()
    return webdriver.Edge(service=service, options=edge_options)


def _selectors_from_site() -> dict[str, list[str]]:
    selectors = getattr(site_selectors, "LOGIN_SELECTORS", None)
    if isinstance(selectors, dict):
        normalized: dict[str, list[str]] = {}
        for key in ("username", "password", "submit"):
            value = selectors.get(key)
            if isinstance(value, str):
                normalized[key] = [value]
            elif isinstance(value, (list, tuple)):
                normalized[key] = [v for v in value if isinstance(v, str)]
        return normalized
    return {}


def _find_first_by_css(driver, selectors: Iterable[str]):
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el:
                return el
        except Exception:
            continue
    return None


def _find_username_input(driver):
    selectors = [
        "input[type='email']",
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[type='text']",
    ]
    return _find_first_by_css(driver, selectors)


def _find_password_input(driver):
    return _find_first_by_css(driver, ["input[type='password']"])


def _find_submit_button(driver):
    selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button[name*='login' i]",
        "button[id*='login' i]",
    ]
    button = _find_first_by_css(driver, selectors)
    if button:
        return button
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button, input[type='button']")
    except Exception:
        buttons = []
    for btn in buttons:
        try:
            text = (btn.text or "").lower()
            if any(token in text for token in ("sign in", "log in", "login")):
                return btn
        except Exception:
            continue
    return None


def attempt_programmatic(ctx: AuthContext) -> StrategyOutcome:
    if not (ctx.username and ctx.password):
        return StrategyOutcome(ok=False, reason="missing_credentials", driver=None)

    try:
        driver = _build_edge_driver(ctx)
    except Exception as exc:
        return StrategyOutcome(ok=False, reason=f"driver_start_failed:{type(exc).__name__}", driver=None)

    try:
        driver.get(ctx.auth_check_url or ctx.base_url)
    except Exception:
        pass

    selectors = _selectors_from_site()
    try:
        wait = WebDriverWait(driver, ctx.timeout_sec)
    except Exception:
        wait = None

    username_input = None
    password_input = None
    submit_button = None

    if selectors:
        username_input = _find_first_by_css(driver, selectors.get("username", []))
        password_input = _find_first_by_css(driver, selectors.get("password", []))
        submit_button = _find_first_by_css(driver, selectors.get("submit", []))

    if not username_input:
        username_input = _find_username_input(driver)
    if not password_input:
        password_input = _find_password_input(driver)
    if not submit_button:
        submit_button = _find_submit_button(driver)

    if not (username_input and password_input and submit_button):
        try:
            driver.quit()
        except Exception:
            pass
        return StrategyOutcome(ok=False, reason="login_form_not_detected", driver=None)

    try:
        username_input.clear()
        username_input.send_keys(ctx.username)
        password_input.clear()
        password_input.send_keys(ctx.password)
        submit_button.click()
    except Exception as exc:
        try:
            driver.quit()
        except Exception:
            pass
        return StrategyOutcome(ok=False, reason=f"login_interaction_failed:{type(exc).__name__}", driver=None)

    try:
        if wait:
            wait.until(lambda d: (d.current_url or "") != (ctx.auth_check_url or ctx.base_url))
    except Exception:
        pass

    try:
        ok, reason = is_authenticated(driver, ctx)
    except Exception as exc:
        ok = False
        reason = f"healthcheck_error:{type(exc).__name__}"

    if ok:
        return StrategyOutcome(ok=True, reason=reason, driver=driver)

    try:
        driver.quit()
    except Exception:
        pass
    return StrategyOutcome(ok=False, reason=reason, driver=None)
