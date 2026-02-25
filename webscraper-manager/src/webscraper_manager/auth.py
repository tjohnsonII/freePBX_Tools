from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from .config import ManagerConfig, ensure_runtime_dirs


@dataclass
class AuthResult:
    browser: str
    success: bool
    message: str
    cookie_file: Path | None


def _verify_logged_in(driver: webdriver.Remote) -> bool:
    cookies = driver.get_cookies()
    if cookies:
        return True
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='logout'],button[id*='logout']")
    return len(anchors) > 0


def authenticate(
    config: ManagerConfig,
    browser: str,
    login_url: str,
    timeout: int = 180,
    headless: bool = False,
) -> AuthResult:
    paths = ensure_runtime_dirs(config)
    auth_dir = paths["auth"]

    if browser == "chrome":
        opts = ChromeOptions()
        profile = paths["profiles_chrome"]
        opts.add_argument(f"--user-data-dir={profile}")
        if config.chrome_binary:
            opts.binary_location = config.chrome_binary
        if headless:
            opts.add_argument("--headless=new")
        service = ChromeService(executable_path=config.chromedriver) if config.chromedriver else ChromeService()
        driver = webdriver.Chrome(service=service, options=opts)
    else:
        opts = EdgeOptions()
        profile = paths["profiles_edge"]
        opts.add_argument(f"--user-data-dir={profile}")
        if config.edge_binary:
            opts.binary_location = config.edge_binary
        if headless:
            opts.add_argument("--headless=new")
        service = EdgeService(executable_path=config.edgedriver) if config.edgedriver else EdgeService()
        driver = webdriver.Edge(service=service, options=opts)

    driver.get(login_url)
    deadline = time.time() + timeout
    success = False
    while time.time() < deadline:
        if _verify_logged_in(driver):
            success = True
            break
        time.sleep(2)

    cookie_file = auth_dir / f"{browser}_cookies.json"
    if success:
        cookie_file.write_text(json.dumps(driver.get_cookies(), indent=2), encoding="utf-8")
        message = f"Authenticated in {browser}. Cookies saved to {cookie_file}"
    else:
        message = f"Login was not verified in {timeout}s for {browser}"
        cookie_file = None

    driver.quit()
    return AuthResult(browser=browser, success=success, message=message, cookie_file=cookie_file)
