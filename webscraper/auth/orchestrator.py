from __future__ import annotations

import os
from typing import List, Optional

from .types import AuthAttempt, AuthContext, AuthMode, AuthResult
from .strategies import manual, profile, programmatic


def _existing_paths(paths: List[str]) -> List[str]:
    return [p for p in paths if p and os.path.exists(p)]


def _build_need_user_input(ctx: AuthContext) -> dict:
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
        message_lines.append("- Provide cookie files (cookies.json or cookies_netscape_format.txt).")
    if not fields:
        message_lines.append("- Review login heuristics or update selectors for this site.")

    return {
        "fields": fields,
        "message": "\n".join(message_lines),
    }


def authenticate(ctx: AuthContext, modes: Optional[List[AuthMode]] = None) -> AuthResult:
    attempts: List[AuthAttempt] = []
    modes = modes or [AuthMode.PROFILE, AuthMode.PROGRAMMATIC, AuthMode.MANUAL]

    for mode in modes:
        if mode == AuthMode.PROFILE:
            ok, driver, reason = profile.try_profile(ctx)
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
        need_user_input=_build_need_user_input(ctx),
    )
