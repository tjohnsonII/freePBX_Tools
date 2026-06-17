from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions


def _add_root_flags(options) -> None:
    """Add flags required for Chromium on headless Linux servers (always needed, not just root)."""
    if os.name != "nt":
        # ── sandbox / root ───────────────────────────────────────────────────
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")

        # ── rendering ────────────────────────────────────────────────────────
        options.add_argument("--disable-gpu")
        # NOTE: do NOT set --disable-software-rasterizer — on Xvfb (no real GPU)
        # this removes the only rendering fallback and causes renderer crashes on
        # complex pages with many tickets. Chrome needs software rasterization here.
        # NOTE: do NOT set --disable-dev-shm-usage here.
        # /dev/shm on this server is 3.9 GB (nearly empty). That flag is only
        # needed in Docker where /dev/shm is 64 MB.  Keeping it causes Chrome
        # to fall back to /tmp for all renderer IPC, which is slower and causes
        # crashes under heavy scrape load.

        # ── display ──────────────────────────────────────────────────────────
        options.add_argument("--window-size=1280,900")
        options.add_argument("--force-device-scale-factor=1")

        # ── memory / process isolation ───────────────────────────────────────
        # NOTE: do NOT set --renderer-process-limit here — SSO login flows spawn
        # extra tabs/windows and a limit of 2 causes Chrome to crash mid-redirect.
        # NOTE: do NOT set --js-flags=--max-old-space-size here — large accounts
        # (e.g. JD4) have hundreds of tickets; a 512MB JS heap cap causes Chrome
        # to OOM-crash on their ticket list pages. Let Chrome manage its own heap.
        # NOTE: do NOT disable cache — large DOM pages (many tickets) rely on
        # Chrome's internal caching to avoid re-fetching fragments. Disabling it
        # causes renderer OOM on large accounts.

        # ── stability ────────────────────────────────────────────────────────
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--disable-prompt-on-repost")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-ipc-flooding-protection")
        # Required for SSO flows that open a popup window for authentication
        options.add_argument("--disable-popup-blocking")

        # ── noise reduction ──────────────────────────────────────────────────
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-component-update")
        options.add_argument("--safebrowsing-disable-auto-update")
        options.add_argument("--disable-client-side-phishing-detection")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--mute-audio")
        options.add_argument("--hide-scrollbars")


def _repair_chrome_profile(profile_dir: Path, profile_name: str = "Default") -> None:
    """Remove lock files and corrupt JSON files that cause Chrome startup crashes."""
    # Remove lock files left by a crashed/killed Chrome — if present, Chrome exits immediately
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        lock = profile_dir / lock_name
        if lock.exists() or lock.is_symlink():
            try:
                lock.unlink()
                print(f"[launcher] Removed stale Chrome lock: {lock.name}")
            except Exception as exc:
                print(f"[launcher] Could not remove {lock.name}: {exc}")

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
        else:
            options.add_argument("--start-maximized")
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
    else:
        options.add_argument("--start-maximized")
    _add_root_flags(options)
    return webdriver.Edge(options=options)
