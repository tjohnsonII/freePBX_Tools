from __future__ import annotations

import os
from typing import List

from .types import AuthAttempt, AuthContext, AuthMode, AuthResult
from .strategies import manual, profile, programmatic


def _existing_paths(paths: List[str]) -> List[str]:
    return [p for p in paths if p and os.path.exists(p)]


def _build_need_user_input(ctx: AuthContext) -> dict:
    fields: List[str] = []
    profile_candidates = [ctx.profile_dir] + ctx.profile_fallback_dirs
    if not _existing_paths([p for p in profile_candidates if p]):
        fields.append("profile_dir")
    if not (ctx.username and ctx.password):
        fields.append("username/password")
    if not _existing_paths(ctx.cookie_files):
        fields.append("cookie_files")

    message_lines = [
        "Authentication failed for all strategies.",
        "Next steps:",
    ]
    if "profile_dir" in fields:
        message_lines.append("- Provide a valid browser profile directory (Edge preferred).")
    if "username/password" in fields:
        message_lines.append("- Provide programmatic credentials via env vars (SCRAPER_USERNAME/SCRAPER_PASSWORD).")
    if "cookie_files" in fields:
        message_lines.append("- Provide cookie files (cookies.json or cookies_netscape_format.txt).")
    if not fields:
        message_lines.append("- Review login heuristics or update selectors for this site.")

    return {
        "fields": fields,
        "message": "\n".join(message_lines),
    }


def authenticate(ctx: AuthContext) -> AuthResult:
    attempts: List[AuthAttempt] = []

    for mode, handler in (
        (AuthMode.PROFILE, profile.attempt_profile),
        (AuthMode.PROGRAMMATIC, programmatic.attempt_programmatic),
        (AuthMode.MANUAL, manual.attempt_manual),
    ):
        outcome = handler(ctx)
        attempts.append(AuthAttempt(mode=mode, ok=outcome.ok, reason=outcome.reason))
        if outcome.ok and outcome.driver:
            return AuthResult(
                mode=mode,
                ok=True,
                reason=outcome.reason,
                driver=outcome.driver,
                need_user_input=None,
                attempts=attempts,
            )

    reasons = "; ".join(attempt.reason for attempt in attempts if attempt.reason)
    return AuthResult(
        mode=AuthMode.FAIL,
        ok=False,
        reason=reasons or "authentication_failed",
        driver=None,
        need_user_input=_build_need_user_input(ctx),
        attempts=attempts,
    )
