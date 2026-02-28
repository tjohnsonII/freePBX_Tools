from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

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


class ChromeCookieError(RuntimeError):
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


def seed_isolated_profile(*, var_root: Path, chrome_profile_dir: str | None = None, seed_domains: list[str] | None = None) -> SeededProfileResult:
    source_profile = _source_profile_path(chrome_profile_dir)
    source_cookie_db = _source_cookie_db(source_profile)
    allowed = [_normalize_domain(domain) for domain in (seed_domains or ["secure.123.net"]) if _normalize_domain(domain)]
    if not allowed:
        allowed = ["secure.123.net"]

    target_profile = _new_seeded_profile_dir(var_root)
    target_cookie_db = target_profile / "Default" / "Network" / "Cookies"
    domain_counts = _seed_cookie_db(source_cookie_db, target_cookie_db, allowed)

    return SeededProfileResult(
        source_profile_dir=str(source_profile),
        temp_profile_dir=str(target_profile),
        cookie_db_path=str(target_cookie_db),
        seeded_domains=allowed,
        domain_counts=domain_counts,
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
    cookie_db = profile / "Default" / "Network" / "Cookies"
    if not cookie_db.exists():
        raise ChromeCookieError(f"Profile cookie DB not found: {cookie_db}")

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
