from __future__ import annotations

import json
import os
from dataclasses import replace
from typing import Iterable, List, Optional

from .chrome_profile import get_driver_reusing_profile
from .probe import TARGET_URL, probe_auth
from .session import build_authenticated_session, selenium_driver_to_requests_session, summarize_driver_cookies

from .types import AuthAttempt, AuthContext, AuthMode, AuthResult
from .strategies import manual, profile, programmatic


def _normalize_driver_cookie_for_store(cookie: dict, default_domain: str = "secure.123.net") -> dict:
    return {
        "name": str(cookie.get("name") or "").strip(),
        "value": str(cookie.get("value") or ""),
        "domain": str(cookie.get("domain") or "").strip() or default_domain,
        "path": str(cookie.get("path") or "/") or "/",
        "secure": bool(cookie.get("secure")),
        "httpOnly": bool(cookie.get("httpOnly")),
        "sameSite": cookie.get("sameSite"),
        "expires": cookie.get("expiry", cookie.get("expires")),
    }


def _persist_selenium_cookies(cookies: list[dict]) -> None:
    try:
        from webscraper.lib.db_path import get_tickets_db_path
        from webscraper.ticket_api import auth_store

        normalized = [_normalize_driver_cookie_for_store(cookie) for cookie in cookies if isinstance(cookie, dict)]
        auth_store.replace_cookies(get_tickets_db_path(), normalized, source="selenium_profile")
    except Exception:
        # Non-fatal: the requests session in-memory can still be used for this run.
        pass


def authenticate_and_fetch(url: str = TARGET_URL, mode: str = "auto") -> dict:
    """Fetch a page using requests, selenium, or auto fallback.

    Returns a dict containing mode/probe/fetch diagnostics.
    """
    selected_mode = (mode or "auto").strip().lower()
    if selected_mode not in {"auto", "requests", "selenium"}:
        raise ValueError("mode must be one of: auto, requests, selenium")

    request_error: str | None = None
    selenium_error: str | None = None

    if selected_mode in {"auto", "requests"}:
        try:
            session = build_authenticated_session()
            req_probe = probe_auth(session, url=url)
            if req_probe.get("ok"):
                response = session.get(url, timeout=30, allow_redirects=True)
                return {
                    "mode": "requests",
                    "probe": req_probe,
                    "status_code": int(response.status_code),
                    "url": response.url,
                    "content": response.text,
                }
            request_error = req_probe.get("notes", "requests probe did not pass")
            if selected_mode == "requests":
                raise RuntimeError(f"requests auth probe failed: {request_error}")
        except Exception as exc:
            request_error = str(exc)
            if selected_mode == "requests":
                raise

    if selected_mode in {"auto", "selenium"}:
        driver = None
        try:
            driver = get_driver_reusing_profile(headless=False)
            sel_probe = probe_auth(driver, url=url)
            if not sel_probe.get("ok"):
                raise RuntimeError(f"selenium auth probe failed: {sel_probe.get('notes', 'unknown reason')}")

            if selected_mode == "auto":
                seeded_session = selenium_driver_to_requests_session(driver, base_url=url)
                seeded_probe = probe_auth(seeded_session, url=url)
                if not seeded_probe.get("ok"):
                    diagnostics = summarize_driver_cookies(driver)
                    raise RuntimeError(
                        "selenium authentication succeeded but requests cookie seeding failed: "
                        f"{seeded_probe.get('notes', 'unknown reason')} cookies={diagnostics}"
                    )
                _persist_selenium_cookies(driver.get_cookies() or [])
                response = seeded_session.get(url, timeout=30, allow_redirects=True)
                return {
                    "mode": "requests_seeded_from_selenium",
                    "probe": seeded_probe,
                    "selenium_probe": sel_probe,
                    "status_code": int(response.status_code),
                    "url": response.url,
                    "content": response.text,
                }

            driver.get(url)
            return {
                "mode": "selenium",
                "probe": sel_probe,
                "status_code": 200,
                "url": driver.current_url,
                "content": driver.page_source,
            }
        except Exception as exc:
            selenium_error = str(exc)
            if selected_mode == "selenium":
                raise
        finally:
            if driver is not None:
                driver.quit()

    raise RuntimeError(
        "Authentication failed in auto mode. "
        f"Requests failure: {request_error or 'n/a'}. Selenium failure: {selenium_error or 'n/a'}. "
        "Verify browser has an active login for secure.123.net and CHROMEDRIVER_PATH is configured."
    )


def _existing_paths(paths: List[str]) -> List[str]:
    return [p for p in paths if p and os.path.exists(p)]


def _build_need_user_input(ctx: AuthContext, modes: Iterable[AuthMode]) -> dict:
    fields: List[str] = []
    if not _existing_paths(ctx.profile_dirs):
        fields.append("profile_dir")
    if AuthMode.PROGRAMMATIC in modes and not (ctx.username and ctx.password):
        fields.append("username/password")
    if not _existing_paths(ctx.cookie_files):
        fields.append("cookie_file")

    message_lines = [
        "Authentication failed for all strategies.",
        "Next steps:",
    ]
    if "profile_dir" in fields:
        message_lines.append("- Provide a valid browser profile directory (Edge preferred).")
    if "username/password" in fields:
        message_lines.append("- Provide programmatic credentials via env vars (SCRAPER_USERNAME/SCRAPER_PASSWORD).")
    if "cookie_file" in fields:
        if AuthMode.MANUAL in modes:
            message_lines.append(
                "- No cookie files found. Re-run with SCRAPER_AUTH_MODE=MANUAL and paste cookies when prompted, or pass --cookie-file <path>."
            )
        else:
            message_lines.append("- Provide cookie files (cookies.json or cookies_netscape_format.txt).")
    if not fields:
        message_lines.append("- Review login heuristics or update selectors for this site.")

    return {
        "fields": fields,
        "message": "\n".join(message_lines),
    }


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_path_candidates(path: str, base_dirs: Iterable[str]) -> List[str]:
    if not path:
        return []
    if os.path.isabs(path):
        return [path]
    resolved = []
    resolved.append(os.path.abspath(path))
    for base in base_dirs:
        resolved.append(os.path.abspath(os.path.join(base, path)))
    return resolved


def _default_cookie_candidates(root_dir: str) -> List[str]:
    webscraper_dir = os.path.join(root_dir, "webscraper")
    return [
        os.path.join(webscraper_dir, "var", "auth", "cookies.json"),
        os.path.join(webscraper_dir, "output", "kb-run", "selenium_cookies.json"),
        os.path.join(webscraper_dir, "cookies.json"),
        os.path.join(webscraper_dir, "live_cookies.json"),
        os.path.join(webscraper_dir, "cookies_netscape_format.txt"),
    ]


def _cookie_export_target(ctx: AuthContext) -> str:
    if ctx.cookie_files:
        first = (ctx.cookie_files[0] or "").strip()
        if first:
            return first
    return os.path.join(_repo_root(), "webscraper", "var", "auth", "cookies.json")


def _persist_auth_artifacts(driver, ctx: AuthContext) -> None:
    cookie_path = _cookie_export_target(ctx)
    os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
    with open(cookie_path, "w", encoding="utf-8") as handle:
        json.dump(driver.get_cookies() or [], handle, indent=2)

    storage_path = os.path.join(os.path.dirname(cookie_path), "storage.json")
    storage_payload = driver.execute_script(
        """
        return {
          localStorage: Object.assign({}, window.localStorage || {}),
          sessionStorage: Object.assign({}, window.sessionStorage || {})
        };
        """
    )
    with open(storage_path, "w", encoding="utf-8") as handle:
        json.dump(storage_payload or {}, handle, indent=2)


def _resolve_cookie_files(ctx: AuthContext) -> List[str]:
    root_dir = _repo_root()
    webscraper_dir = os.path.join(root_dir, "webscraper")
    resolved: List[str] = []

    for raw_path in ctx.cookie_files:
        for candidate in _resolve_path_candidates(raw_path, (root_dir, webscraper_dir)):
            if candidate and os.path.exists(candidate) and candidate not in resolved:
                resolved.append(candidate)

    for candidate in _default_cookie_candidates(root_dir):
        if candidate and os.path.exists(candidate) and candidate not in resolved:
            resolved.append(candidate)

    return resolved


def _max_profile_dirs() -> int:
    raw = os.environ.get("SCRAPER_AUTH_MAX_PROFILE_DIRS", "3")
    try:
        value = int(raw)
    except ValueError:
        value = 3
    return max(1, value)


def authenticate(ctx: AuthContext, modes: Optional[List[AuthMode]] = None) -> AuthResult:
    attempts: List[AuthAttempt] = []
    if modes is None:
        requested = (os.getenv("WEBSCRAPER_AUTH_MODE") or "auto").strip().lower()
        if requested == "cookies":
            modes = [AuthMode.COOKIES]
        elif requested == "profile":
            modes = [AuthMode.PROFILE]
        elif requested == "manual":
            modes = [AuthMode.MANUAL]
        else:
            modes = [AuthMode.COOKIES, AuthMode.PROFILE, AuthMode.MANUAL]
    max_attempts_per_strategy = 1
    attempted_by_mode: dict[AuthMode, int] = {}
    ctx = replace(ctx, cookie_files=_resolve_cookie_files(ctx))
    max_profiles = _max_profile_dirs()

    for mode in modes:
        if attempted_by_mode.get(mode, 0) >= max_attempts_per_strategy:
            continue
        attempted_by_mode[mode] = attempted_by_mode.get(mode, 0) + 1
        if mode == AuthMode.COOKIES:
            ok, driver, reason = manual.try_cookies(ctx)
        elif mode == AuthMode.PROFILE:
            profile_ctx = replace(ctx, profile_dirs=ctx.profile_dirs[:max_profiles])
            ok, driver, reason = profile.try_profile(profile_ctx)
        elif mode == AuthMode.PROGRAMMATIC:
            ok, driver, reason = programmatic.try_programmatic(ctx)
        elif mode == AuthMode.MANUAL:
            ok, driver, reason = manual.try_manual(ctx)
        else:
            ok, driver, reason = False, None, "unsupported_mode"
        attempts.append(AuthAttempt(mode=mode, ok=ok, reason=reason))
        if ok and driver:
            try:
                _persist_auth_artifacts(driver, ctx)
                print(f"[AUTH] exported cookies to {_cookie_export_target(ctx)}")
            except Exception as exc:
                print(f"[AUTH] artifact export warning: {exc}")
            return AuthResult(
                ok=True,
                mode=mode,
                reason=reason,
                attempts=attempts,
                driver=driver,
                need_user_input=None,
            )

    reasons = "; ".join(attempt.reason for attempt in attempts if attempt.reason)
    return AuthResult(
        ok=False,
        mode=AuthMode.FAIL,
        reason=reasons or "authentication_failed",
        attempts=attempts,
        driver=None,
        need_user_input=_build_need_user_input(ctx, modes),
    )
