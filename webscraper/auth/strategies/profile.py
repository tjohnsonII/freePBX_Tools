from __future__ import annotations

import os
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from ..healthcheck import is_authenticated
from ..types import AuthContext


def _build_edge_driver(ctx: AuthContext, profile_dir: Optional[str]) -> webdriver.Edge:
    edge_options = EdgeOptions()
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_argument("--ignore-certificate-errors")
    edge_options.add_argument("--allow-insecure-localhost")

    if ctx.edge_binary:
        edge_options.binary_location = ctx.edge_binary
    if profile_dir:
        edge_options.add_argument(f"--user-data-dir={profile_dir}")
        edge_options.add_argument(f"--profile-directory={ctx.profile_name}")
    if ctx.headless:
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--no-sandbox")

    if ctx.edgedriver_path and os.path.exists(ctx.edgedriver_path):
        service = EdgeService(ctx.edgedriver_path)
    else:
        service = EdgeService()
    return webdriver.Edge(service=service, options=edge_options)


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
        try:
            driver = _build_edge_driver(ctx, profile_dir)
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
