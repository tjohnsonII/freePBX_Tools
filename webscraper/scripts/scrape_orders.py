"""Scraper for secure.123.net orders_web_admin.cgi.

Auth flow (two layers, both required):
  1. HTTP Basic Auth — sent on every request (CGI checks it stateless).
  2. noc-tickets session cookie — server sets it on the first GET;
     requests.Session() captures and resends it automatically on the POST.

Required env vars:
  ORDERS_123NET_USERNAME  — 123.net admin username (e.g. tjohnson)
  ORDERS_123NET_PASSWORD  — 123.net admin password

Optional env vars:
  ORDERS_123NET_PM   — PM/engineer to filter by (default: same as USERNAME)
  CLIENT_MODE        — set to 1 to ingest to remote server via /api/ingest/orders
  INGEST_SERVER_URL  — required when CLIENT_MODE=1
  INGEST_API_KEY     — required when CLIENT_MODE=1
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

ORDERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAYS_RE = re.compile(r"^(\d+)\s+days?$", re.IGNORECASE)
_ORDER_ID_RE = re.compile(r"^[A-Z0-9]{3}-[A-F0-9]+$", re.IGNORECASE)

# Order type keywords to detect from description
_ORDER_TYPE_PREFIXES = (
    "UCaaS INSTALL",
    "UCaaS Install",
    "OTT HOSTED INSTALL",
    "OTT Hosted Install",
    "HOSTED INSTALL",
    "Hosted Install",
    "HOSTED MACD",
    "Hosted MACD",
    "SIP INSTALL",
    "Sip Install",
)


# ── Auth ──────────────────────────────────────────────────────────────────────


def _build_session() -> requests.Session:
    user = os.environ.get("ORDERS_123NET_USERNAME", "").strip()
    passwd = os.environ.get("ORDERS_123NET_PASSWORD", "").strip()
    if not user or not passwd:
        raise RuntimeError(
            "Set ORDERS_123NET_USERNAME and ORDERS_123NET_PASSWORD env vars."
        )

    s = requests.Session()
    s.auth = (user, passwd)
    s.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    s.headers["Referer"] = ORDERS_URL
    return s


# ── Fetch ──────────────────────────────────────────────────────────────────────


def fetch_orders(pm: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch and parse orders for pm (defaults to ORDERS_123NET_PM or USERNAME).

    Two-step flow:
      1. GET  → establishes session, captures noc-tickets cookie automatically.
      2. POST → sends filter params, returns filtered HTML.
    """
    session = _build_session()
    if not pm:
        pm = os.environ.get(
            "ORDERS_123NET_PM",
            os.environ.get("ORDERS_123NET_USERNAME", ""),
        ).strip()

    # Step 1: GET to establish session cookie
    LOGGER.info("GET %s to establish session cookie", ORDERS_URL)
    get_resp = session.get(ORDERS_URL, timeout=20, allow_redirects=True)
    get_resp.raise_for_status()
    if "login" in get_resp.url.lower():
        raise PermissionError("401 Unauthorized — check ORDERS_123NET_USERNAME / PASSWORD")

    # Step 2: POST with filter params
    payload = {
        "web_show_bill": "y",
        "web_search_order_id": "",
        "web_request_type": "",
        "web_fac_type": "",
        "web_bucket": "",
        "web_pm": "",
        "web_netopsengineer": pm,
        "web_tech": "",
        "web_cft": "",
        "web_calendar": "",
        "web_order_type": "",
        "web_status": "",
        "web_company_type": "",
        "web_priority": "",
        "web_exp": "",
        "web_neteng": "All",
        "web_core": "All",
        "web_bill": "All",
        "web_last_note": "summary",
        "web_sort": "standard",
    }
    LOGGER.info("POST %s (pm=%s)", ORDERS_URL, pm)
    post_resp = session.post(ORDERS_URL, data=payload, timeout=30)
    post_resp.raise_for_status()

    return _parse_orders(post_resp.text)


# ── Parse ──────────────────────────────────────────────────────────────────────


def _extract_order_type(description: str) -> str:
    desc_upper = description.upper()
    for prefix in _ORDER_TYPE_PREFIXES:
        if desc_upper.startswith(prefix.upper()):
            return prefix
    # Fallback: first two words
    words = description.split()
    return " ".join(words[:2]) if len(words) >= 2 else description[:30]


def _extract_location(description: str) -> str:
    """Pull the street address from the end of the description line."""
    if " - " in description:
        return description.rsplit(" - ", 1)[-1].strip()
    return ""


def _parse_orders(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, Any]] = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) != 5:
            continue

        texts = [c.get_text(" ", strip=True) for c in cells]
        col0, col1, col2, col3, col4 = texts

        # col1 must look like an order ID
        if not _ORDER_ID_RE.match(col1):
            continue

        # col0 determines row type
        if _DATE_RE.match(col0):
            row_type = "dispatch"
            install_date: str | None = col0
        elif _DAYS_RE.match(col0):
            row_type = "task"
            install_date = None
        else:
            continue

        link = cells[1].find("a")
        detail_url = link["href"] if link else ""

        assigned_str = col4.strip()
        order_type = _extract_order_type(col3)

        rows.append(
            {
                "row_type":       row_type,
                "order_id":       col1,
                "customer_name":  col2,
                "customer_abbrev": col1.split("-")[0],
                "dispatch_date":  install_date or "",
                "install_type":   order_type,
                "task":           col3,
                "assigned":       assigned_str,
                "pm":             os.environ.get("ORDERS_123NET_PM", os.environ.get("ORDERS_123NET_USERNAME", "")),
                "detail_url":     detail_url,
                "location":       _extract_location(col3),
                "on_net_ott":     "OTT" if "ott" in order_type.lower() else "ON-NET",
                "seats":          "",
                "pbx_ip":         "",
                "phone_model":    "",
                "pon":            "",
                "scraped_utc":    now_utc,
            }
        )

    return rows


# ── Ingest ─────────────────────────────────────────────────────────────────────


def ingest_orders(records: list[dict[str, Any]]) -> int:
    """Push records to the ticket API (local or remote via CLIENT_MODE)."""
    if not records:
        return 0

    # Add the shared path so we can import the db/db_client modules
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    client_mode = os.environ.get("CLIENT_MODE", "").strip() == "1"

    if client_mode:
        from webscraper.ticket_api import db_client as db_mod  # type: ignore[import]
        db_path = ""
    else:
        from webscraper.ticket_api import db as db_mod  # type: ignore[import]
        db_path = str(Path(__file__).resolve().parents[1] / "var" / "db" / "tickets.sqlite")

    if not client_mode:
        db_mod.ensure_indexes(db_path)

    n = db_mod.upsert_orders(db_path, records, now_utc)
    return n


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    pm = os.environ.get(
        "ORDERS_123NET_PM",
        os.environ.get("ORDERS_123NET_USERNAME", ""),
    ).strip()

    if not pm:
        print("Set ORDERS_123NET_USERNAME env var.", file=sys.stderr)
        sys.exit(1)

    LOGGER.info("Fetching orders for pm=%s", pm)
    all_orders = fetch_orders(pm=pm)
    dispatch = [o for o in all_orders if o["row_type"] == "dispatch"]
    LOGGER.info(
        "%d total rows, %d dispatch rows",
        len(all_orders),
        len(dispatch),
    )

    n = ingest_orders(dispatch)
    LOGGER.info("Ingested %d order records", n)

    # Also write JSON to var/orders/ for debugging
    out_dir = Path(__file__).resolve().parents[1] / "var" / "orders"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "orders.json"
    out.write_text(json.dumps(dispatch, indent=2), encoding="utf-8")
    LOGGER.info("Wrote %s", out)


if __name__ == "__main__":
    main()
