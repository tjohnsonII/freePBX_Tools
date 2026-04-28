"""Scraper for 123.net Orders Web Admin.

Pulls all orders assigned to a given PM username via a single authenticated POST,
parses the HTML, and returns structured records ready for upsert_orders().

Required env vars:
    ORDERS_123NET_USERNAME  — 123.net admin username (e.g. tjohnson)
    ORDERS_123NET_PASSWORD  — 123.net admin password

Optional env vars:
    ORDERS_123NET_PM        — PM username to filter on (defaults to ORDERS_123NET_USERNAME)
    ORDERS_ADMIN_URL        — override the CGI URL (default: the secure.123.net URL)

Usage:
    from webscraper.scrapers.orders_admin_scraper import scrape_orders
    records = scrape_orders()
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup

_LOG = logging.getLogger(__name__)

_DEFAULT_URL = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"

_ORDER_ID_RE = re.compile(r'^[A-Z0-9]{3}-[A-Z0-9]{8}$')
_DATE_RE     = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# Patterns applied to the task description (cell 3)
_SEATS_RE    = re.compile(r'(\d+)\s+seats?', re.I)
_IP_RE       = re.compile(r'\bIP:\s*([\d.]+)', re.I)
_PHONE_RE    = re.compile(r'(\d+)\s+(Yealink|Polycom|Cisco|Grandstream)\s+([A-Z0-9\-]+)', re.I)
_PON_RE      = re.compile(r'\bPON[:\s]+([A-Z0-9\-]+)', re.I)
_ADDR_RE     = re.compile(
    r'[-–]\s*'                       # dash separator before address
    r'(\d+\s+[A-Z0-9 ,\.#]+?)'      # street number + name
    r'\s+(?:[A-Z][a-z]+\s+){1,3}'   # city
    r'(?:MI|OH|IN|IL|WI|MN|PA|NY)\s+\d{5}',  # state + zip
    re.I,
)
_TYPE_RE = re.compile(
    r'^(OTT\s+Hosted|UCaaS|HOSTED|Hosted|SIP\s+Trunking|Internet)',
    re.I,
)


def scrape_orders(
    username: str | None = None,
    password: str | None = None,
    pm_filter: str | None = None,
    url: str | None = None,
    timeout: int = 45,
) -> list[dict[str, Any]]:
    """Fetch and parse orders from 123.net Orders Web Admin.

    Auth flow:
      1. Session() with Basic Auth — credentials sent on every request via
         the Authorization header. The CGI sets a session cookie (noc-tickets)
         on the first response; Session() carries it automatically on all
         subsequent requests in this call.
      2. GET the base URL first to establish the session cookie, then POST
         with the filter params to get the filtered order list.

    Falls back to env vars when arguments are not supplied.
    Returns a list of order dicts suitable for db_client.upsert_orders().
    """
    username   = username   or os.environ["ORDERS_123NET_USERNAME"]
    password   = password   or os.environ["ORDERS_123NET_PASSWORD"]
    pm_filter  = pm_filter  or os.getenv("ORDERS_123NET_PM") or username
    url        = url        or os.getenv("ORDERS_ADMIN_URL") or _DEFAULT_URL

    _LOG.info("orders_admin_scraper: fetching orders for pm=%s", pm_filter)

    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; internal-scraper/1.0)"})

    # Step 1 — establish session cookie. The CGI sets noc-tickets on first
    # authenticated GET; Session() carries it automatically on the POST below.
    init = session.get(url, timeout=timeout)
    if init.status_code == 401:
        raise PermissionError(
            f"orders_admin_scraper: 401 Unauthorized — check ORDERS_123NET_USERNAME "
            f"and ORDERS_123NET_PASSWORD in your .env"
        )
    init.raise_for_status()
    _LOG.debug("orders_admin_scraper: session established, cookies=%s",
               list(session.cookies.keys()))

    # Step 2 — POST with filter to get orders for this PM
    resp = session.post(
        url,
        data={
            "web_show_bill":      "y",
            "web_netopsengineer": pm_filter,
            "web_last_note":      "summary",
            "web_neteng":         "All",
            "web_core":           "All",
            "web_bill":           "All",
            "web_sort":           "standard",
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    records = _parse_html(resp.text, pm_filter)
    _LOG.info("orders_admin_scraper: parsed %d orders", len(records))
    return records


def _parse_html(html: str, pm: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    orders: dict[str, dict[str, Any]] = {}  # keyed by order_id; deduplicates multi-site rows

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 5:
            continue

        cells = [td.get_text(" ", strip=True) for td in tds]
        order_id = cells[1].strip()

        if not _ORDER_ID_RE.match(order_id):
            continue

        date_val   = cells[0].strip()
        task       = cells[3]
        assigned   = cells[4].strip()
        link_tag   = tds[1].find("a")
        detail_url = link_tag["href"] if link_tag else ""

        # Only keep dispatch rows (real date) or task rows ("N days")
        is_dispatch = bool(_DATE_RE.match(date_val))

        # Parse task description
        seats_m = _SEATS_RE.search(task)
        ip_m    = _IP_RE.search(task)
        phone_m = _PHONE_RE.search(task)
        pon_m   = _PON_RE.search(task)
        addr_m  = _ADDR_RE.search(task)
        type_m  = _TYPE_RE.match(task)

        phone_str = ""
        if phone_m:
            phone_str = f"{phone_m.group(1)}x {phone_m.group(2)} {phone_m.group(3)}"

        install_type = type_m.group(0).strip().upper() if type_m else ""
        on_net_ott   = "OTT" if "ott" in install_type.lower() else "ON-NET"

        if order_id not in orders:
            orders[order_id] = {
                "order_id":       order_id,
                "customer_name":  cells[2],
                "customer_abbrev": order_id.split("-")[0],
                "dispatch_date":  date_val if is_dispatch else "",
                "install_type":   install_type,
                "task":           task,
                "assigned":       assigned,
                "pm":             pm,
                "detail_url":     detail_url,
                "seats":          seats_m.group(1) if seats_m else "",
                "pbx_ip":         ip_m.group(1) if ip_m else "",
                "phone_model":    phone_str,
                "location":       addr_m.group(0).lstrip("-– ").strip() if addr_m else "",
                "pon":            pon_m.group(1) if pon_m else "",
                "on_net_ott":     on_net_ott,
                "scraped_utc":    now_utc,
            }
        else:
            # Merge additional data from extra rows (multi-site orders)
            existing = orders[order_id]
            if is_dispatch and not existing["dispatch_date"]:
                existing["dispatch_date"] = date_val
            if ip_m and not existing["pbx_ip"]:
                existing["pbx_ip"] = ip_m.group(1)
            if phone_m and not existing["phone_model"]:
                existing["phone_model"] = phone_str
            if seats_m and not existing["seats"]:
                existing["seats"] = seats_m.group(1)
            if addr_m and not existing["location"]:
                existing["location"] = addr_m.group(0).lstrip("-– ").strip()
            if pon_m and not existing["pon"]:
                existing["pon"] = pon_m.group(1)

    return list(orders.values())
