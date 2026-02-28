from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional, Tuple

from selenium import webdriver

from ..driver_factory import create_edge_driver_for_auth
from ..healthcheck import is_authenticated
from ..types import AuthContext

_MANUAL_PROMPTED = False


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


def _manual_output_dir(base_dir: str) -> str:
    root = base_dir or os.path.join("webscraper", "output", "auth_manual")
    return os.path.join(root, "auth_manual") if base_dir else root


def _read_prompt_line() -> str:
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.rstrip("\r\n")


def prompt_for_cookie_source(output_dir: str) -> tuple[Optional[str], Optional[str], str]:
    print("MANUAL AUTH: Paste cookies JSON now OR enter a file path.")
    print("To paste: paste JSON, then type a single line: END and press Enter.")
    print("To use a file: type PATH:<full_path> and press Enter.")
    print("To skip: press Enter on an empty line.")
    first_line = _read_prompt_line().strip()
    if not first_line:
        return None, None, "user_skipped"

    cookie_path: Optional[str] = None
    reason = "pasted"

    if first_line.startswith("PATH:"):
        path = first_line[len("PATH:") :].strip()
        if path and os.path.exists(path):
            cookie_path = path
            reason = "path_provided"
        else:
            return None, None, "path_missing"
    else:
        os.makedirs(output_dir, exist_ok=True)
        cookie_lines = [first_line]
        while True:
            next_line = _read_prompt_line()
            if next_line == "END":
                break
            cookie_lines.append(next_line)
        cookie_payload = "\n".join(cookie_lines).strip()
        cookie_path = os.path.join(output_dir, "manual_cookies.json")
        with open(cookie_path, "w", encoding="utf-8") as handle:
            handle.write(cookie_payload)

    os.makedirs(output_dir, exist_ok=True)
    storage_path: Optional[str] = None
    print("Optional: paste localStorage/sessionStorage JSON now (or press Enter to skip). End with END.")
    storage_first = _read_prompt_line().strip()
    if storage_first:
        storage_lines = [storage_first]
        while True:
            next_line = _read_prompt_line()
            if next_line == "END":
                break
            storage_lines.append(next_line)
        storage_payload = "\n".join(storage_lines).strip()
        storage_path = os.path.join(output_dir, "manual_storage.json")
        with open(storage_path, "w", encoding="utf-8") as handle:
            handle.write(storage_payload)

    return cookie_path, storage_path, reason


def _prompt_enabled() -> bool:
    return os.environ.get("WEBSCRAPER_AUTH_PAUSE_ON_FAIL", "1") != "0"


def _allow_multiple_prompts() -> bool:
    return os.environ.get("SCRAPER_MANUAL_PROMPT_MULTI", "0") == "1"


def _wait_mode() -> str:
    mode = (os.environ.get("WEBSCRAPER_AUTH_WAIT_MODE") or "auto").strip().lower()
    return mode if mode in {"auto", "enter"} else "auto"


def _wait_timeout_sec() -> int:
    raw = os.environ.get("WEBSCRAPER_AUTH_WAIT_TIMEOUT_SEC", "180")
    try:
        value = int(raw)
    except ValueError:
        value = 180
    return max(1, value)


def _diagnostic_dump(driver, ctx: AuthContext) -> None:
    output_dir = Path(_manual_output_dir(ctx.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    screenshot_path = output_dir / f"auth_timeout_{timestamp}.png"
    html_path = output_dir / f"auth_timeout_{timestamp}.html"
    try:
        driver.save_screenshot(str(screenshot_path))
    except Exception:
        pass
    try:
        html_path.write_text(driver.page_source or "", encoding="utf-8")
    except Exception:
        pass
    print(f"[AUTH] timeout diagnostics saved: screenshot={screenshot_path} html={html_path}", flush=True)


def _wait_for_manual_auth(driver, ctx: AuthContext) -> Tuple[bool, str]:
    mode = _wait_mode()
    timeout_sec = _wait_timeout_sec()

    if mode == "enter":
        print("Login in the opened browser, then press Enter in terminal to continue", flush=True)
        _ = sys.stdin.readline()
        return is_authenticated(driver, ctx)

    print(f"[AUTH] waiting for MFA/login completion (mode=auto timeout={timeout_sec}s)", flush=True)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ok, reason = is_authenticated(driver, ctx)
        if ok:
            return True, reason
        time.sleep(1)

    _diagnostic_dump(driver, ctx)
    print(
        "[AUTH] Timeout waiting for authenticated selector/state. "
        "Browser remains open. Complete MFA and press Enter to re-check (Ctrl+C to abort).",
        flush=True,
    )
    while True:
        _ = sys.stdin.readline()
        ok, reason = is_authenticated(driver, ctx)
        if ok:
            return True, reason
        print("[AUTH] Still not authenticated. Complete MFA then press Enter to re-check.", flush=True)


def _maybe_prompt_for_cookie(ctx: AuthContext) -> Optional[str]:
    global _MANUAL_PROMPTED
    if not _prompt_enabled():
        return None
    if _MANUAL_PROMPTED and not _allow_multiple_prompts():
        return None
    _MANUAL_PROMPTED = True
    output_dir = _manual_output_dir(ctx.output_dir)
    cookie_path, _, _ = prompt_for_cookie_source(output_dir)
    return cookie_path


def _attempt_manual_with_cookie(ctx: AuthContext, cookie_path: str) -> Tuple[bool, Optional[webdriver.Edge], str, bool]:
    print(f"[AUTH] TRY MANUAL cookie={cookie_path}")
    ctx_for_run = replace(ctx, profile_dirs=[], edge_temp_profile=True)
    try:
        driver, _, _, _ = create_edge_driver_for_auth(ctx_for_run)
    except Exception as exc:
        return False, None, f"driver_start_failed:{type(exc).__name__}", False

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
        return False, None, "cookie_file_empty_or_unreadable", False

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
        return False, None, "cookie_injection_failed", False

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
        return True, driver, reason, True

    try:
        driver.quit()
    except Exception:
        pass
    return False, None, reason, True


def _sanitize_cookie(cookie: dict) -> dict:
    allowed = {"name", "value", "domain", "path", "secure", "httpOnly", "expiry"}
    return {k: v for k, v in cookie.items() if k in allowed and v is not None}


def try_cookies(ctx: AuthContext) -> Tuple[bool, Optional[webdriver.Edge], str]:
    cookie_path = _first_cookie_file(ctx.cookie_files)
    if not cookie_path:
        return False, None, "no_cookie_provided"

    ok, driver, reason, _ = _attempt_manual_with_cookie(ctx, cookie_path)
    if ok:
        return True, driver, reason
    return False, None, reason


def _save_driver_cookies(driver: webdriver.Edge, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cookies = driver.get_cookies() or []
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cookies, handle, indent=2)


def try_manual(ctx: AuthContext) -> Tuple[bool, Optional[webdriver.Edge], str]:
    login_url = ctx.auth_check_url or ctx.base_url
    try:
        driver, _, _, _ = create_edge_driver_for_auth(replace(ctx, headless=False))
    except Exception as exc:
        return False, None, f"driver_start_failed:{type(exc).__name__}"

    try:
        driver.get(login_url)
    except Exception:
        pass

    ok, reason = _wait_for_manual_auth(driver, ctx)
    if ok:
        cookie_target = (ctx.cookie_files[0] if ctx.cookie_files else "").strip()
        if cookie_target:
            try:
                _save_driver_cookies(driver, cookie_target)
                print(f"[AUTH] cookies exported to {cookie_target}")
            except Exception as exc:
                print(f"[AUTH] cookie export failed: {exc}")
        return True, driver, reason

    try:
        driver.quit()
    except Exception:
        pass
    return False, None, reason
