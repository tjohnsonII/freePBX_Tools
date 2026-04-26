"""
orders.py — scrape 123NET orders_web_admin.cgi and return structured JSON.

Uses cookies exported from the browser (webscraper/cookies.json) to make
an authenticated requests.Session call to secure.123.net, then parses the
HTML table with BeautifulSoup.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

LOGGER = logging.getLogger("webscraper.orders")

ORDERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"
COOKIE_PATHS = [
    Path(__file__).resolve().parents[4] / "webscraper" / "cookies.json",
    Path(__file__).resolve().parents[4] / "webscraper" / "var" / "cookies" / "cookies.json",
]
TIMEOUT = 20

router = APIRouter(prefix="/api/orders", tags=["orders"])


# ── cookie loading ────────────────────────────────────────────────────────────

def _load_cookie_jar() -> dict[str, str]:
    """Return {name: value} for all 123.net cookies from the first found cookie file."""
    for path in COOKIE_PATHS:
        if path.exists():
            try:
                raw: list[dict] = json.loads(path.read_text(encoding="utf-8"))
                jar = {
                    c["name"]: c["value"]
                    for c in raw
                    if isinstance(c, dict)
                    and "123.net" in c.get("domain", "")
                    and c.get("name") and c.get("value")
                }
                LOGGER.info("Loaded %d cookies from %s", len(jar), path)
                return jar
            except Exception as exc:
                LOGGER.warning("Failed to parse %s: %s", path, exc)
    return {}


# ── HTML parser ───────────────────────────────────────────────────────────────

def _parse_orders(html: str) -> list[dict[str, str]]:
    """Parse the orders table HTML into a list of order dicts."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        LOGGER.error("BeautifulSoup not installed — run: pip install beautifulsoup4")
        return []

    soup = BeautifulSoup(html, "html.parser")
    orders: list[dict[str, str]] = []

    # The page renders tasks as <tr> rows inside the main content table.
    # Each row has: date | order_id link | company_abbrev | company_name | description | tech
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        texts = [c.get_text(separator=" ", strip=True) for c in cells]

        # Date column: looks like 2026-04-29
        date_text = texts[0]
        if not (len(date_text) == 10 and date_text[4] == "-" and date_text[7] == "-"):
            continue

        # Order ID may be a link
        order_link = cells[1].find("a")
        order_id = order_link.get_text(strip=True) if order_link else texts[1]

        # Split company abbrev from company name if they're in the same cell
        company_abbrev = texts[2] if len(texts) > 2 else ""
        company_name = texts[3] if len(texts) > 3 else ""
        description = texts[4] if len(texts) > 4 else ""
        tech = texts[-1] if texts else ""

        # Skip header rows or rows that don't look like real orders
        if not order_id or order_id.lower() in {"order id", "id", ""}:
            continue

        orders.append({
            "install_date": date_text,
            "order_id": order_id,
            "customer_abbrev": company_abbrev,
            "customer_name": company_name,
            "description": description,
            "project_manager": tech,
            "location": _extract_location(description),
        })

    return orders


def _extract_location(description: str) -> str:
    """Best-effort: pull the street address from the description line."""
    # Descriptions often end with the address: "... - 1042 N MILFORD RD Milford MI 48381"
    if " - " in description:
        parts = description.rsplit(" - ", 1)
        return parts[-1].strip()
    return ""


# ── request helper ────────────────────────────────────────────────────────────

def _fetch_orders(pm: str, status: str) -> dict[str, Any]:
    try:
        import requests as req
    except ImportError:
        return {"ok": False, "error": "requests not installed", "orders": []}

    jar = _load_cookie_jar()
    if not jar:
        return {"ok": False, "error": "No 123.net cookies found — export cookies from your browser first.", "orders": []}

    session = req.Session()
    session.cookies.update(jar)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": ORDERS_URL,
    })

    params: dict[str, str] = {
        "pm": pm,
        "status": status,
        "special_function": "Summary Only",
        "filter": "Filter",
    }

    try:
        resp = session.get(ORDERS_URL, params=params, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "orders": []}

    # Detect redirect to login page
    if "login" in resp.url.lower() or "sign_in" in resp.url.lower():
        return {"ok": False, "error": "Session expired — re-export cookies from your browser.", "orders": []}

    orders = _parse_orders(resp.text)
    return {"ok": True, "orders": orders, "count": len(orders), "pm": pm, "url": resp.url}


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_orders(
    pm: str = Query(default="tjohnson", description="PM/engineer username to filter by"),
    status: str = Query(default="Default", description="Order status filter"),
) -> dict:
    """
    Fetch scheduled orders for a PM from the 123NET orders admin page.
    Returns structured order data ready to populate the Order Tracker tab.
    """
    return _fetch_orders(pm=pm, status=status)
