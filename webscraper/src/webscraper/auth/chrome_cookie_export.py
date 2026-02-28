"""
Windows-only Chromium cookie export helper.

WARNING: Exported cookies contain sensitive authenticated session data.
The output directory ``webscraper/var/cookies/`` is gitignored to help prevent
accidental commits, but exported files must still be handled as secrets.
"""

from __future__ import annotations

# Usage with the scraper:
# PowerShell
# $path = python -m webscraper.auth.chrome_cookie_export --domain secure.123.net
# $env:SCRAPER_COOKIE_FILES = $path
# python -m webscraper.ultimate_scraper --handles KPM

import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    import win32crypt
    from Crypto.Cipher import AES


CHROME_EPOCH_UNIX_OFFSET_SECONDS = 11_644_473_600


def _assert_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("chrome_cookie_export is Windows-only (expected sys.platform == 'win32').")


def _browser_user_data_dir(browser: str) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set; cannot locate Chromium profile data.")

    normalized = browser.strip().lower()
    if normalized == "chrome":
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if normalized == "edge":
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    raise ValueError("browser must be 'chrome' or 'edge'.")


def _load_master_key(local_state_path: Path) -> bytes:
    local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)
    key_material = encrypted_key[5:]  # strip DPAPI prefix
    return win32crypt.CryptUnprotectData(key_material, None, None, None, 0)[1]


def _decrypt_cookie_value(encrypted_value: bytes, master_key: bytes) -> str:
    if not encrypted_value:
        return ""

    # Chromium AES-GCM format starts with b"v10" (or v11) prefix.
    if encrypted_value.startswith((b"v10", b"v11")):
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="replace")

    # Legacy DPAPI path.
    return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8", errors="replace")


def _chrome_expires_to_unix(expires_utc: int | float | None) -> int:
    if not expires_utc:
        return 0
    return max(0, int(int(expires_utc) / 1_000_000 - CHROME_EPOCH_UNIX_OFFSET_SECONDS))


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


def export_cookies(domain: str = "secure.123.net", profile: str = "Default", browser: str = "chrome") -> str:
    _assert_windows()

    user_data_dir = _browser_user_data_dir(browser)
    local_state_path = user_data_dir / "Local State"
    cookies_db_path = user_data_dir / profile / "Network" / "Cookies"

    if not local_state_path.exists():
        raise FileNotFoundError(f"Local State not found: {local_state_path}")
    if not cookies_db_path.exists():
        raise FileNotFoundError(f"Cookies database not found: {cookies_db_path}")

    master_key = _load_master_key(local_state_path)

    with tempfile.NamedTemporaryFile(prefix="cookies_db_", suffix=".sqlite", delete=False) as temp_db:
        temp_db_path = Path(temp_db.name)
    try:
        shutil.copy(cookies_db_path, temp_db_path)
        conn = sqlite3.connect(str(temp_db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, encrypted_value, host_key, path, is_secure, expires_utc
                FROM cookies
                WHERE host_key = ? OR host_key = ?
                """,
                (domain, f".{domain.lstrip('.')}"),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
    finally:
        temp_db_path.unlink(missing_ok=True)

    normalized = []
    for name, encrypted_value, host_key, path, is_secure, expires_utc in rows:
        value = _decrypt_cookie_value(encrypted_value, master_key)
        normalized.append(
            {
                "name": name,
                "value": value,
                "domain": host_key,
                "path": path or "/",
                "secure": bool(is_secure),
                "expires": _chrome_expires_to_unix(expires_utc),
            }
        )

    project_root = Path(__file__).resolve().parents[3]
    output_dir = project_root / "var" / "cookies"
    output_dir.mkdir(parents=True, exist_ok=True)

    outfile = output_dir / (
        f"cookies_{_safe_name(browser.lower())}_{_safe_name(profile)}_{_safe_name(domain.lstrip('.'))}.json"
    )
    outfile.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(outfile.resolve())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export decrypted Chromium cookies for scraper auth.")
    parser.add_argument("--domain", default="secure.123.net", help="Target domain/host_key to export.")
    parser.add_argument("--profile", default="Default", help="Browser profile directory name.")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"], help="Browser source.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        out_path = export_cookies(domain=args.domain, profile=args.profile, browser=args.browser)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
