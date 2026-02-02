from __future__ import annotations

import json
import os
import tempfile
from typing import Iterable, Optional

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from ..healthcheck import is_authenticated
from ..types import AuthContext, StrategyOutcome


def _resolve_edge_binary() -> Optional[str]:
    for env_key in ("EDGE_PATH", "EDGE_BINARY_PATH"):
        candidate = os.environ.get(env_key)
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _build_edge_driver(ctx: AuthContext, profile_dir: str) -> webdriver.Edge:
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
    if profile_dir:
        edge_options.add_argument(f"--user-data-dir={profile_dir}")
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


def _first_cookie_file(paths: Iterable[str]) -> Optional[str]:
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None


def _parse_json_cookies(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        return [item for item in payload.get("cookies") if isinstance(item, dict)]
    return []


def _parse_netscape_cookie_line(line: str) -> Optional[dict]:
    if not line or line.startswith("#"):
        return None
    parts = line.split("\t")
    if len(parts) < 7:
        return None
    domain, _, path, secure, expiry, name, value = parts[:7]
    if name.startswith("#HttpOnly_"):
        name = name.replace("#HttpOnly_", "", 1)
    cookie: dict = {
        "domain": domain.strip(),
        "path": path.strip() or "/",
        "name": name.strip(),
        "value": value.strip(),
        "secure": secure.strip().lower() == "true",
    }
    if expiry and expiry.strip().isdigit():
        cookie["expiry"] = int(expiry.strip())
    return cookie


def _load_cookies_from_file(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except Exception:
        return []

    try:
        payload = json.loads(content)
        return _parse_json_cookies(payload)
    except Exception:
        pass

    cookies: list[dict] = []
    for line in content.splitlines():
        parsed = _parse_netscape_cookie_line(line.strip())
        if parsed:
            cookies.append(parsed)
    return cookies


def _sanitize_cookie(cookie: dict) -> dict:
    allowed = {"name", "value", "domain", "path", "secure", "httpOnly", "expiry"}
    return {k: v for k, v in cookie.items() if k in allowed and v is not None}


def attempt_manual(ctx: AuthContext) -> StrategyOutcome:
    cookie_path = _first_cookie_file(ctx.cookie_files)
    if not cookie_path:
        return StrategyOutcome(ok=False, reason="no_cookie_files_found", driver=None)

    profile_dir = tempfile.mkdtemp(prefix="ws_auth_profile_")
    try:
        driver = _build_edge_driver(ctx, profile_dir)
    except Exception as exc:
        return StrategyOutcome(ok=False, reason=f"driver_start_failed:{type(exc).__name__}", driver=None)

    try:
        driver.get(ctx.base_url)
    except Exception:
        pass

    cookies = _load_cookies_from_file(cookie_path)
    if not cookies:
        try:
            driver.quit()
        except Exception:
            pass
        return StrategyOutcome(ok=False, reason="cookie_file_empty_or_unreadable", driver=None)

    added = 0
    for cookie in cookies:
        sanitized = _sanitize_cookie(cookie)
        if not sanitized.get("name") or "value" not in sanitized:
            continue
        try:
            driver.add_cookie(sanitized)
            added += 1
        except Exception:
            continue

    if not added:
        try:
            driver.quit()
        except Exception:
            pass
        return StrategyOutcome(ok=False, reason="cookie_injection_failed", driver=None)

    try:
        driver.refresh()
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
