from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from webscraper.paths import var_dir
from webscraper.ticket_api import auth_store


@dataclass(frozen=True)
class AuthPaths:
    auth_dir: Path
    canonical_cookie_file: Path
    storage_state_file: Path
    session_file: Path
    token_cache_file: Path
    imported_cookie_file: Path
    legacy_cookie_file: Path
    selenium_cookie_file: Path
    chrome_profiles_dir: Path
    forced_profiles_dir: Path


def get_auth_paths() -> AuthPaths:
    base = var_dir()
    auth_dir = base / "auth"
    return AuthPaths(
        auth_dir=auth_dir,
        canonical_cookie_file=auth_dir / "cookies.json",
        storage_state_file=auth_dir / "storage_state.json",
        session_file=auth_dir / "session.json",
        token_cache_file=auth_dir / "cached_tokens.json",
        imported_cookie_file=auth_dir / "imported_cookies.json",
        legacy_cookie_file=base / "cookies" / "cookies.json",
        selenium_cookie_file=base / "cookies" / "selenium_cookies.json",
        chrome_profiles_dir=base / "chrome_profiles",
        forced_profiles_dir=auth_dir / "forced_profiles",
    )


class AuthManager:
    def __init__(self, db_path_getter, browser_path_getter, log_func):
        self._db_path_getter = db_path_getter
        self._browser_path_getter = browser_path_getter
        self._log = log_func
        self._lock = Lock()
        self._active_driver: webdriver.Chrome | None = None

    def _register_driver(self, driver: webdriver.Chrome | None) -> None:
        with self._lock:
            self._active_driver = driver

    def _close_active_driver(self) -> str | None:
        with self._lock:
            driver = self._active_driver
            self._active_driver = None
        if not driver:
            return None
        try:
            driver.quit()
            return "active_selenium_driver"
        except Exception as exc:
            return f"active_selenium_driver:{type(exc).__name__}"

    def clear_auth_state(self) -> dict[str, Any]:
        paths = get_auth_paths()
        removed: list[str] = []
        warnings: list[str] = []

        closed = self._close_active_driver()
        if closed:
            removed.append(closed)

        auth_store.clear_cookies(self._db_path_getter())
        removed.append("auth_cookies_db")

        to_remove = [
            paths.canonical_cookie_file,
            paths.storage_state_file,
            paths.session_file,
            paths.token_cache_file,
            paths.imported_cookie_file,
            paths.legacy_cookie_file,
            paths.selenium_cookie_file,
        ]

        for file_path in to_remove:
            try:
                if file_path.exists():
                    file_path.unlink()
                    removed.append(str(file_path))
            except Exception as exc:
                warnings.append(f"failed_remove_file:{file_path}:{type(exc).__name__}")

        for dir_path in [paths.forced_profiles_dir, paths.chrome_profiles_dir / "ticketing"]:
            try:
                if dir_path.exists():
                    shutil.rmtree(dir_path, ignore_errors=False)
                    removed.append(str(dir_path))
            except Exception as exc:
                warnings.append(f"failed_remove_dir:{dir_path}:{type(exc).__name__}")

        return {"ok": True, "removed": removed, "warnings": warnings}

    def load_cookies(self) -> list[dict[str, Any]]:
        return auth_store.load_cookies(self._db_path_getter())

    def save_cookies(self, cookies: list[dict[str, Any]], source: str) -> dict[str, Any]:
        paths = get_auth_paths()
        paths.auth_dir.mkdir(parents=True, exist_ok=True)
        result = auth_store.replace_cookies(self._db_path_getter(), cookies, source=source)
        with paths.canonical_cookie_file.open("w", encoding="utf-8") as handle:
            json.dump(cookies, handle, indent=2)
        return {"saved": int(result.get("accepted", 0)), "file": str(paths.canonical_cookie_file)}

    def _is_logged_in(self, current_url: str, cookies: list[dict[str, Any]]) -> bool:
        lowered = (current_url or "").lower()
        if any(marker in lowered for marker in ("login", "signin", "sign-in", "sso")):
            return False
        valid_domains = {"secure.123.net", ".secure.123.net", "123.net", ".123.net"}
        for cookie in cookies:
            domain = str(cookie.get("domain") or "").strip().lower()
            if domain in valid_domains or domain.endswith(".secure.123.net"):
                return True
        return False

    def launch_login(self, *, force_fresh: bool, target_url: str, timeout_seconds: int = 300) -> dict[str, Any]:
        paths = get_auth_paths()
        profile_dir: Path
        if force_fresh:
            paths.forced_profiles_dir.mkdir(parents=True, exist_ok=True)
            profile_dir = Path(tempfile.mkdtemp(prefix="ticket-auth-", dir=str(paths.forced_profiles_dir)))
        else:
            profile_dir = paths.chrome_profiles_dir / "ticketing"
            profile_dir.mkdir(parents=True, exist_ok=True)

        options = Options()
        options.binary_location = str(self._browser_path_getter())
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--new-window")

        chromedriver_path = (os.getenv("CHROMEDRIVER_PATH") or "").strip()
        if chromedriver_path:
            driver = webdriver.Chrome(service=Service(executable_path=chromedriver_path), options=options)
        else:
            driver = webdriver.Chrome(options=options)

        self._register_driver(driver)
        cookies_saved = False
        cookie_file = str(paths.canonical_cookie_file)
        warnings: list[str] = []

        self._log(
            f"auth_launch force_fresh={force_fresh} profile_dir={profile_dir} target_url={target_url} cookie_file={cookie_file}"
        )

        try:
            driver.get(target_url)
            if force_fresh:
                deadline = time.time() + max(10, int(timeout_seconds))
                while time.time() < deadline:
                    time.sleep(2)
                    current_cookies = driver.get_cookies() or []
                    if self._is_logged_in(driver.current_url, current_cookies):
                        save_result = self.save_cookies(current_cookies, source="selenium_forced_login")
                        cookies_saved = save_result["saved"] > 0
                        break
                if not cookies_saved:
                    warnings.append("login_not_completed_before_timeout")
            return {
                "ok": True,
                "forced": force_fresh,
                "cookies_saved": cookies_saved,
                "profile_dir": str(profile_dir),
                "cookie_file": cookie_file,
                "warnings": warnings,
            }
        finally:
            try:
                driver.quit()
            finally:
                self._register_driver(None)


def default_target_url(explicit_url: str | None = None) -> str:
    if explicit_url and explicit_url.strip():
        return explicit_url.strip()
    configured = (os.getenv("TICKETING_LOGIN_URL") or "").strip()
    if configured:
        return configured
    return "https://secure.123.net/cgi-bin/web_interface/login.cgi"

