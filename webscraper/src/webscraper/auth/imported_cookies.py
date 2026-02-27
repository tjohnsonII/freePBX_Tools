from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webscraper.paths import var_dir

_IMPORTED_COOKIES_PATH = var_dir() / "auth" / "imported_cookies.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_cookie_item(item: dict[str, Any], idx: int) -> dict[str, Any]:
    name = str(item.get("name") or "").strip()
    value = str(item.get("value") or "")
    domain = str(item.get("domain") or "").strip()
    if not domain:
        host_only = item.get("hostOnly") or item.get("host")
        if isinstance(host_only, str) and host_only.strip():
            domain = host_only.strip()
    if not name or not value:
        raise ValueError(f"Cookie at index {idx} missing required fields: name/value")
    if not domain:
        raise ValueError(f"Cookie at index {idx} missing required fields: domain/hostOnly")

    cookie: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": str(item.get("path") or "/"),
    }
    for bool_key in ("secure", "httpOnly"):
        if bool_key in item:
            cookie[bool_key] = bool(item.get(bool_key))
    same_site = item.get("sameSite")
    if same_site is not None:
        cookie["sameSite"] = same_site

    raw_expiry = item.get("expiry", item.get("expirationDate", item.get("expires")))
    if raw_expiry not in (None, ""):
        try:
            expiry = int(float(raw_expiry))
            if expiry > 0:
                cookie["expiry"] = expiry
        except Exception:
            pass

    return {
        key: cookie[key]
        for key in ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "expiry")
        if key in cookie
    }


def _parse_cookie_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("Expected JSON array of cookies or {'cookies': [...]} payload")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Cookie at index {idx} must be an object")
        normalized.append(_normalize_cookie_item(item, idx))
    return normalized


def _parse_netscape_text(raw: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, expiration, name, value = parts[:7]
        domain = domain.strip()
        name = name.strip()
        value = value.strip()
        if not name or not value or not domain:
            continue

        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path.strip() or "/",
            "secure": secure.strip().upper() == "TRUE",
            "httpOnly": False,
        }
        try:
            expiry = int(expiration.strip())
            if expiry > 0:
                cookie["expiry"] = expiry
        except Exception:
            pass
        normalized.append(cookie)
    return normalized


def parse_cookie_input(raw: str | dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return _parse_cookie_list(raw.get("cookies"))
    if isinstance(raw, list):
        return _parse_cookie_list(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON cookie payload") from exc
            return parse_cookie_input(payload)
        return _parse_netscape_text(raw)
    raise ValueError("Unsupported cookie payload type")


def _cookie_metadata(cookies: list[dict[str, Any]], *, stored_utc: str | None) -> dict[str, Any]:
    domains = sorted({str(cookie.get("domain") or "").lstrip(".") for cookie in cookies if cookie.get("domain")})
    return {
        "hasImportedCookies": bool(cookies),
        "count": len(cookies),
        "domains": domains,
        "stored_utc": stored_utc,
    }


def save_imported_cookies(data: Any) -> dict[str, Any]:
    cookies = parse_cookie_input(data)
    stored_utc = _iso_now()
    _IMPORTED_COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _IMPORTED_COOKIES_PATH.write_text(json.dumps({"stored_utc": stored_utc, "cookies": cookies}, indent=2), encoding="utf-8")
    return _cookie_metadata(cookies, stored_utc=stored_utc)


def load_imported_cookies() -> list[dict[str, Any]]:
    if not _IMPORTED_COOKIES_PATH.exists():
        return []
    try:
        payload = json.loads(_IMPORTED_COOKIES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    cookies = payload.get("cookies") if isinstance(payload, dict) else payload
    if not isinstance(cookies, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in cookies:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "")
        domain = str(item.get("domain") or "").strip()
        if not name or not value or not domain:
            continue
        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": str(item.get("path") or "/"),
        }
        for bool_key in ("secure", "httpOnly"):
            if bool_key in item:
                cookie[bool_key] = bool(item.get(bool_key))
        if "sameSite" in item and item.get("sameSite") is not None:
            cookie["sameSite"] = item.get("sameSite")
        raw_expiry = item.get("expiry", item.get("expirationDate", item.get("expires")))
        if raw_expiry not in (None, ""):
            try:
                cookie["expiry"] = int(float(raw_expiry))
            except Exception:
                pass
        normalized.append(cookie)
    return normalized


def clear_imported_cookies() -> None:
    if _IMPORTED_COOKIES_PATH.exists():
        _IMPORTED_COOKIES_PATH.unlink()


def get_imported_cookie_meta() -> dict[str, Any]:
    if not _IMPORTED_COOKIES_PATH.exists():
        return _cookie_metadata([], stored_utc=None)
    try:
        payload = json.loads(_IMPORTED_COOKIES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _cookie_metadata([], stored_utc=None)
    cookies = payload.get("cookies") if isinstance(payload, dict) else payload
    stored_utc = payload.get("stored_utc") if isinstance(payload, dict) else None
    if not isinstance(cookies, list):
        cookies = []
    valid = [cookie for cookie in cookies if isinstance(cookie, dict) and cookie.get("name") and cookie.get("domain")]
    return _cookie_metadata(valid, stored_utc=stored_utc)


def imported_cookies_path() -> Path:
    return _IMPORTED_COOKIES_PATH
