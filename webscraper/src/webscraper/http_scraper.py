"""HTTP-only scraping utilities.

Selenium is used only to obtain authenticated cookies; all data fetching happens
through HTTP requests for stability and speed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import json
import os

import requests

try:
    from bs4 import BeautifulSoup
except Exception as exc:
    BeautifulSoup = None
    _BS4_IMPORT_ERROR = exc
else:
    _BS4_IMPORT_ERROR = None

DEFAULT_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class FetchResult:
    ok: bool
    status_code: int
    url: str
    html: str
    auth_valid: bool
    auth_indicator: bool


def _require_bs4() -> Any:
    if BeautifulSoup is None:
        raise RuntimeError(
            "BeautifulSoup (bs4) is required for HTML parsing. Install with `pip install beautifulsoup4`."
        ) from _BS4_IMPORT_ERROR
    return BeautifulSoup


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _extract_text(node: Any) -> str:
    if not node:
        return ""
    return node.get_text(" ", strip=True)


def load_selenium_cookies(path: str) -> list[dict[str, Any]]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        return [item for item in payload.get("cookies") if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def session_from_selenium_cookies(cookies: Iterable[dict[str, Any]]) -> requests.Session:
    session = requests.Session()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name:
            continue
        rest = {}
        if "httpOnly" in cookie:
            rest["HttpOnly"] = cookie.get("httpOnly")
        expiry = cookie.get("expiry")
        try:
            expiry = int(expiry) if expiry is not None else None
        except (TypeError, ValueError):
            expiry = None
        session.cookies.set(
            name,
            value,
            domain=cookie.get("domain"),
            path=cookie.get("path"),
            secure=bool(cookie.get("secure")),
            expires=expiry,
            rest=rest or None,
        )
    return session


def _find_label_value(soup: Any, labels: Iterable[str]) -> str:
    label_set = {_normalize(label) for label in labels}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        for idx, cell in enumerate(cells):
            if _normalize(_extract_text(cell)) in label_set and idx + 1 < len(cells):
                return _extract_text(cells[idx + 1])
    for dt in soup.find_all("dt"):
        if _normalize(_extract_text(dt)) in label_set:
            dd = dt.find_next_sibling("dd")
            return _extract_text(dd)
    return ""


def _table_headers(table: Any) -> tuple[list[str], list[str]]:
    header_cells = [
        cell for cell in table.find_all("th") if _extract_text(cell)
    ]
    if header_cells:
        headers = [_normalize(_extract_text(cell)) for cell in header_cells]
        raw_headers = [_extract_text(cell) for cell in header_cells]
        return headers, raw_headers
    first_row = table.find("tr")
    if not first_row:
        return [], []
    raw_headers = [_extract_text(cell) for cell in first_row.find_all(["td", "th"])]
    return [_normalize(text) for text in raw_headers], raw_headers


def _find_table_by_headers(soup: Any, required: Iterable[str]) -> Optional[Any]:
    required_norm = {_normalize(item) for item in required}
    for table in soup.find_all("table"):
        headers, _ = _table_headers(table)
        if not headers:
            continue
        if required_norm.issubset(set(headers)):
            return table
    return None


def _map_row(headers: list[str], cells: list[str], alias_map: dict[str, list[str]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for idx, header in enumerate(headers):
        for key, aliases in alias_map.items():
            if any(alias in header for alias in aliases):
                mapped[key] = cells[idx] if idx < len(cells) else ""
                break
    return mapped


def parse_company_details(soup: Any) -> dict[str, str]:
    # TODO/VERIFY: Adjust label matching based on the live customer page layout.
    return {
        "name": _find_label_value(soup, ["Company Name", "Company"]),
        "handle": _find_label_value(soup, ["Company Handle", "Handle"]),
        "phone": _find_label_value(soup, ["Phone Number", "Phone", "Telephone"]),
        "address": _find_label_value(soup, ["Address", "Service Address"]),
    }


def parse_circuits(soup: Any) -> list[dict[str, str]]:
    # TODO/VERIFY: Confirm circuit table headers in production HTML.
    required = ["pon", "type", "circuit id", "service address"]
    table = _find_table_by_headers(soup, required)
    if not table:
        return []
    headers, raw_headers = _table_headers(table)
    alias_map = {
        "pon": ["pon"],
        "type": ["type"],
        "circuit_id": ["circuit id", "circuit"],
        "service_address": ["service address", "address"],
    }
    rows = []
    for row in table.find_all("tr"):
        cells = [
            _extract_text(cell)
            for cell in row.find_all(["td", "th"])
        ]
        if not cells or cells == raw_headers:
            continue
        mapped = _map_row(headers, cells, alias_map)
        if any(mapped.values()):
            rows.append(mapped)
    return rows


def parse_tickets(soup: Any) -> list[dict[str, str]]:
    # TODO/VERIFY: Confirm ticket table headers in production HTML.
    required = ["ticket id", "subject", "status", "priority", "created on"]
    table = _find_table_by_headers(soup, required)
    if not table:
        return []
    headers, raw_headers = _table_headers(table)
    alias_map = {
        "ticket_id": ["ticket id", "ticket #", "id"],
        "subject": ["subject", "summary"],
        "status": ["status"],
        "priority": ["priority"],
        "created_on": ["created on", "created", "opened"],
    }
    rows = []
    for row in table.find_all("tr"):
        cells = [
            _extract_text(cell)
            for cell in row.find_all(["td", "th"])
        ]
        if not cells or cells == raw_headers:
            continue
        mapped = _map_row(headers, cells, alias_map)
        if any(mapped.values()):
            rows.append(mapped)
    return rows


def parse_customer_html(html: str, handle: str) -> dict[str, Any]:
    bs4 = _require_bs4()
    soup = bs4(html, "html.parser")
    company = parse_company_details(soup)
    if not company.get("handle"):
        company["handle"] = handle
    return {
        "handle": handle,
        "company": company,
        "circuits": parse_circuits(soup),
        "tickets": parse_tickets(soup),
    }


def detect_auth_indicator(html: str) -> bool:
    return "company handle" in _normalize(html)


def fetch_customer(
    handle: str,
    cookies_path: str,
    user_agent: Optional[str] = None,
    timeout: int = 30,
    url: str = DEFAULT_URL,
) -> FetchResult:
    cookies = load_selenium_cookies(cookies_path)
    session = session_from_selenium_cookies(cookies)
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Referer": url,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "customer": f"company_handle:{handle}",
        "option_fe": "retrieve",
    }
    response = session.post(url, data=payload, headers=headers, timeout=timeout, allow_redirects=True)
    html = response.text or ""
    redirected_to_login = False
    if response.history:
        for prior in response.history:
            location = prior.headers.get("Location", "")
            if "login" in location.lower():
                redirected_to_login = True
                break
    if "login" in response.url.lower():
        redirected_to_login = True
    auth_indicator = detect_auth_indicator(html)
    auth_valid = not redirected_to_login and auth_indicator
    return FetchResult(
        ok=response.ok,
        status_code=response.status_code,
        url=response.url,
        html=html,
        auth_valid=auth_valid,
        auth_indicator=auth_indicator,
    )
