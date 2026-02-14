from __future__ import annotations

import os
from typing import Optional, Tuple, TYPE_CHECKING

from .types import AuthContext
from .error_logging import log_exception

if TYPE_CHECKING:
    from selenium import webdriver


def create_edge_driver_for_auth(ctx: AuthContext) -> Tuple["webdriver.Edge", bool, bool, Optional[str]]:
    from webscraper.browser.edge_driver import create_edge_driver

    profile_dir = ctx.profile_dirs[0] if ctx.profile_dirs else None
    output_dir = ctx.output_dir or os.getcwd()
    init_mode = "attach" if (ctx.attach or ctx.auto_attach) else "launch"
    print(
        "[AUTH][DRIVER] "
        f"mode={init_mode} "
        f"edge_binary={ctx.edge_binary or '<auto>'} "
        f"user_data_dir={profile_dir or '<none>'} "
        f"profile_directory={ctx.profile_name or 'Default'}"
    )
    try:
        return create_edge_driver(
            output_dir=output_dir,
            headless=ctx.headless,
            headless_requested=False,
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
    except Exception as exc:
        log_exception("driver_start_failed", exc, output_dir, "driver_start_failed.txt")
        raise
