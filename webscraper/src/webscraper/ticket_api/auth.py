from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any

from pydantic import BaseModel

DEFAULT_TARGET_DOMAINS = ["secure.123.net", "123.net"]


class CookieNormalized(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: int | None = None
    secure: bool | None = None
    httpOnly: bool | None = None
    sameSite: str | None = None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def get_target_domains() -> list[str]:
    raw = os.getenv("TARGET_DOMAINS", "")
    domains = [part.strip().lstrip(".").lower() for part in raw.split(",") if part.strip()]
    return domains or DEFAULT_TARGET_DOMAINS


def get_default_cookie_domain() -> str | None:
    value = (os.getenv("DEFAULT_COOKIE_DOMAIN") or "").strip().lstrip(".").lower()
    return value or None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _to_expiry(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        stamp = int(float(value))
    except Exception:
        return None
    return stamp if stamp > 0 else None


def _normalize_domain(domain: str) -> str:
    return str(domain or "").strip().lstrip(".").lower()


def _normalize_same_site(value: Any) -> str | None:
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if not lowered:
        return None
    mapping = {"strict": "Strict", "lax": "Lax", "none": "None", "unspecified": "Unspecified"}
    return mapping.get(lowered, str(value).strip())


def _normalize_cookie_item(item: dict[str, Any], idx: int, default_domain: str | None = None) -> CookieNormalized:
    name = str(item.get("name") or "").strip()
    value = str(item.get("value") or "")
    domain = _normalize_domain(item.get("domain") or item.get("hostOnly") or item.get("host") or default_domain or "")
    if not name:
        raise ValueError(f"Cookie at index {idx} missing required field: name")
    if domain == "":
        raise ValueError(f"Cookie at index {idx} missing required field: domain")
    return CookieNormalized(
        name=name,
        value=value,
        domain=domain,
        path=str(item.get("path") or "/"),
        expires=_to_expiry(item.get("expiry", item.get("expirationDate", item.get("expires")))),
        secure=_to_bool(item.get("secure")),
        httpOnly=_to_bool(item.get("httpOnly")),
        sameSite=_normalize_same_site(item.get("sameSite")),
    )


def parse_cookies_from_json(text: str) -> list[CookieNormalized]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc.msg}") from exc

    raw_cookies: Any = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("cookies"), list):
            raw_cookies = payload.get("cookies")
        else:
            raise ValueError("JSON object must include a 'cookies' array")

    if not isinstance(raw_cookies, list):
        raise ValueError("JSON cookie payload must be an array or object with 'cookies' array")

    cookies: list[CookieNormalized] = []
    for idx, item in enumerate(raw_cookies):
        if not isinstance(item, dict):
            continue
        cookies.append(_normalize_cookie_item(item, idx))
    return cookies


def parse_cookies_from_netscape(text: str) -> list[CookieNormalized]:
    cookies: list[CookieNormalized] = []
    for idx, line in enumerate(text.splitlines()):
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


def parse_cookies_from_cookie_header(text: str, default_domain: str) -> list[CookieNormalized]:
    if not default_domain:
        raise ValueError("Cookie header format requires a default domain")
    body = text.strip()
    if body.lower().startswith("cookie:"):
        body = body.split(":", 1)[1].strip()

    cookies: list[CookieNormalized] = []
    for idx, pair in enumerate(body.split(";")):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        if not name.strip():
            continue
        cookies.append(_normalize_cookie_item({"name": name.strip(), "value": value.strip()}, idx, default_domain=default_domain))
    return cookies


def parse_cookies(text: str, filename: str, default_domain: str | None) -> tuple[list[CookieNormalized], str]:
    lower_name = filename.lower()
    stripped = text.strip()
    if not stripped:
        raise ValueError("Uploaded file is empty")

    if lower_name.endswith(".json"):
        return parse_cookies_from_json(stripped), "json"

    if lower_name.endswith(".txt"):
        if "\t" in text or "netscape http cookie file" in stripped.lower():
            return parse_cookies_from_netscape(text), "netscape"
        if default_domain:
            return parse_cookies_from_cookie_header(text, default_domain), "cookie_header"
        raise ValueError("Cookie header TXT requires DEFAULT_COOKIE_DOMAIN or form field 'domain'")

    if stripped.startswith("[") or stripped.startswith("{"):
        return parse_cookies_from_json(stripped), "json"
    if "\t" in text or "netscape http cookie file" in stripped.lower():
        return parse_cookies_from_netscape(text), "netscape"
    if default_domain:
        return parse_cookies_from_cookie_header(text, default_domain), "cookie_header"
    raise ValueError("Unable to determine cookie format; provide .json/.txt file")


def domain_matches_selected(cookie_domain: str, selected_domains: list[str]) -> bool:
    domain = _normalize_domain(cookie_domain)
    if not domain:
        return False
    for selected in selected_domains:
        target = _normalize_domain(selected)
        if domain == target or domain.endswith(f".{target}"):
            return True
    return False


def filter_cookies_for_domains(cookies: list[CookieNormalized], target_domains: list[str]) -> list[CookieNormalized]:
    normalized_targets = [_normalize_domain(domain) for domain in target_domains if _normalize_domain(domain)]
    return [cookie for cookie in cookies if domain_matches_selected(cookie.domain, normalized_targets)]


def cookie_domain_summary(cookies: list[CookieNormalized], limit: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for cookie in cookies:
        counts[cookie.domain] = counts.get(cookie.domain, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [f"{domain}:{count}" for domain, count in ordered[:limit]]


def normalize_cookie_input(raw: Any, selected_domains: list[str] | None = None) -> list[dict[str, Any]]:
    if isinstance(raw, (dict, list)):
        text = json.dumps(raw)
        cookies, _ = parse_cookies(text, "payload.json", get_default_cookie_domain())
    elif isinstance(raw, str):
        cookies, _ = parse_cookies(raw, "payload.txt", get_default_cookie_domain())
    else:
        raise ValueError("Unsupported cookie payload")

    if selected_domains:
        cookies = filter_cookies_for_domains(cookies, selected_domains)
    return [cookie.model_dump() for cookie in cookies]


def cookie_header_for_domain(cookies: list[dict[str, Any]], domain: str) -> str:
    target = _normalize_domain(domain)
    parts: list[str] = []
    for cookie in cookies:
        cookie_domain = _normalize_domain(cookie.get("domain"))
        if cookie_domain == target or target.endswith(f".{cookie_domain}"):
            parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(parts)


def detected_missing_domains(stored_domains: list[str], selected_domains: list[str]) -> tuple[list[str], list[str]]:
    normalized_stored = sorted({_normalize_domain(d) for d in stored_domains if _normalize_domain(d)})
    normalized_selected = [_normalize_domain(d) for d in selected_domains if _normalize_domain(d)]
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
    expires = cookie.get("expires")
    if expires:
        payload["expiry"] = int(expires)
    elif cookie.get("expires_utc"):
        try:
            payload["expiry"] = int(datetime.fromisoformat(str(cookie["expires_utc"]).replace("Z", "+00:00")).timestamp())
        except Exception:
            pass
    if cookie.get("sameSite"):
        payload["sameSite"] = cookie.get("sameSite")
    return payload


def cookie_as_http_line(cookie: dict[str, Any]) -> str:
    expires = ""
    expiry = cookie.get("expires")
    if expiry:
        try:
            dt = datetime.fromtimestamp(int(expiry), tz=timezone.utc)
            expires = f"; Expires={format_datetime(dt, usegmt=True)}"
        except Exception:
            expires = ""
    return f"{cookie['name']}={cookie['value']}; Path={cookie.get('path') or '/'}; Domain={cookie.get('domain')}{expires}"
