from __future__ import annotations

import os
from dataclasses import replace
from typing import Iterable, List, Optional

from .types import AuthAttempt, AuthContext, AuthMode, AuthResult
from .strategies import manual, profile, programmatic


def _existing_paths(paths: List[str]) -> List[str]:
    return [p for p in paths if p and os.path.exists(p)]


def _build_need_user_input(ctx: AuthContext, modes: Iterable[AuthMode]) -> dict:
    fields: List[str] = []
    if not _existing_paths(ctx.profile_dirs):
        fields.append("profile_dir")
    if not (ctx.username and ctx.password):
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
        os.path.join(webscraper_dir, "output", "kb-run", "selenium_cookies.json"),
        os.path.join(webscraper_dir, "cookies.json"),
        os.path.join(webscraper_dir, "live_cookies.json"),
        os.path.join(webscraper_dir, "cookies_netscape_format.txt"),
    ]


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
    modes = modes or [AuthMode.PROFILE, AuthMode.PROGRAMMATIC, AuthMode.MANUAL]
    max_attempts_per_strategy = 1
    attempted_by_mode: dict[AuthMode, int] = {}
    ctx = replace(ctx, cookie_files=_resolve_cookie_files(ctx))
    max_profiles = _max_profile_dirs()

    for mode in modes:
        if attempted_by_mode.get(mode, 0) >= max_attempts_per_strategy:
            continue
        attempted_by_mode[mode] = attempted_by_mode.get(mode, 0) + 1
        if mode == AuthMode.PROFILE:
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
