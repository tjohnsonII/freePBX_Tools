"""
Windows-only Chromium cookie export helper for scraper authentication.

SECURITY WARNING:
- Exported cookies contain authenticated session credentials.
- Files are written to ``webscraper/var/cookies/``.
- That directory is gitignored, but treat each exported file like a password.
- Never share exported cookie files through chat/email/commits.
- This module intentionally avoids logging cookie values.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from webscraper.auth.chrome_cookies import ChromeCookieError, copy_cookie_db_for_read

if sys.platform == "win32":
    import win32crypt
    from Crypto.Cipher import AES

CHROME_EPOCH_UNIX_OFFSET_SECONDS = 11_644_473_600


def _assert_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("chrome_cookie_export is Windows-only (expected sys.platform == 'win32').")


def _resolve_user_data_dir(browser: str) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set; cannot locate browser profile data.")

    normalized = browser.strip().lower()
    if normalized == "chrome":
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if normalized == "edge":
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    raise ValueError("browser must be 'chrome' or 'edge'.")


def _resolve_cookies_db(user_data_dir: Path, profile: str) -> Path:
    profile_dir = user_data_dir / profile
    preferred = profile_dir / "Network" / "Cookies"
    fallback = profile_dir / "Cookies"
    if preferred.exists():
        return preferred
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Cookies DB not found for profile '{profile}': tried {preferred} and {fallback}")


def _load_master_key(local_state_path: Path) -> bytes:
    if not local_state_path.exists():
        raise FileNotFoundError(f"Local State not found: {local_state_path}")

    try:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
        encoded_key = local_state["os_crypt"]["encrypted_key"]
    except Exception as exc:
        raise RuntimeError(f"Failed to parse encrypted key from Local State: {local_state_path}") from exc

    try:
        encrypted_key = base64.b64decode(encoded_key)
    except Exception as exc:
        raise RuntimeError("Failed to base64 decode os_crypt.encrypted_key.") from exc

    if len(encrypted_key) <= 5:
        raise RuntimeError("Encrypted key from Local State is malformed (missing DPAPI prefix).")

    key_material = encrypted_key[5:]
    try:
        return win32crypt.CryptUnprotectData(key_material, None, None, None, 0)[1]
    except Exception as exc:
        raise RuntimeError("Failed to decrypt Chromium master key via DPAPI.") from exc


def _decrypt_cookie_value(encrypted_value: bytes, plain_value: str, master_key: bytes) -> str:
    if encrypted_value:
        if encrypted_value.startswith((b"v10", b"v11")):
            try:
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:-16]
                tag = encrypted_value[-16:]
                cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
                return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="replace")
            except Exception:
                pass

        try:
            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8", errors="replace")
        except Exception:
            pass

    return plain_value or ""


def _chrome_expires_to_unix(expires_utc: int | float | None) -> int:
    if not expires_utc:
        return 0
    unix = int(float(expires_utc) / 1_000_000 - CHROME_EPOCH_UNIX_OFFSET_SECONDS)
    return max(0, unix)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


def _output_dir() -> Path:
    webscraper_root = Path(__file__).resolve().parents[3]
    output = webscraper_root / "var" / "cookies"
    output.mkdir(parents=True, exist_ok=True)
    return output


def export_cookies(domain: str = "secure.123.net", profile: str = "Default", browser: str = "chrome") -> str:
    _assert_windows()

    user_data_dir = _resolve_user_data_dir(browser)
    local_state_path = user_data_dir / "Local State"
    cookies_db_path = _resolve_cookies_db(user_data_dir, profile)
    master_key = _load_master_key(local_state_path)

    try:
        temp_db_path = copy_cookie_db_for_read(cookies_db_path)
    except ChromeCookieError as exc:
        if exc.code == "DB_LOCKED":
            raise RuntimeError("Cookie DB locked. Close Chrome/Edge OR use CDP method (Launch Debug Chrome).") from exc
        raise

    try:
        conn = sqlite3.connect(str(temp_db_path))
        try:
            cursor = conn.cursor()
            normalized_domain = domain.lstrip(".")
            cursor.execute(
                """
                SELECT
                  host_key,
                  name,
                  value,
                  encrypted_value,
                  path,
                  is_secure,
                  expires_utc
                FROM cookies
                WHERE host_key = ?
                   OR host_key = ?
                   OR host_key LIKE ?
                """,
                (normalized_domain, f".{normalized_domain}", f"%.{normalized_domain}"),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
    finally:
        shutil.rmtree(temp_db_path.parent, ignore_errors=True)

    payload: list[dict[str, object]] = []
    for host_key, name, value, encrypted_value, path, is_secure, expires_utc in rows:
        cookie_value = _decrypt_cookie_value(encrypted_value or b"", str(value or ""), master_key)
        payload.append(
            {
                "name": str(name or ""),
                "value": cookie_value,
                "domain": str(host_key or ""),
                "path": str(path or "/"),
                "secure": bool(is_secure),
                "expires": _chrome_expires_to_unix(expires_utc),
            }
        )

    output_file = _output_dir() / (
        f"cookies_{_safe_name(browser.lower())}_{_safe_name(profile)}_{_safe_name(domain.lstrip('.'))}.json"
    )
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_file.resolve())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Chromium cookies from local browser profile.")
    parser.add_argument("--domain", default="secure.123.net")
    parser.add_argument("--profile", default="Default")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        path = export_cookies(domain=args.domain, profile=args.profile, browser=args.browser)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


# Optional Ticket API integration example (do not modify existing auth-store logic):
#
# @app.post("/api/auth/import-from-browser")
# def api_auth_import_from_browser(domain: str = "secure.123.net", profile: str = "Default", browser: str = "chrome"):
#     extracted_from = export_cookies(domain=domain, profile=profile, browser=browser)
#     import_result = import_cookie_file(extracted_from)
#     return {
#         "extracted_from": extracted_from,
#         "imported_count": int(import_result.get("imported_count", 0)),
#         "domain": domain,
#     }


if __name__ == "__main__":
    raise SystemExit(main())
