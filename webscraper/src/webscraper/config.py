from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return repo_root() / path


@dataclass(frozen=True)
class WebscraperConfig:
    profile_dir: Path
    chrome_path: str | None
    chromedriver_path: str | None
    auth_timeout: int


def load_config() -> WebscraperConfig:
    profile_dir_raw = os.getenv("WEBSCRAPER_PROFILE_DIR", "webscraper/var/chrome-profile")
    auth_timeout_raw = os.getenv("WEBSCRAPER_AUTH_TIMEOUT", "300")

    try:
        auth_timeout = max(1, int(auth_timeout_raw))
    except ValueError:
        auth_timeout = 300

    chrome_path = (os.getenv("CHROME_PATH") or "").strip() or None
    chromedriver_path = (os.getenv("CHROMEDRIVER_PATH") or "").strip() or None

    profile_dir = resolve_repo_path(profile_dir_raw)
    profile_dir.mkdir(parents=True, exist_ok=True)

    return WebscraperConfig(
        profile_dir=profile_dir,
        chrome_path=chrome_path,
        chromedriver_path=chromedriver_path,
        auth_timeout=auth_timeout,
    )
