from __future__ import annotations

from pathlib import Path
from typing import Literal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions


def get_driver(browser: Literal["edge", "chrome"], headless: bool, profile_dir: Path):
    profile_dir.mkdir(parents=True, exist_ok=True)
    if browser == "chrome":
        options = ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--profile-directory=default")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        if headless:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    options = EdgeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--profile-directory=default")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Edge(options=options)
