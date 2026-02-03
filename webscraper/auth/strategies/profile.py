from __future__ import annotations

import os
from dataclasses import replace
from typing import List, Optional, Tuple

from selenium import webdriver

from ..healthcheck import is_authenticated
from ..types import AuthContext
from ..driver_factory import create_edge_driver_for_auth


def _candidate_profiles(ctx: AuthContext) -> List[str]:
    return [p for p in ctx.profile_dirs if p]


def try_profile(ctx: AuthContext) -> Tuple[bool, Optional[webdriver.Edge], str]:
    candidates = _candidate_profiles(ctx)
    if not candidates:
        return False, None, "no_profile_dirs_configured"

    last_reason = "no_profile_dirs_found"
    for profile_dir in candidates:
        if not profile_dir or not os.path.exists(profile_dir):
            last_reason = f"profile_missing:{profile_dir}"
            continue
        print(f"[AUTH] TRY PROFILE dir={profile_dir}")
        ctx_for_profile = replace(ctx, profile_dirs=[profile_dir], edge_temp_profile=False)
        try:
            driver, _, _, _ = create_edge_driver_for_auth(ctx_for_profile)
        except Exception as exc:
            last_reason = f"driver_start_failed:{type(exc).__name__}"
            continue

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
        last_reason = reason

    return False, None, last_reason
