from __future__ import annotations

import logging
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

LOGGER = logging.getLogger(__name__)


def _default_chrome_user_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return str(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    return str(Path.home() / ".config" / "google-chrome")


def _webdriver_manager_allowed() -> bool:
    repo_root = Path(__file__).resolve().parents[3]
    requirements_path = repo_root / "requirements.txt"
    if not requirements_path.exists():
        return False
    content = requirements_path.read_text(encoding="utf-8", errors="ignore").lower()
    return "webdriver-manager" in content or "webdriver_manager" in content


def _build_options(headless: bool) -> Options:
    user_data_dir = os.environ.get("CHROME_USER_DATA_DIR", _default_chrome_user_data_dir())
    profile_dir = os.environ.get("CHROME_PROFILE_DIR", "Default")

    options = Options()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    if headless:
        options.add_argument("--headless=new")
    return options


def get_driver_reusing_profile(headless: bool = False) -> webdriver.Chrome:
    """Launch Chrome using an existing profile for cookie/session reuse."""
    options = _build_options(headless=headless)

    if _webdriver_manager_allowed():
        from webdriver_manager.chrome import ChromeDriverManager  # pragma: no cover - optional dependency

        LOGGER.info("Starting Selenium Chrome via webdriver-manager (profile reuse).")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "").strip()
    if not chromedriver_path:
        raise RuntimeError(
            "CHROMEDRIVER_PATH is required because webdriver-manager is not listed in requirements.txt"
        )

    LOGGER.info("Starting Selenium Chrome via CHROMEDRIVER_PATH (profile reuse).")
    service = Service(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=options)
