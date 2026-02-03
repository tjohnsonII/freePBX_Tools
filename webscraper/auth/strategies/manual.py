from __future__ import annotations

import json
import os
from dataclasses import replace
from typing import Iterable, Optional, Tuple

from selenium import webdriver

from ..healthcheck import is_authenticated
from ..types import AuthContext
from ..driver_factory import create_edge_driver_for_auth


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


def try_manual(ctx: AuthContext) -> Tuple[bool, Optional[webdriver.Edge], str]:
    cookie_path = _first_cookie_file(ctx.cookie_files)
    if not cookie_path:
        return False, None, "no_cookie_files_found"

    print(f"[AUTH] TRY MANUAL cookie={cookie_path}")
    ctx_for_run = replace(ctx, profile_dirs=[], edge_temp_profile=True)
    try:
        driver, _, _, _ = create_edge_driver_for_auth(ctx_for_run)
    except Exception as exc:
        return False, None, f"driver_start_failed:{type(exc).__name__}"

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
        return False, None, "cookie_file_empty_or_unreadable"

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
        return False, None, "cookie_injection_failed"

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
        return True, driver, reason

    try:
        driver.quit()
    except Exception:
        pass
    return False, None, reason
