from __future__ import annotations

import json
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
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")


def _repair_chrome_profile(profile_dir: Path, profile_name: str = "Default") -> None:
    """Remove corrupt or unreadable Chrome profile JSON files that cause startup crashes."""
    candidates = [
        profile_dir / "Local State",
        profile_dir / profile_name / "Preferences",
        profile_dir / profile_name / "Secure Preferences",
    ]
    for pref_path in candidates:
        if not pref_path.exists():
            continue
        try:
            data = pref_path.read_text(encoding="utf-8")
            json.loads(data)
        except (PermissionError, json.JSONDecodeError, UnicodeDecodeError):
            backup = pref_path.with_name(pref_path.name + ".bak")
            try:
                pref_path.rename(backup)
                print(f"[launcher] Moved corrupt {pref_path.name} to {backup.name} — Chrome will recreate it")
            except Exception as exc:
                print(f"[launcher] Could not remove corrupt {pref_path.name}: {exc}")


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
        _repair_chrome_profile(profile_dir, profile_name)
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
