from __future__ import annotations

import os
from typing import Optional, Tuple, TYPE_CHECKING

from .types import AuthContext

if TYPE_CHECKING:
    from selenium import webdriver


def create_edge_driver_for_auth(ctx: AuthContext) -> Tuple["webdriver.Edge", bool, bool, Optional[str]]:
    from webscraper.ultimate_scraper import create_edge_driver

    profile_dir = ctx.profile_dirs[0] if ctx.profile_dirs else None
    output_dir = ctx.output_dir or os.getcwd()
    return create_edge_driver(
        output_dir=output_dir,
        headless=ctx.headless,
        attach=ctx.attach,
        auto_attach=ctx.auto_attach,
        attach_host=ctx.attach_host,
        attach_timeout=ctx.attach_timeout,
        fallback_profile_dir=ctx.fallback_profile_dir,
        profile_dir=profile_dir,
        profile_name=ctx.profile_name,
        auth_dump=False,
        auth_pause=False,
        auth_timeout=ctx.timeout_sec,
        auth_url=ctx.auth_check_url or ctx.base_url,
        edge_temp_profile=ctx.edge_temp_profile,
        edge_kill_before=ctx.edge_kill_before,
        show_browser=ctx.show_browser,
    )
