from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from webscraper.auth.chrome_cdp import ChromeCDPError, connect_browser_ws, find_free_port, get_all_cookies, launch_chrome_with_debug

try:  # optional dependency
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - optional import
    AESGCM = None

LOGGER = logging.getLogger(__name__)

DEFAULT_CDP_PORT = 9222
DEFAULT_DOMAINS = ["secure.123.net", "123.net"]


class CookieSeedError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]


@dataclass
class SeedResult:
    mode_used: str
    cookies: list[dict[str, Any]]
    details: dict[str, Any]


def normalize_domains(domains: list[str] | None) -> list[str]:
    selected = [str(domain).strip().lstrip(".").lower() for domain in (domains or DEFAULT_DOMAINS) if str(domain).strip()]
    return selected or DEFAULT_DOMAINS


def resolve_chrome_user_data_dir(profile_dir: str | Path | None) -> Path:
    if profile_dir:
        return Path(profile_dir)
    env_dir = (os.getenv("CHROME_USER_DATA_DIR") or "").strip()
    if env_dir:
        return Path(env_dir)
    local_app_data = (os.getenv("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    return Path.home() / ".config" / "google-chrome"


def resolve_profile_name(profile_name: str | None = None) -> str:
    candidate = (profile_name or os.getenv("CHROME_PROFILE_DIR") or "").strip()
    return candidate or "Default"


def resolve_cookie_db_path(profile_dir: str | Path, profile_name: str) -> Path:
    return Path(profile_dir) / profile_name / "Network" / "Cookies"


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, sqlite3.OperationalError) and "locked" in message:
        return True
    if "sharing violation" in message or "database is locked" in message:
        return True
    return False


def _copy_with_backoff(source: Path, backoff_seconds: tuple[float, ...] = (0.5, 1.0, 2.0)) -> Path:
    last_exc: Exception | None = None
    attempts = len(backoff_seconds) + 1
    for attempt in range(attempts):
        fd, tmp_name = tempfile.mkstemp(prefix="cookie_seed_", suffix=source.suffix or ".sqlite")
        os.close(fd)
        target = Path(tmp_name)
        try:
            shutil.copy2(source, target)
            LOGGER.info("[AUTH][DISK] copied cookie DB source=%s temp=%s", source, target)
            return target
        except Exception as exc:
            target.unlink(missing_ok=True)
            last_exc = exc
            if _is_lock_error(exc):
                LOGGER.warning("[AUTH][DISK] copy failed due to probable lock attempt=%s error=%s", attempt + 1, exc)
                if attempt < len(backoff_seconds):
                    time.sleep(backoff_seconds[attempt])
                continue
            raise CookieSeedError("DISK_COPY_FAILED", f"Failed copying cookie DB: {exc}") from exc
    raise CookieSeedError(
        "DB_LOCKED",
        "Chrome cookie DB appears locked (Chrome may be running).",
        details={"source": str(source), "error": str(last_exc) if last_exc else None},
    )


def _crypt_unprotect_data(data: bytes) -> bytes:
    in_blob = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise CookieSeedError("DECRYPT_FAILED", "CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _load_os_crypt_key(user_data_dir: Path) -> bytes | None:
    state_path = user_data_dir / "Local State"
    if not state_path.exists():
        return None
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    key_b64 = payload.get("os_crypt", {}).get("encrypted_key")
    if not key_b64:
        return None
    encrypted_key = base64.b64decode(key_b64)
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return _crypt_unprotect_data(encrypted_key)


def _decrypt_cookie_value(encrypted_value: bytes, value: str, aes_key: bytes | None) -> str:
    if value:
        return value
    if not encrypted_value:
        return ""
    if encrypted_value.startswith((b"v10", b"v11")):
        if AESGCM is None or not aes_key:
            raise CookieSeedError("DECRYPT_FAILED", "AES-GCM cookie decryption unavailable")
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None).decode("utf-8", errors="replace")
    return _crypt_unprotect_data(encrypted_value).decode("utf-8", errors="replace")


def _domain_match(cookie_domain: str, selected_domains: list[str]) -> bool:
    normalized = str(cookie_domain or "").lstrip(".").lower()
    return any(normalized == domain or normalized.endswith(f".{domain}") for domain in selected_domains)


def _cookie_from_row(row: tuple[Any, ...], aes_key: bytes | None, selected_domains: list[str]) -> dict[str, Any] | None:
    host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite = row
    domain = str(host_key or "")
    if not _domain_match(domain, selected_domains):
        return None
    try:
        decrypted = _decrypt_cookie_value(encrypted_value or b"", str(value or ""), aes_key)
    except CookieSeedError:
        raise
    except Exception as exc:
        raise CookieSeedError("DECRYPT_FAILED", f"Cookie decryption failed for {name}@{domain}: {exc}") from exc

    expires = None
    if expires_utc:
        try:
            chrome_epoch_seconds = (int(expires_utc) / 1_000_000) - 11644473600
            expires = int(chrome_epoch_seconds) if chrome_epoch_seconds > 0 else None
        except Exception:
            expires = None
    return {
        "name": str(name or ""),
        "value": decrypted,
        "domain": domain,
        "path": str(path or "/"),
        "expires": expires,
        "secure": bool(is_secure),
        "httpOnly": bool(is_httponly),
        "sameSite": str(samesite) if samesite is not None else None,
    }


def seed_from_disk(profile_dir: str | Path, domains: list[str], *, profile_name: str | None = None) -> SeedResult:
    selected_domains = normalize_domains(domains)
    user_data_dir = resolve_chrome_user_data_dir(profile_dir)
    chosen_profile = resolve_profile_name(profile_name)
    cookie_db = resolve_cookie_db_path(user_data_dir, chosen_profile)
    if not cookie_db.exists():
        raise CookieSeedError("COOKIE_DB_MISSING", f"Cookie DB not found: {cookie_db}")

    temp_copy = _copy_with_backoff(cookie_db)
    cookies: list[dict[str, Any]] = []
    try:
        aes_key: bytes | None = None
        if sys.platform.startswith("win"):
            try:
                aes_key = _load_os_crypt_key(user_data_dir)
            except Exception as exc:  # pragma: no cover - runtime platform dependency
                LOGGER.warning("[AUTH][DISK] failed loading Local State encryption key error=%s", exc)

        with sqlite3.connect(temp_copy) as conn:
            rows = conn.execute(
                "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite FROM cookies"
            ).fetchall()

        for row in rows:
            cookie = _cookie_from_row(row, aes_key, selected_domains)
            if cookie:
                cookies.append(cookie)
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            raise CookieSeedError("DB_LOCKED", "Cookie DB is locked while reading copied DB") from exc
        raise CookieSeedError("DISK_READ_FAILED", f"Unable to read cookie DB: {exc}") from exc
    finally:
        temp_copy.unlink(missing_ok=True)

    LOGGER.info("[AUTH][DISK] loaded cookies count=%s profile=%s", len(cookies), chosen_profile)
    return SeedResult(
        mode_used="disk",
        cookies=cookies,
        details={"profile_dir": str(user_data_dir), "profile_name": chosen_profile, "cookie_db": str(cookie_db)},
    )


def _extract_port(cdp_url_or_port: str | int | None) -> int:
    if cdp_url_or_port is None:
        return int(os.getenv("CHROME_CDP_PORT", str(DEFAULT_CDP_PORT)))
    if isinstance(cdp_url_or_port, int):
        return cdp_url_or_port
    raw = str(cdp_url_or_port).strip()
    if raw.isdigit():
        return int(raw)
    if ":" in raw:
        try:
            return int(raw.rsplit(":", 1)[1].strip("/"))
        except Exception:
            pass
    return DEFAULT_CDP_PORT


def launch_debug_chrome(*, chrome_path: Path, user_data_dir: Path, profile_name: str = "Default", port: int = DEFAULT_CDP_PORT) -> subprocess.Popen:
    user_data_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    LOGGER.info("[AUTH][CDP] launching debug Chrome cmd=%s", command)
    return subprocess.Popen(command)


def seed_from_cdp(cdp_url_or_port: str | int | None, domains: list[str]) -> SeedResult:
    selected_domains = normalize_domains(domains)
    port = _extract_port(cdp_url_or_port)
    try:
        ws = connect_browser_ws(port)
    except ChromeCDPError as exc:
        raise CookieSeedError("CDP_UNAVAILABLE", f"No debuggable Chrome found on port {port}: {exc}") from exc

    try:
        all_cookies = get_all_cookies(ws)
    except ChromeCDPError as exc:
        raise CookieSeedError("CDP_QUERY_FAILED", f"Failed querying cookies via CDP: {exc}") from exc
    finally:
        ws.close()

    filtered = [
        {
            "name": str(cookie.get("name") or ""),
            "value": str(cookie.get("value") or ""),
            "domain": str(cookie.get("domain") or ""),
            "path": str(cookie.get("path") or "/"),
            "expires": int(cookie.get("expires")) if isinstance(cookie.get("expires"), (int, float)) else None,
            "secure": bool(cookie.get("secure")),
            "httpOnly": bool(cookie.get("httpOnly")),
            "sameSite": cookie.get("sameSite"),
        }
        for cookie in all_cookies
        if _domain_match(str(cookie.get("domain") or ""), selected_domains)
    ]
    LOGGER.info("[AUTH][CDP] loaded cookies count=%s port=%s", len(filtered), port)
    return SeedResult(mode_used="cdp", cookies=filtered, details={"cdp_port": port})


def seed_auto(*, profile_dir: str | Path, domains: list[str], profile_name: str | None = None, cdp_url_or_port: str | int | None = None) -> SeedResult:
    try:
        return seed_from_disk(profile_dir, domains, profile_name=profile_name)
    except CookieSeedError as exc:
        if exc.code != "DB_LOCKED":
            raise
        LOGGER.warning("[AUTH][DISK] DB locked after retries; falling back to CDP")
        cdp_result = seed_from_cdp(cdp_url_or_port, domains)
        cdp_result.details["fallback_from"] = "disk"
        cdp_result.details["fallback_reason"] = "DB_LOCKED"
        return cdp_result


def import_cookies_auto(
    *,
    profile_dir: str | Path,
    domains: list[str],
    profile_name: str | None = None,
    cdp_url_or_port: str | int | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        result = seed_from_disk(profile_dir, domains, profile_name=profile_name)
        return {
            "method_used": "disk",
            "imported_count": len(result.cookies),
            "warnings": warnings,
            "cookies": result.cookies,
            "details": result.details,
        }
    except CookieSeedError as exc:
        if exc.code != "DB_LOCKED":
            raise
        lock_warning = "Disk cookie DB locked; switched to CDP import. Close browser to prefer disk import."
        warnings.append(lock_warning)
        LOGGER.warning("[AUTH][DISK] DB locked after retries; falling back to CDP")

    cdp_result = seed_from_cdp(cdp_url_or_port, domains)
    cdp_result.details["fallback_from"] = "disk"
    cdp_result.details["fallback_reason"] = "DB_LOCKED"
    return {
        "method_used": "cdp",
        "imported_count": len(cdp_result.cookies),
        "warnings": warnings,
        "cookies": cdp_result.cookies,
        "details": cdp_result.details,
    }


def auth_doctor(*, chrome_path: str | None = None, profile_dir: str | Path | None = None, profile_name: str | None = None, cdp_port: int = DEFAULT_CDP_PORT) -> dict[str, Any]:
    selected_profile_name = resolve_profile_name(profile_name)
    user_data_dir = resolve_chrome_user_data_dir(profile_dir)
    cookie_db = resolve_cookie_db_path(user_data_dir, selected_profile_name)

    browser = Path((chrome_path or os.getenv("CHROME_PATH") or "").strip()) if (chrome_path or os.getenv("CHROME_PATH")) else None

    checks: list[dict[str, Any]] = []

    checks.append({"check": "CHROME_PATH exists", "ok": bool(browser and browser.exists()), "value": str(browser) if browser else None})
    checks.append({"check": "Profile dir exists", "ok": user_data_dir.exists(), "value": str(user_data_dir)})
    checks.append({"check": "Cookies DB exists", "ok": cookie_db.exists(), "value": str(cookie_db)})

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    port_listening = sock.connect_ex(("127.0.0.1", int(cdp_port))) == 0
    sock.close()
    checks.append({"check": f"CDP port {cdp_port} listening", "ok": port_listening, "value": f"127.0.0.1:{cdp_port}"})

    json_version_ok = False
    json_version_error = None
    if port_listening:
        try:
            with urllib_request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                json_version_ok = isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            json_version_error = str(exc)
    checks.append(
        {
            "check": f"CDP /json/version valid JSON on {cdp_port}",
            "ok": json_version_ok,
            "value": None if json_version_ok else json_version_error,
        }
    )

    fixes: list[str] = []
    if not checks[0]["ok"]:
        fixes.append("Set CHROME_PATH to chrome.exe (or edge executable) before seeding auth.")
    if not checks[1]["ok"]:
        fixes.append("Set CHROME_USER_DATA_DIR to your Chrome User Data path.")
    if checks[1]["ok"] and not checks[2]["ok"]:
        fixes.append(f"Verify profile name '{selected_profile_name}' exists (Default, Profile 1, ...).")
    if not port_listening:
        fixes.append(f"Start Chrome with --remote-debugging-port={cdp_port} or use Launch Debug Chrome.")
    elif not json_version_ok:
        fixes.append("CDP port is open but /json/version is invalid. Restart debug Chrome instance.")

    return {
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "fixes": fixes,
        "profile_name": selected_profile_name,
    }
