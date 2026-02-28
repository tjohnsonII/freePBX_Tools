from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from webscraper.auth.chrome_cdp import (
    ChromeCDPError,
    connect_browser_ws,
    find_free_port,
    get_all_cookies,
    launch_chrome_with_debug,
    navigate,
    set_cookie,
)

try:  # optional dependency
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - optional import
    AESGCM = None


CHROME_CUSTOMERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
_ALLOWED_COOKIE_COLUMNS = "host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]


@dataclass
class SeededProfileResult:
    source_profile_dir: str
    temp_profile_dir: str
    cookie_db_path: str
    seeded_domains: list[str]
    domain_counts: dict[str, int]
    seed_method: str


class ChromeCookieError(RuntimeError):
    pass


class ChromeCookieDBLockedError(ChromeCookieError):
    pass


def _chrome_user_data_base() -> Path:
    local_app_data = (os.getenv("LOCALAPPDATA") or "").strip()
    if not local_app_data:
        raise ChromeCookieError("LOCALAPPDATA is not set; cannot locate Chrome user profile.")
    return Path(local_app_data) / "Google" / "Chrome" / "User Data"


def list_chrome_profile_dirs() -> list[str]:
    base = _chrome_user_data_base()
    if not base.exists():
        return []
    profile_dirs: list[str] = []
    if (base / "Default").is_dir():
        profile_dirs.append("Default")
    profile_dirs.extend(sorted(path.name for path in base.glob("Profile *") if path.is_dir()))
    return profile_dirs


def _source_profile_path(chrome_profile_dir: str | None = None) -> Path:
    base = _chrome_user_data_base()
    requested = (chrome_profile_dir or "").strip()
    if requested:
        requested_path = base / requested
        if requested_path.is_dir():
            return requested_path

    profile_1 = base / "Profile 1"
    if profile_1.is_dir():
        return profile_1

    default = base / "Default"
    if default.is_dir():
        return default

    candidates = [path for path in base.glob("Profile *") if path.is_dir()]
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)

    if requested:
        raise ChromeCookieError(f"Chrome profile not found: {base / requested}")
    raise ChromeCookieError(f"No Chrome profile directory found under: {base}")


def _source_cookie_db(profile_path: Path) -> Path:
    db_path = profile_path / "Network" / "Cookies"
    if not db_path.exists():
        raise ChromeCookieError(f"Chrome cookie database not found: {db_path}")
    return db_path


def _profile_root(var_root: Path) -> Path:
    return var_root / "chrome_profiles"


def _new_seeded_profile_dir(var_root: Path) -> Path:
    profile_root = _profile_root(var_root)
    profile_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    target = profile_root / f"seeded_{timestamp}"
    (target / "Default" / "Network").mkdir(parents=True, exist_ok=True)
    return target


def _normalize_domain(domain: str) -> str:
    return str(domain or "").strip().lstrip(".").lower()


def _domain_allowed(host_key: str, allowed_domains: list[str]) -> bool:
    normalized_host = _normalize_domain(host_key)
    return any(normalized_host == allowed or normalized_host.endswith(f".{allowed}") for allowed in allowed_domains)


def _copy_to_temp(source_path: Path) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        temp_path = Path(tmp.name)
    shutil.copy2(source_path, temp_path)
    return temp_path


def _is_win_lock_error(exc: Exception) -> bool:
    return isinstance(exc, PermissionError) and getattr(exc, "winerror", None) == 32


def _domain_matches_allowed(cookie_domain: str, allowed_domains: list[str]) -> bool:
    normalized = _normalize_domain(cookie_domain)
    return any(normalized == allowed or normalized.endswith(f".{allowed}") for allowed in allowed_domains)


def _filter_cdp_cookies(cookies: list[dict[str, Any]], allowed_domains: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        if not _domain_matches_allowed(domain, allowed_domains):
            continue
        counts[domain] = counts.get(domain, 0) + 1
        filtered.append(cookie)
    return filtered, counts


def _map_same_site(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered == "unspecified":
        return None
    mapping = {
        "lax": "Lax",
        "strict": "Strict",
        "none": "None",
        "samesitestrict": "Strict",
        "samesitelax": "Lax",
        "samesitenone": "None",
    }
    return mapping.get(lowered)


def _seed_cookies_via_cdp(
    *,
    chrome_path: Path,
    source_profile_dir_name: str,
    target_profile_dir: Path,
    allowed_domains: list[str],
    target_url: str,
) -> dict[str, int]:
    source_port = find_free_port()
    target_port = find_free_port()
    source_proc: subprocess.Popen | None = None
    target_proc: subprocess.Popen | None = None
    source_ws = None
    target_ws = None

    try:
        source_proc = launch_chrome_with_debug(
            chrome_path=chrome_path,
            profile_dir_name=source_profile_dir_name,
            user_data_dir=str(_chrome_user_data_base()),
            port=source_port,
            initial_url="about:blank",
        )
        source_ws = connect_browser_ws(source_port)
        source_cookies = get_all_cookies(source_ws)
        filtered_cookies, domain_counts = _filter_cdp_cookies(source_cookies, allowed_domains)

        target_proc = launch_chrome_with_debug(
            chrome_path=chrome_path,
            profile_dir_name="Default",
            user_data_dir=str(target_profile_dir),
            port=target_port,
            initial_url="about:blank",
        )
        target_ws = connect_browser_ws(target_port)

        for cookie in filtered_cookies:
            payload: dict[str, Any] = {
                "name": str(cookie.get("name") or ""),
                "value": str(cookie.get("value") or ""),
                "domain": str(cookie.get("domain") or ""),
                "path": str(cookie.get("path") or "/"),
                "secure": bool(cookie.get("secure")),
                "httpOnly": bool(cookie.get("httpOnly")),
            }
            expires = cookie.get("expires")
            if isinstance(expires, (int, float)) and expires > 0:
                payload["expires"] = float(expires)
            same_site = _map_same_site(cookie.get("sameSite"))
            if same_site:
                payload["sameSite"] = same_site
            if payload["domain"].lstrip(".").lower() == "secure.123.net":
                payload["url"] = "https://secure.123.net/"
            set_cookie(target_ws, payload)

        navigate(target_ws, target_url)
        return domain_counts
    except ChromeCDPError as exc:
        raise ChromeCookieError(f"CDP cookie seeding failed: {exc}") from exc
    finally:
        if source_ws:
            source_ws.close()
        if target_ws:
            target_ws.close()
        if source_proc and source_proc.poll() is None:
            source_proc.terminate()


def _seed_cookie_db(src_db: Path, dst_db: Path, allowed_domains: list[str]) -> dict[str, int]:
    temp_copy = _copy_to_temp(src_db)
    try:
        shutil.copy2(temp_copy, dst_db)
        with sqlite3.connect(dst_db) as conn:
            rows = conn.execute("SELECT host_key, COUNT(*) FROM cookies GROUP BY host_key").fetchall()
            domain_counts = {str(row[0]): int(row[1]) for row in rows if _domain_allowed(str(row[0]), allowed_domains)}
            conn.execute("DELETE FROM cookies")
            with sqlite3.connect(temp_copy) as src_conn:
                keep_rows = src_conn.execute(
                    f"SELECT {_ALLOWED_COOKIE_COLUMNS} FROM cookies"
                ).fetchall()
            filtered_rows = [row for row in keep_rows if _domain_allowed(str(row[0]), allowed_domains)]
            conn.executemany(
                "INSERT INTO cookies(host_key,name,value,encrypted_value,path,expires_utc,is_secure,is_httponly,samesite) VALUES(?,?,?,?,?,?,?,?,?)",
                filtered_rows,
            )
            conn.execute("VACUUM")
            return domain_counts
    finally:
        temp_copy.unlink(missing_ok=True)


def seed_isolated_profile(
    *,
    var_root: Path,
    chrome_path: Path,
    chrome_profile_dir: str | None = None,
    seed_domains: list[str] | None = None,
    target_url: str = CHROME_CUSTOMERS_URL,
) -> SeededProfileResult:
    source_profile = _source_profile_path(chrome_profile_dir)
    allowed = [_normalize_domain(domain) for domain in (seed_domains or ["secure.123.net", "123.net"]) if _normalize_domain(domain)]
    if not allowed:
        allowed = ["secure.123.net", "123.net"]

    target_profile = _new_seeded_profile_dir(var_root)
    target_cookie_db = target_profile / "Default" / "Network" / "Cookies"
    seed_method = "cdp"
    try:
        domain_counts = _seed_cookies_via_cdp(
            chrome_path=chrome_path,
            source_profile_dir_name=source_profile.name,
            target_profile_dir=target_profile,
            allowed_domains=allowed,
            target_url=target_url,
        )
    except ChromeCookieError:
        seed_method = "sqlite_copy"
        source_cookie_db = _source_cookie_db(source_profile)
        try:
            domain_counts = _seed_cookie_db(source_cookie_db, target_cookie_db, allowed)
        except PermissionError as exc:
            if _is_win_lock_error(exc):
                raise ChromeCookieDBLockedError("Chrome is running and cookie DB is locked. Use CDP seeding path.") from exc
            raise

    return SeededProfileResult(
        source_profile_dir=str(source_profile),
        temp_profile_dir=str(target_profile),
        cookie_db_path=str(target_cookie_db),
        seeded_domains=allowed,
        domain_counts=domain_counts,
        seed_method=seed_method,
    )


def _crypt_unprotect_data(data: bytes) -> bytes:
    if not data:
        return b""
    in_blob = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ChromeCookieError("CryptUnprotectData failed.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _load_os_crypt_key(user_data_base: Path) -> bytes | None:
    local_state_path = user_data_base / "Local State"
    if not local_state_path.exists():
        return None
    payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key_b64 = payload.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key_b64:
        return None
    encrypted_key = base64.b64decode(encrypted_key_b64)
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
            raise ChromeCookieError("AES-GCM cookie decryption unavailable; install cryptography or use unencrypted cookie values.")
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None).decode("utf-8", errors="replace")
    return _crypt_unprotect_data(encrypted_value).decode("utf-8", errors="replace")


def load_cookies_from_profile(profile_dir: str | Path, seed_domains: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    profile = Path(profile_dir)
    cookie_db = profile / "Network" / "Cookies"
    if not cookie_db.exists():
        raise ChromeCookieError(f"Profile cookie DB not found at: {cookie_db}")

    allowed = [_normalize_domain(domain) for domain in (seed_domains or ["secure.123.net"]) if _normalize_domain(domain)]
    if not allowed:
        allowed = ["secure.123.net"]

    temp_copy = _copy_to_temp(cookie_db)
    cookies: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    try:
        aes_key: bytes | None = None
        if sys.platform.startswith("win"):
            try:
                aes_key = _load_os_crypt_key(_chrome_user_data_base())
            except Exception:
                aes_key = None

        with sqlite3.connect(temp_copy) as conn:
            rows = conn.execute(
                "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite FROM cookies"
            ).fetchall()

        for host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite in rows:
            if not _domain_allowed(str(host_key), allowed):
                continue
            try:
                decrypted = _decrypt_cookie_value(encrypted_value or b"", str(value or ""), aes_key)
            except Exception:
                continue
            domain = str(host_key or "")
            counts[domain] = counts.get(domain, 0) + 1
            expires = None
            if expires_utc:
                try:
                    chrome_epoch_seconds = (int(expires_utc) / 1_000_000) - 11644473600
                    expires = int(chrome_epoch_seconds) if chrome_epoch_seconds > 0 else None
                except Exception:
                    expires = None
            cookies.append(
                {
                    "name": str(name or ""),
                    "value": decrypted,
                    "domain": domain,
                    "path": str(path or "/"),
                    "expires": expires,
                    "secure": bool(is_secure),
                    "httpOnly": bool(is_httponly),
                    "sameSite": str(samesite) if samesite is not None else None,
                }
            )
    finally:
        temp_copy.unlink(missing_ok=True)

    return cookies, counts
