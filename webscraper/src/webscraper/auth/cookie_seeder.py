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
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from websocket import create_connection

from webscraper.auth.chrome_cdp import ChromeCDPError, connect_browser_ws, find_free_port, get_all_cookies, launch_chrome_with_debug
from webscraper.auth.chrome_cookies import ChromeCookieError, copy_cookie_db_for_read

try:  # optional dependency
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - optional import
    AESGCM = None

LOGGER = logging.getLogger(__name__)

DEFAULT_CDP_PORT = 9222
DEFAULT_DOMAINS = ["secure.123.net", "123.net"]
CDP_ALLOWED_ORIGIN = "http://127.0.0.1:9222"


def is_cdp_origin_rejected(error_text: str) -> bool:
    text = str(error_text or "")
    lowered = text.lower()
    return (
        "403" in lowered
        and "websocket" in lowered
        and ("remote-allow-origins" in lowered or "rejected an incoming websocket connection" in lowered)
    )


def cdp_availability(port: int, *, check_ws: bool = True) -> dict[str, Any]:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    status: dict[str, Any] = {
        "cdp_port": int(port),
        "json_version_ok": False,
        "ws_connectable": False,
        "status": "no_browser",
        "error": None,
        "websocket_debugger_url": None,
    }
    try:
        with urllib_request.urlopen(endpoint, timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        status["error"] = str(exc)
        status["skip_reason"] = "CDP endpoint unreachable"
        return status

    ws_url = str(payload.get("webSocketDebuggerUrl") or "").strip() if isinstance(payload, dict) else ""
    status["json_version_ok"] = True
    status["websocket_debugger_url"] = ws_url or None
    if not ws_url:
        status["status"] = "missing_websocket_debugger_url"
        status["error"] = "missing_websocket_debugger_url"
        status["skip_reason"] = "CDP /json/version missing websocket debugger URL"
        return status

    if not check_ws:
        status["status"] = "json_version_ok"
        return status

    ws = None
    try:
        ws = create_connection(ws_url, timeout=2)
        status["ws_connectable"] = True
        status["status"] = "ok"
        return status
    except Exception as exc:
        error_text = str(exc)
        status["error"] = error_text
        status["status"] = "ws_origin_rejected" if is_cdp_origin_rejected(error_text) else "ws_connect_failed"
        status["skip_reason"] = (
            "CDP websocket origin rejected"
            if status["status"] == "ws_origin_rejected"
            else "CDP websocket connection failed"
        )
        return status
    finally:
        if ws is not None:
            ws.close()


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


def browser_user_data_dir(browser: str) -> Path:
    browser_name = str(browser or "chrome").strip().lower()
    local_app_data = (os.getenv("LOCALAPPDATA") or "").strip()
    if browser_name == "chrome":
        return Path(local_app_data) / "Google" / "Chrome" / "User Data" if local_app_data else Path.home() / ".config" / "google-chrome"
    if browser_name == "edge":
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data" if local_app_data else Path.home() / ".config" / "microsoft-edge"
    raise ValueError(f"Unsupported browser '{browser}'. Expected one of: chrome, edge")


def list_browser_profiles(browser: str) -> list[str]:
    root = browser_user_data_dir(browser)
    if not root.exists():
        return []
    profiles: list[str] = []
    if (root / "Default").is_dir():
        profiles.append("Default")
    profiles.extend(sorted(path.name for path in root.glob("Profile *") if path.is_dir()))
    return profiles


def resolve_profile_name(profile_name: str | None = None) -> str:
    candidate = (profile_name or os.getenv("CHROME_PROFILE_DIR") or "").strip()
    return candidate or "Default"


def resolve_cookie_db_path(profile_dir: str | Path, profile_name: str) -> Path:
    return Path(profile_dir) / profile_name / "Network" / "Cookies"


def cookie_db_candidates(profile_dir: Path) -> list[Path]:
    return [profile_dir / "Network" / "Cookies", profile_dir / "Cookies"]


def resolve_profile_dir(browser: str, profile_name: str | None, *, user_data_dir: Path | None = None) -> Path:
    root = user_data_dir or browser_user_data_dir(browser)
    requested = (profile_name or os.getenv("CHROME_PROFILE_DIR") or "").strip()
    if requested:
        requested_path = root / requested
        if requested_path.is_dir():
            return requested_path

    default_profile = root / "Default"
    if default_profile.is_dir():
        return default_profile

    candidates = [
        profile
        for profile in root.iterdir()
        if profile.is_dir() and any(cookie_path.exists() for cookie_path in cookie_db_candidates(profile))
    ] if root.exists() else []
    candidates.sort(key=lambda candidate: (candidate.name != "Default", candidate.name.lower()))
    if candidates:
        return candidates[0]

    if requested:
        return root / requested
    return default_profile


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, sqlite3.OperationalError) and "locked" in message:
        return True
    if "sharing violation" in message or "database is locked" in message:
        return True
    return False


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


def seed_from_disk(profile_dir: str | Path | None, domains: list[str], *, profile_name: str | None = None, browser: str = "chrome") -> SeedResult:
    selected_domains = normalize_domains(domains)
    user_data_dir = Path(profile_dir) if profile_dir else browser_user_data_dir(browser)
    profile_dir_path = resolve_profile_dir(browser, profile_name, user_data_dir=user_data_dir)
    chosen_profile = profile_dir_path.name
    candidates = cookie_db_candidates(profile_dir_path)
    cookie_db = next((path for path in candidates if path.exists()), None)
    LOGGER.info("Cookie import requested: browser=%s profile=%s domains=%s", browser, chosen_profile, selected_domains)
    LOGGER.info("Resolved profile dir: %s", profile_dir_path)
    if cookie_db is None:
        raise CookieSeedError(
            "COOKIE_DB_MISSING",
            f"Cookie DB not found for browser={browser} profile={chosen_profile}",
            details={"profile_dir": str(profile_dir_path), "candidates": [str(path) for path in candidates]},
        )
    LOGGER.info("Cookie DB selected: %s", cookie_db)

    try:
        temp_copy = copy_cookie_db_for_read(cookie_db)
    except ChromeCookieError as exc:
        if exc.code == "DB_LOCKED":
            raise CookieSeedError(
                "DB_LOCKED",
                "Cookie DB locked. Close Chrome/Edge OR use CDP method (Launch Debug Chrome).",
            ) from exc
        raise CookieSeedError("DISK_COPY_FAILED", f"Failed copying cookie DB: {exc}") from exc

    temp_dir = temp_copy.parent
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
        shutil.rmtree(temp_dir, ignore_errors=True)

    LOGGER.info("[AUTH][DISK] loaded cookies count=%s profile=%s", len(cookies), chosen_profile)
    return SeedResult(
        mode_used="disk",
        cookies=cookies,
        details={
            "browser": browser,
            "profile_dir": str(profile_dir_path),
            "profile_name": chosen_profile,
            "cookie_db": str(cookie_db),
            "cookie_db_candidates": [str(path) for path in candidates],
        },
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
    allowed_origin = CDP_ALLOWED_ORIGIN if port == DEFAULT_CDP_PORT else f"http://127.0.0.1:{port}"
    command = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins={allowed_origin}",
        "--remote-allow-origins=*",
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
        details = {"cdp_port": port}
        if is_cdp_origin_rejected(str(exc)):
            details["remote_allow_origins_hint"] = f"--remote-allow-origins=http://127.0.0.1:{port}"
            raise CookieSeedError(
                "CDP_WS_ORIGIN_REJECTED",
                f"Chrome CDP websocket origin rejected on port {port}: {exc}",
                details=details,
            ) from exc
        raise CookieSeedError("CDP_UNAVAILABLE", f"No debuggable Chrome found on port {port}: {exc}", details=details) from exc

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


def _cdp_json_version_ok(port: int) -> tuple[bool, str | None]:
    availability = cdp_availability(port, check_ws=False)
    return bool(availability.get("json_version_ok")), availability.get("error")


def _select_auto_source(cdp_url_or_port: str | int | None) -> tuple[str, dict[str, Any]]:
    port = _extract_port(cdp_url_or_port)
    ws_diag = cdp_availability(port, check_ws=True)
    cdp_ok, cdp_error = _cdp_json_version_ok(port)
    diagnostics = {
        "cdp_port": port,
        "cdp_reachable": cdp_ok,
        "cdp_ws_connectable": bool(ws_diag.get("ws_connectable")),
        "cdp_status": ws_diag.get("status"),
    }
    if cdp_error:
        diagnostics["cdp_error"] = cdp_error
    if ws_diag.get("error"):
        diagnostics["cdp_ws_error"] = ws_diag.get("error")
    if ws_diag.get("skip_reason"):
        diagnostics["cdp_skip_reason"] = ws_diag.get("skip_reason")

    # Prefer CDP when json/version is live (flow A), even if websocket attach fails.
    # This keeps the primary failure visible (e.g., origin rejection) instead of
    # silently masking it with a profile fallback.
    return ("cdp", diagnostics) if cdp_ok else ("disk", diagnostics)


def seed_auto(*, profile_dir: str | Path | None, domains: list[str], profile_name: str | None = None, cdp_url_or_port: str | int | None = None, browser: str = "chrome") -> SeedResult:
    source, diagnostics = _select_auto_source(cdp_url_or_port)
    LOGGER.info("[AUTH][AUTO] selected source=%s diagnostics=%s", source, diagnostics)
    if source == "cdp":
        cdp_result = seed_from_cdp(cdp_url_or_port, domains)
        cdp_result.details.update({"auto_selected_source": "cdp", **diagnostics})
        return cdp_result
    try:
        disk_result = seed_from_disk(profile_dir, domains, profile_name=profile_name, browser=browser)
        disk_result.details.update({"auto_selected_source": "disk", **diagnostics})
        return disk_result
    except CookieSeedError as exc:
        if exc.code != "DB_LOCKED":
            raise
        LOGGER.warning("[AUTH][AUTO] disk source locked; fallback to CDP diagnostics=%s", diagnostics)
        cdp_result = seed_from_cdp(cdp_url_or_port, domains)
        cdp_result.details.update({"fallback_from": "disk", "fallback_reason": "DB_LOCKED", "auto_selected_source": "disk", **diagnostics})
        return cdp_result


def import_cookies_auto(
    *,
    profile_dir: str | Path | None,
    domains: list[str],
    profile_name: str | None = None,
    cdp_url_or_port: str | int | None = None,
    browser: str = "chrome",
) -> dict[str, Any]:
    warnings: list[str] = []
    attempted: list[dict[str, Any]] = []
    source, diagnostics = _select_auto_source(cdp_url_or_port)
    LOGGER.info("[AUTH][AUTO] import selected source=%s diagnostics=%s", source, diagnostics)

    def _result_payload(method: str, result: SeedResult) -> dict[str, Any]:
        return {
            "method_used": method,
            "imported_count": len(result.cookies),
            "warnings": warnings,
            "cookies": result.cookies,
            "details": {**result.details, **diagnostics, "attempted_sources": attempted},
        }

    if source == "cdp":
        attempted.append({"source": "cdp_debug_chrome", "status": "selected"})
        try:
            cdp_result = seed_from_cdp(cdp_url_or_port, domains)
            cdp_result.details["source"] = "cdp_debug_chrome"
            return _result_payload("cdp", cdp_result)
        except CookieSeedError as exc:
            attempted[-1]["status"] = "failed"
            attempted[-1]["reason"] = exc.code
            attempted[-1]["message"] = str(exc)
            warnings.append(f"CDP import failed ({exc.code}); trying browser profile import.")
            LOGGER.warning("[AUTH][AUTO] cdp selected but failed reason=%s diagnostics=%s", exc.code, diagnostics)
            if exc.code == "CDP_WS_ORIGIN_REJECTED":
                warnings.append(
                    f"CDP websocket origin rejected on {diagnostics.get('cdp_port')}; "
                    "relaunch with --remote-allow-origins and retry Seed Auth."
                )

    attempted.append({"source": f"{browser}_profile", "status": "selected"})
    try:
        disk_result = seed_from_disk(profile_dir, domains, profile_name=profile_name, browser=browser)
        disk_result.details["source"] = f"{browser}_profile"
        return _result_payload("disk", disk_result)
    except CookieSeedError as exc:
        attempted[-1]["status"] = "failed"
        attempted[-1]["reason"] = exc.code
        LOGGER.warning("[AUTH][AUTO] disk import failed reason=%s diagnostics=%s", exc.code, diagnostics)
        if exc.code != "DB_LOCKED":
            raise

        lock_warning = "Disk cookie DB locked; switched to CDP import. Close browser to prefer disk import."
        warnings.append(lock_warning)
        attempted.append({"source": "cdp_debug_chrome", "status": "fallback"})
        cdp_result = seed_from_cdp(cdp_url_or_port, domains)
        cdp_result.details.update({"fallback_from": "disk", "fallback_reason": "DB_LOCKED", "source": "cdp_debug_chrome"})
        return _result_payload("cdp", cdp_result)


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
