from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any

DEFAULT_TARGET_DOMAINS = ["secure.123.net", "noc-tickets.123.net", "10.123.203.1"]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _expires_utc(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        stamp = int(float(value))
    except Exception:
        return None
    if stamp <= 0:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_cookie_item(item: dict[str, Any], idx: int) -> dict[str, Any]:
    name = str(item.get("name") or "").strip()
    value = str(item.get("value") or "")
    domain = str(item.get("domain") or item.get("hostOnly") or item.get("host") or "").strip().lstrip(".").lower()
    if not name or not value:
        raise ValueError(f"Cookie at index {idx} missing required fields: name/value")
    if not domain:
        raise ValueError(f"Cookie at index {idx} missing required fields: domain")
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": str(item.get("path") or "/"),
        "secure": _to_bool(item.get("secure")),
        "httpOnly": _to_bool(item.get("httpOnly")),
        "expires_utc": _expires_utc(item.get("expiry", item.get("expirationDate", item.get("expires")))),
        "sameSite": item.get("sameSite") if item.get("sameSite") is not None else None,
    }


def _parse_cookie_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("cookies")
    if not isinstance(raw, list):
        raise ValueError("Expected a cookie list or {'cookies':[...]} payload")
    return [_normalize_cookie_item(item, idx) for idx, item in enumerate(raw) if isinstance(item, dict)]


def _parse_netscape_text(raw: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for idx, line in enumerate(raw.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, expiration, name, value = parts[:7]
        cookies.append(
            _normalize_cookie_item(
                {
                    "domain": domain,
                    "name": name,
                    "value": value,
                    "path": path,
                    "secure": secure.upper() == "TRUE",
                    "expires": expiration,
                    "httpOnly": False,
                },
                idx,
            )
        )
    return cookies


def _parse_cookie_header_text(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    cookies: list[dict[str, Any]] = []
    for idx, pair in enumerate(text.split(";")):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        n = name.strip()
        if not n:
            continue
        cookies.append(
            {
                "name": n,
                "value": value.strip(),
                "domain": "",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "expires_utc": None,
                "sameSite": None,
            }
        )
    return cookies


def normalize_cookie_input(raw: Any, selected_domains: list[str] | None = None) -> list[dict[str, Any]]:
    selected = [d.strip().lstrip(".").lower() for d in (selected_domains or []) if str(d).strip()]
    cookies: list[dict[str, Any]]
    if isinstance(raw, (dict, list)):
        cookies = _parse_cookie_list(raw)
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        if stripped.startswith("[") or stripped.startswith("{"):
            cookies = _parse_cookie_list(json.loads(stripped))
        elif "\t" in raw or "Netscape HTTP Cookie File" in raw:
            cookies = _parse_netscape_text(raw)
        else:
            cookies = _parse_cookie_header_text(raw)
    else:
        raise ValueError("Unsupported cookie payload")

    if cookies and any(not c.get("domain") for c in cookies):
        if not selected:
            raise ValueError("Cookie header format requires at least one selected domain")
        expanded: list[dict[str, Any]] = []
        for cookie in cookies:
            if cookie.get("domain"):
                expanded.append(cookie)
                continue
            for domain in selected:
                expanded.append({**cookie, "domain": domain})
        cookies = expanded

    if selected:
        cookies = [cookie for cookie in cookies if domain_matches_selected(cookie.get("domain", ""), selected)]

    return cookies


def domain_matches_selected(cookie_domain: str, selected_domains: list[str]) -> bool:
    domain = str(cookie_domain or "").strip().lstrip(".").lower()
    if not domain:
        return False
    for selected in selected_domains:
        target = selected.strip().lstrip(".").lower()
        if domain == target or domain.endswith(f".{target}") or target.endswith(f".{domain}"):
            return True
    return False


def cookie_header_for_domain(cookies: list[dict[str, Any]], domain: str) -> str:
    target = domain.strip().lower()
    parts: list[str] = []
    for cookie in cookies:
        cookie_domain = str(cookie.get("domain") or "").strip().lstrip(".").lower()
        if cookie_domain == target or target.endswith(f".{cookie_domain}"):
            parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(parts)


def detected_missing_domains(stored_domains: list[str], selected_domains: list[str]) -> tuple[list[str], list[str]]:
    normalized_stored = sorted({d.strip().lstrip('.').lower() for d in stored_domains if str(d).strip()})
    normalized_selected = [d.strip().lstrip('.').lower() for d in selected_domains if str(d).strip()]
    missing = [domain for domain in normalized_selected if not any(sd == domain or sd.endswith(f".{domain}") for sd in normalized_stored)]
    return normalized_stored, missing


def cookie_to_selenium(cookie: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "name": cookie.get("name"),
        "value": cookie.get("value"),
        "domain": str(cookie.get("domain") or "").lstrip("."),
        "path": cookie.get("path") or "/",
        "secure": bool(cookie.get("secure")),
        "httpOnly": bool(cookie.get("httpOnly")),
    }
    expires = cookie.get("expires_utc")
    if expires:
        try:
            payload["expiry"] = int(datetime.fromisoformat(str(expires).replace("Z", "+00:00")).timestamp())
        except Exception:
            pass
    if cookie.get("sameSite"):
        payload["sameSite"] = cookie.get("sameSite")
    return payload


def cookie_as_http_line(cookie: dict[str, Any]) -> str:
    expires = ""
    if cookie.get("expires_utc"):
        try:
            dt = datetime.fromisoformat(str(cookie["expires_utc"]).replace("Z", "+00:00"))
            expires = f"; Expires={format_datetime(dt, usegmt=True)}"
        except Exception:
            expires = ""
    return f"{cookie['name']}={cookie['value']}; Path={cookie.get('path') or '/'}; Domain={cookie.get('domain')}{expires}"
