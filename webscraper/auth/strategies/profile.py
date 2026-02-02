from __future__ import annotations

import os
from typing import List, Optional

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


def _build_edge_driver(ctx: AuthContext, profile_dir: Optional[str]) -> webdriver.Edge:
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


def _candidate_profiles(ctx: AuthContext) -> List[str]:
    candidates = []
    if ctx.profile_dir:
        candidates.append(ctx.profile_dir)
    candidates.extend([p for p in ctx.profile_fallback_dirs if p])
    return candidates


def attempt_profile(ctx: AuthContext) -> StrategyOutcome:
    candidates = _candidate_profiles(ctx)
    if not candidates:
        return StrategyOutcome(ok=False, reason="no_profile_dirs_configured", driver=None)

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
            return StrategyOutcome(ok=True, reason=reason, driver=driver)

        try:
            driver.quit()
        except Exception:
            pass
        last_reason = reason

    return StrategyOutcome(ok=False, reason=last_reason, driver=None)
