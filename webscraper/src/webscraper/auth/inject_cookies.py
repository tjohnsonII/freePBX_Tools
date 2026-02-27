from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from webscraper.auth.imported_cookies import load_imported_cookies


def _host_matches_domain(host: str, domain: str) -> bool:
    clean_host = (host or "").strip().lower()
    clean_domain = (domain or "").strip().lower()
    if not clean_host or not clean_domain:
        return False
    domain_without_dot = clean_domain.lstrip(".")
    return (
        clean_domain == clean_host
        or clean_domain == f".{clean_host}"
        or clean_host.endswith(domain_without_dot)
    )


def inject_imported_cookies(driver: Any, base_urls: list[str]) -> dict[str, Any]:
    cookies = load_imported_cookies()
    applied = 0
    skipped = 0
    errors = 0
    domains: set[str] = set()
    hosts: set[str] = set()

    for base_url in base_urls:
        parts = urlsplit(base_url)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
        if not host:
            continue
        hosts.add(host)
        try:
            driver.get(base_url)
        except Exception:
            errors += 1
            continue

        for cookie in cookies:
            domain = str(cookie.get("domain") or "").strip().lower()
            if not _host_matches_domain(host, domain):
                skipped += 1
                continue
            if scheme == "http" and bool(cookie.get("secure")):
                skipped += 1
                continue
            safe_cookie = {
                key: cookie[key]
                for key in ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "expiry")
                if key in cookie
            }
            domains.add(domain.lstrip("."))
            try:
                driver.add_cookie(safe_cookie)
                applied += 1
            except Exception:
                errors += 1
                continue

        try:
            driver.refresh()
        except Exception:
            errors += 1

    return {
        "applied": applied,
        "skipped": skipped,
        "domains": sorted(domain for domain in domains if domain),
        "hosts": sorted(hosts),
        "errors": errors,
    }


__all__ = ["inject_imported_cookies"]
