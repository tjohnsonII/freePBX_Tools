from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions


def _add_root_flags(options) -> None:
    """Chromium-based browsers crash when run as root without --no-sandbox."""
    if os.name != "nt" and os.getuid() == 0:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")


def get_driver(
    browser: Literal["edge", "chrome"],
    headless: bool,
    profile_dir: Path,
    *,
    profile_name: str = "Default",
    binary_path: Optional[str] = None,
):
    profile_dir.mkdir(parents=True, exist_ok=True)
    if browser == "chrome":
        options = ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument(f"--profile-directory={profile_name}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        if binary_path:
            options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        _add_root_flags(options)
        return webdriver.Chrome(options=options)

    options = EdgeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--profile-directory={profile_name}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    if binary_path:
        options.binary_location = binary_path
    if headless:
        options.add_argument("--headless=new")
    _add_root_flags(options)
    return webdriver.Edge(options=options)
