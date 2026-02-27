from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from webscraper.auth.imported_cookies import load_imported_cookies
from webscraper.lib.db_path import get_tickets_db_path
from webscraper.ticket_api import db as ticket_api_db
from webscraper.ticket_api.auth import cookie_to_selenium


def _host_matches_domain(host: str, domain: str) -> bool:
    clean_host = (host or "").strip().lower()
    clean_domain = (domain or "").strip().lower().lstrip(".")
    if not clean_host or not clean_domain:
        return False
    return clean_host == clean_domain or clean_host.endswith(f".{clean_domain}")


def load_all_imported_cookies() -> list[dict[str, Any]]:
    cookies = ticket_api_db.get_auth_cookies(get_tickets_db_path())
    if cookies:
        return cookies
    return load_imported_cookies()


def inject_imported_cookies(driver: Any, base_urls: list[str]) -> dict[str, Any]:
    cookies = load_all_imported_cookies()
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
            raw_domain = str(cookie.get("domain") or "").strip().lower()
            cookie_domain = raw_domain.lstrip(".")
            if not _host_matches_domain(host, raw_domain):
                skipped += 1
                continue
            if scheme == "http" and bool(cookie.get("secure")):
                skipped += 1
                continue
            safe_cookie = cookie_to_selenium(cookie)
            domains.add(cookie_domain)
            try:
                driver.add_cookie(safe_cookie)
                applied += 1
            except Exception:
                errors += 1

        try:
            driver.refresh()
        except Exception:
            errors += 1

    return {"applied": applied, "skipped": skipped, "domains": sorted(d for d in domains if d), "hosts": sorted(hosts), "errors": errors}


__all__ = ["inject_imported_cookies", "load_all_imported_cookies"]
