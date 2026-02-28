from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserSelection:
    browser: str
    binary_path: str | None
    profile_dir: Path
    profile_name: str


def _existing(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    return str(candidate) if candidate.exists() else None


def _detect_chrome() -> str | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for item in candidates:
        resolved = _existing(item)
        if resolved:
            return resolved
    return None


def _detect_edge() -> str | None:
    candidates = [
        os.getenv("EDGE_PATH") or os.getenv("EDGE_BINARY_PATH"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for item in candidates:
        resolved = _existing(item)
        if resolved:
            return resolved
    return None


def resolve_browser_selection() -> BrowserSelection:
    browser = (os.getenv("WEBSCRAPER_BROWSER") or "edge").strip().lower()
    if browser not in {"chrome", "edge"}:
        browser = "chrome"

    default_profile_dir = "webscraper/var/edge-profile" if browser == "edge" else "webscraper/var/chrome-profile"
    profile_dir_raw = os.getenv("WEBSCRAPER_PROFILE_DIR", default_profile_dir)
    profile_name = (os.getenv("WEBSCRAPER_PROFILE_NAME") or "Default").strip() or "Default"
    profile_dir = Path(profile_dir_raw).expanduser()
    if not profile_dir.is_absolute():
        profile_dir = Path.cwd() / profile_dir
    profile_dir.mkdir(parents=True, exist_ok=True)

    binary_path = _detect_chrome() if browser == "chrome" else _detect_edge()
    return BrowserSelection(browser=browser, binary_path=binary_path, profile_dir=profile_dir, profile_name=profile_name)
