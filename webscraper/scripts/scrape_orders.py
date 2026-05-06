"""Three-phase order intelligence scraper for secure.123.net.

Discovery-driven design (see scripts/discover_pages.py for the HTML recon).

Phase 1 — orders_web_admin.cgi (POST filtered by PM)
  - 5-column summary row: install_date, order_id, customer, description, assigned
  - Per-order DETABLE: MRC, NRC, last-modified, log count, contract #, customer email,
    forecast date, BBNB date, most recent log entry text

Phase 2 — account_edit.cgi (per order, concurrent)
  - Handle derived from first 3 chars of order ID (e.g. CVV-69B2F941 → CVV)
  - GET account_edit.cgi?handle=XXX
  - Parse by known element IDs: #company_name, #handle, #address_1, #address_2,
    #city, #state_providence, #postal_code, #past_due, #account_balance, #net_terms

Phase 3 — dispatch.cgi (Man-Hour Summary)
  - Parses the CSV block in the <center> tag:
    PM, Order ID, Bill Date, Closed Date, Bill MRC
  - Also fetches per-week hosted calendar (web_calendar + web_week)

Auth: HTTP Basic Auth + noc-tickets session cookie (captured by requests.Session).

Required env vars:
  ORDERS_123NET_USERNAME  — 123.net admin username (e.g. tjohnson)
  ORDERS_123NET_PASSWORD  — 123.net admin password

Optional:
  ORDERS_123NET_PM    — filter PM/engineer (defaults to USERNAME)
  ORDERS_WORKERS      — concurrent workers for Phase 2 (default: 4, max: 10)
  ORDERS_PHASE2       — set to 0 to skip account_edit phase
  ORDERS_PHASE3       — set to 0 to skip dispatch phase
  CLIENT_MODE         — set to 1 to ingest via remote /api/ingest/orders
  INGEST_SERVER_URL   — required when CLIENT_MODE=1
  INGEST_API_KEY      — required when CLIENT_MODE=1
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

BASE_URL     = "https://secure.123.net"
_ADMIN_BASE  = "https://secure.123.net/cgi-bin/web_interface/admin/"
ORDERS_URL   = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"
ACCOUNT_URL  = "https://secure.123.net/cgi-bin/web_interface/admin/account_edit.cgi"
DISPATCH_URL = "https://secure.123.net/cgi-bin/web_interface/admin/dispatch.cgi"

_DATE_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAYS_RE       = re.compile(r"^(\d+)\s+days?$", re.IGNORECASE)
_ORDER_ID_RE   = re.compile(r"^[A-Z0-9]{3}-[A-F0-9]{8}$", re.IGNORECASE)

# Patterns for extracting data from DETABLE text
_CONTRACT_RE   = re.compile(r"Download\s+Contract\s+(\d+)", re.IGNORECASE)
_BBNB_FORE_RE  = re.compile(r"bbnb\s+forecast\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_BBNB_DATE_RE  = re.compile(r"BBNB\s+FORECASTED\s+DATE\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_QTY_TERM_RE   = re.compile(r"QTY:\s*(\d+),\s*TERM:\s*([^,]+),", re.IGNORECASE)
_SALESPERSON_RE= re.compile(r"salesperson\s+(\w+)", re.IGNORECASE)
_MAILTO_RE     = re.compile(r"^mailto:", re.IGNORECASE)

# Known element IDs for account_edit.cgi parsing
_ACCOUNT_ID_MAP: dict[str, str] = {
    "company_name":     "account_company",
    "handle":           "account_handle",
    "address_1":        "account_address",
    "address_2":        "account_address2",
    "city":             "account_city",
    "state_providence": "account_state",
    "postal_code":      "account_zip",
    "bill_refnum_p3":   "account_billing_ref",
    "company_type":     "account_type",
    "white_glove":      "account_white_glove",
}
_ACCOUNT_DIV_MAP: dict[str, str] = {
    "past_due":       "account_past_due",
    "account_balance": "account_balance",
    "net_terms":      "account_net_terms",
}

_ORDER_TYPE_PREFIXES = (
    "UCaaS INSTALL", "UCaaS Install",
    "OTT HOSTED INSTALL", "OTT Hosted Install",
    "HOSTED INSTALL", "Hosted Install",
    "HOSTED MACD", "Hosted MACD",
    "SIP INSTALL", "Sip Install",
)

# Hosted calendar regex as the 123.net form expects it
_HOSTED_CALENDAR = "^(hosted|netops|gobackeast)$"


# ── Utility ────────────────────────────────────────────────────────────────────


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _debug_dir() -> Path:
    d = Path(__file__).resolve().parents[1] / "var" / "orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve(href: str, base: str = BASE_URL) -> str:
    if not href or href.startswith("#") or href.startswith("javascript"):
        return ""
    try:
        return urljoin(base, href)
    except Exception:
        return href


# ── Auth ───────────────────────────────────────────────────────────────────────


def _build_session() -> requests.Session:
    user   = os.environ.get("ORDERS_123NET_USERNAME", "").strip()
    passwd = os.environ.get("ORDERS_123NET_PASSWORD", "").strip()
    if not user or not passwd:
        raise RuntimeError("Set ORDERS_123NET_USERNAME and ORDERS_123NET_PASSWORD env vars.")
    s = requests.Session()
    s.auth = (user, passwd)
    s.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    s.headers["Referer"] = ORDERS_URL
    return s


# ── Phase 1a: parse the 5-column summary rows ─────────────────────────────────


def _extract_order_type(description: str) -> str:
    desc_upper = description.upper()
    for prefix in _ORDER_TYPE_PREFIXES:
        if desc_upper.startswith(prefix.upper()):
            return prefix
    words = description.split()
    return " ".join(words[:2]) if len(words) >= 2 else description[:30]


def _extract_location(description: str) -> str:
    if " - " in description:
        return description.rsplit(" - ", 1)[-1].strip()
    return ""


def _parse_summary_rows(html: str) -> list[dict[str, Any]]:
    """Parse order list rows from the POST response.

    The table normally has 5 columns but web_show_bill=y can add extras.
    We scan every row for a cell matching the order-ID pattern rather than
    requiring a fixed column count.
    """
    soup = BeautifulSoup(html, "html.parser")
    now  = _now_utc()
    rows: list[dict[str, Any]] = []

    all_trs = soup.find_all("tr")
    LOGGER.info("Phase 1 parse: %d <tr> elements in response", len(all_trs))

    cell_count_sample: dict[int, int] = {}
    for tr in all_trs:
        n = len(tr.find_all(["td", "th"], recursive=False))
        cell_count_sample[n] = cell_count_sample.get(n, 0) + 1
    LOGGER.info("Phase 1 parse: cell-count distribution: %s", cell_count_sample)

    for tr in all_trs:
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) < 4:
            continue
        texts = [c.get_text(" ", strip=True) for c in cells]

        # Find which cell contains the order ID
        oid_idx = next(
            (i for i, t in enumerate(texts) if _ORDER_ID_RE.match(t.split()[0] if t else "")),
            None,
        )
        if oid_idx is None:
            continue

        order_id = texts[oid_idx].split()[0]

        # Column layout: date/days is before order_id; customer, desc, assigned follow
        col0 = texts[oid_idx - 1] if oid_idx > 0 else ""
        col2 = texts[oid_idx + 1] if oid_idx + 1 < len(texts) else ""
        col3 = texts[oid_idx + 2] if oid_idx + 2 < len(texts) else ""
        col4 = texts[oid_idx + 3] if oid_idx + 3 < len(texts) else ""

        if _DATE_RE.match(col0):
            row_type     = "dispatch"
            install_date: str | None = col0
        elif _DAYS_RE.match(col0):
            row_type     = "task"
            install_date = None
        else:
            row_type     = "task"
            install_date = None

        link = cells[oid_idx].find("a")
        detail_url = _resolve(link["href"], ORDERS_URL) if (link and link.get("href")) else ""
        # Don't let the age text ("NEW 240 days", "123 days") leak into assigned
        assigned   = (
            [] if (_DATE_RE.match(col4) or _DAYS_RE.match(col4) or
                   re.match(r"^(NEW|MACD|UCaaS)\s+\d", col4, re.IGNORECASE))
            else [u.strip() for u in col4.split() if u.strip()]
        )

        rows.append({
            "row_type":      row_type,
            "install_date":  install_date,
            "order_id":      order_id,
            "customer_name": col2,
            "description":   col3,
            "order_type":    _extract_order_type(col3),
            "location":      _extract_location(col3),
            "assigned":      assigned,
            "detail_url":    detail_url,
            "scraped_utc":   now,
        })

    LOGGER.info("Phase 1 parse: %d order rows found (%d dispatch, %d task)",
                len(rows),
                sum(1 for r in rows if r["row_type"] == "dispatch"),
                sum(1 for r in rows if r["row_type"] == "task"))
    return rows


# ── Phase 1b: extract DETABLE rich detail (inline, no extra HTTP calls) ────────


def _extract_detable(soup: BeautifulSoup, order_id: str) -> dict[str, Any]:
    """
    Pull rich data from the per-order DETABLE and update form that are
    already embedded in the orders page POST response.

    Extracted fields:
      last_modified   — web_tstamp_modified (e.g. "2026-05-04 11:48:03")
      bill_mrc        — web_bill_mrc_update (e.g. "191.82")
      bill_nrc        — web_bill_nrc_update (e.g. "-191.82")
      assigned_tech   — web_tech_update selected option
      log_count       — number of log entry IDs in the form
      last_log_entry  — text of the first div#log{ID} for this order
      contract_number — Download Contract {NUM} link text
      forecast_date   — BBNB FORECASTED DATE
      customer_email  — from mailto: link in DETABLE
      salesperson     — extracted from DETABLE text
      qty_term        — e.g. "QTY: 1, TERM: 61 months"
    """
    result: dict[str, Any] = {}

    # ── Update form (web_order_id = order_id) ──────────────────────────────────
    order_input = soup.find("input", {"name": "web_order_id", "value": order_id})
    if order_input:
        form = order_input.find_parent("form")
        if form:
            def _fv(name: str) -> str:
                el = form.find(["input", "textarea"], {"name": name})
                return (el.get("value", "") or el.get_text(strip=True) if el else "") or ""

            result["last_modified"]  = _fv("web_tstamp_modified")
            result["bill_mrc"]       = _fv("web_bill_mrc_update")
            result["bill_nrc"]       = _fv("web_bill_nrc_update")

            # Tech: selected option in web_tech_update
            tech_sel = form.find("select", {"name": "web_tech_update"})
            if tech_sel:
                opt = tech_sel.find("option", selected=True)
                if opt:
                    result["assigned_tech"] = opt.get("value", opt.get_text(strip=True))

            # Log count: radio inputs with numeric values
            log_radios = form.find_all("input", {"name": "order_web_log_row_id"})
            result["log_count"] = sum(
                1 for r in log_radios if (r.get("value") or "").isdigit()
            )

    # ── DETABLE table ──────────────────────────────────────────────────────────
    detable = soup.find("table", id=f"DETABLE{order_id}")
    if detable:
        text = detable.get_text(" ", strip=True)

        m = _CONTRACT_RE.search(text)
        if m:
            result["contract_number"] = m.group(1)

        for pat in (_BBNB_DATE_RE, _BBNB_FORE_RE):
            m = pat.search(text)
            if m:
                result["forecast_date"] = m.group(1)
                break

        m = _QTY_TERM_RE.search(text)
        if m:
            result["qty_term"] = f"QTY:{m.group(1)} TERM:{m.group(2).strip()}"

        m = _SALESPERSON_RE.search(text)
        if m:
            result["salesperson"] = m.group(1)

        # Customer email from first non-CC mailto link
        for a in detable.find_all("a", href=_MAILTO_RE):
            raw = a["href"].replace("mailto:", "").split("?")[0].split(",")[0].strip()
            if raw and "@" in raw:
                result["customer_email"] = raw
                break

    # ── div#log{ID} entries associated with this order ─────────────────────────
    # Log divs for this order are listed in the form's radio buttons
    if order_input:
        form = order_input.find_parent("form")
        if form:
            first_log_id = next(
                (
                    r.get("value")
                    for r in form.find_all("input", {"name": "order_web_log_row_id"})
                    if (r.get("value") or "").isdigit()
                ),
                None,
            )
            if first_log_id:
                log_div = soup.find("div", id=f"log{first_log_id}")
                if log_div:
                    result["last_log_entry"] = log_div.get_text(" ", strip=True)[:500]

    return result


def _parse_orders_html(html: str) -> list[dict[str, Any]]:
    """
    Full Phase 1 parse: summary rows + inline DETABLE enrichment for each order.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = _parse_summary_rows(html)

    for row in rows:
        oid   = row["order_id"]
        extra = _extract_detable(soup, oid)
        row.update(extra)

    return rows


def _fetch_orders_with_session(session: requests.Session, pm: str) -> list[dict[str, Any]]:
    """GET session init → POST filter → full parse."""
    LOGGER.info("Phase 1: GET %s (session init)", ORDERS_URL)
    get_resp = session.get(ORDERS_URL, timeout=20, allow_redirects=True)
    get_resp.raise_for_status()
    if "login" in get_resp.url.lower():
        raise PermissionError("401 Unauthorized — check ORDERS_123NET_USERNAME / PASSWORD")

    payload = {
        "web_show_bill":       "y",
        "web_search_order_id": "",
        "web_request_type":    "",
        "web_fac_type":        "",
        "web_bucket":          "",
        "web_pm":              "",
        "web_netopsengineer":  pm,
        "web_tech":            "",
        "web_cft":             "",
        "web_calendar":        "",
        "web_order_type":      "",
        "web_status":          "",
        "web_company_type":    "",
        "web_priority":        "",
        "web_exp":             "",
        "web_neteng":          "All",
        "web_core":            "All",
        "web_bill":            "All",
        "web_last_note":       "summary",
        "web_sort":            "standard",
    }
    LOGGER.info("Phase 1: POST %s (pm=%s)", ORDERS_URL, pm)
    post_resp = session.post(ORDERS_URL, data=payload, timeout=60)
    post_resp.raise_for_status()

    dbg = _debug_dir()
    (dbg / "orders_debug.html").write_bytes(post_resp.content)
    LOGGER.info("Phase 1: saved %d bytes → %s", len(post_resp.content), dbg / "orders_debug.html")

    return _parse_orders_html(post_resp.text)


def fetch_orders(pm: str | None = None) -> list[dict[str, Any]]:
    """Backward-compatible: Phase 1 only (summary rows + inline DETABLE)."""
    session = _build_session()
    if not pm:
        pm = os.environ.get("ORDERS_123NET_PM", os.environ.get("ORDERS_123NET_USERNAME", "")).strip()
    return _fetch_orders_with_session(session, pm)


# ── Phase 2: account_edit.cgi (per order, ID-based, concurrent) ───────────────


def _parse_account_page(html: str, source_url: str) -> dict[str, Any]:
    """
    Parse account_edit.cgi using known element IDs.
    Discovered IDs: #company_name, #handle, #address_1, #address_2,
    #city, #state_providence, #postal_code, #past_due, #account_balance, #net_terms, etc.
    """
    soup   = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    # Input/select fields
    for elem_id, field in _ACCOUNT_ID_MAP.items():
        el = soup.find(id=elem_id)
        if not el:
            continue
        if el.name == "select":
            opt = el.find("option", selected=True)
            val = opt.get_text(strip=True) if opt else ""
        else:
            val = (el.get("value") or el.get_text(strip=True) or "").strip()
        if val:
            result[field] = val

    # Div/span text fields
    for elem_id, field in _ACCOUNT_DIV_MAP.items():
        el = soup.find(id=elem_id)
        if el:
            val = el.get_text(strip=True)
            if val:
                result[field] = val

    if result:
        result["account_scraped_utc"] = _now_utc()
        result["_source_url"]         = source_url

    return result


_JSON_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _fetch_account_for_order(
    session: requests.Session,
    order: dict[str, Any],
    rate_limit: float = 0.25,
) -> dict[str, Any]:
    """
    Phase 2: enrich one order with account data from two JSON endpoints.

    Handle = first 3 chars of order_id (e.g. CTR-68128AFA → CTR).

    json/contracts.cgi      POST company_handle=HANDLE
        → pon, ckt_id, contract_bill_start, contract_mrc, contract_term_end
    json/resources_json.cgi POST term=HANDLE
        → sip_trunk, sip_trunk_billby
    """
    order_id = order.get("order_id", "")
    handle: str | None = order_id[:3].upper() if order_id else None

    if not handle:
        return {}

    result: dict[str, Any] = {}
    time.sleep(rate_limit)

    # ── contracts.cgi → PON / CKT_ID / billing ─────────────────────────────
    try:
        resp = session.post(
            _ADMIN_BASE + "json/contracts.cgi",
            data={"company_handle": handle},
            headers=_JSON_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json() if resp.content.strip() else None
        if raw is not None:
            contracts = (raw.get("data") or []) if isinstance(raw, dict) else (raw or [])
            # Prefer the contract whose web_order_id matches this order
            matching = [c for c in contracts if c.get("web_order_id") == order_id]
            best = (matching or contracts)
            if best:
                c = best[0]
                result["pon"]                 = c.get("pon") or None
                result["ckt_id"]              = c.get("ckt_id") or None
                result["contract_bill_start"] = c.get("bill_start_date") or None
                result["contract_mrc"]        = c.get("mrc") or None
                result["contract_term_end"]   = c.get("term_end") or None
            if contracts:
                result["account_contracts_json"] = json.dumps(contracts, default=str)
        LOGGER.debug("Phase 2: order=%s contracts → pon=%s ckt=%s",
                     order_id, result.get("pon"), result.get("ckt_id"))
    except Exception as exc:
        LOGGER.warning("Phase 2: contracts.cgi order=%s handle=%s err=%s", order_id, handle, exc)

    time.sleep(rate_limit)

    # ── resources_json.cgi → SIP trunk group ───────────────────────────────
    try:
        resp2 = session.post(
            _ADMIN_BASE + "json/resources_json.cgi",
            data={"term": handle},
            headers=_JSON_HEADERS,
            timeout=15,
        )
        resp2.raise_for_status()
        raw2 = resp2.json() if resp2.content.strip() else None
        if raw2 is not None:
            resources = (raw2.get("data") or []) if isinstance(raw2, dict) else (raw2 or [])
            sip = next(
                (r for r in resources
                 if "SIP" in (r.get("description", "") or "").upper()
                 or (r.get("TOS", "") or "").upper() == "SIP"),
                None,
            )
            if sip:
                result["sip_trunk"]        = sip.get("description") or None
                result["sip_trunk_billby"] = sip.get("bill_by") or None
        LOGGER.debug("Phase 2: order=%s sip_trunk=%s", order_id, result.get("sip_trunk"))
    except Exception as exc:
        LOGGER.warning("Phase 2: resources_json.cgi order=%s handle=%s err=%s", order_id, handle, exc)

    if result:
        result["account_handle"]      = handle
        result["account_scraped_utc"] = _now_utc()

    return result


# ── Phase 3: dispatch.cgi (Man-Hour Summary + weekly hosted calendar) ──────────


def _parse_manhour_csv(html: str) -> list[dict[str, Any]]:
    """
    Parse the Man-Hour Summary CSV from the <center> tag of dispatch.cgi.

    Format (CSV inside <center> tag, mixed with calendar labels):
      PM,Order ID,Bill Date, Closed Date, Bill MRC
      akennedy,GTM-69164D1F,2026-04-29,2026-05-04,130.00
      ...
    """
    soup   = BeautifulSoup(html, "html.parser")
    center = soup.find("center")
    if not center:
        return []

    now     = _now_utc()
    records: list[dict[str, Any]] = []
    in_data = False

    for line in center.get_text("\n").splitlines():
        line = line.strip()
        if not line:
            continue
        if "PM,Order ID" in line:
            in_data = True
            continue
        if not in_data:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5 and _ORDER_ID_RE.match(parts[1]):
            records.append({
                "order_id":             parts[1],
                "dispatch_pm":          parts[0],
                "dispatch_bill_date":   parts[2],
                "dispatch_closed_date": parts[3],
                "dispatch_bill_mrc":    parts[4],
                "dispatch_scraped_utc": now,
            })

    return records


def _parse_calendar_html(html: str) -> list[dict[str, Any]]:
    """
    Parse the weekly calendar view returned when web_calendar + web_week are set.

    Table columns (10 cells per data row):
      0: Calendar (type + MRC + contract date)
      1: Scheduled (date + day number + street)
      2: People Involved (names + CFT rating)
      3: OrderID + description
      4: Bandwidth
      5: Dispatch Info
      6: Call Ahead Info
      7: ManHours
      8: CORE status
      9: CPE status
    """
    soup    = BeautifulSoup(html, "html.parser")
    now     = _now_utc()
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) != 10:
            continue
        texts = [c.get_text(" ", strip=True) for c in cells]

        # Skip header row
        if texts[0].lower().startswith("calendar") or texts[3].lower().startswith("orderid"):
            continue

        # OrderID is the first token of cell[3]
        order_token = (texts[3].split()[0] if texts[3].strip() else "")
        if not _ORDER_ID_RE.match(order_token) or order_token in seen:
            continue
        seen.add(order_token)

        # People Involved: space-separated names before "CFT"
        people: list[str] = []
        for word in texts[2].split():
            if word.upper() == "CFT":
                break
            if word:
                people.append(word)

        # Scheduled date: first token of cell[1] (format: YYYY-MM-DD - DAY N Weekday ...)
        sched_tokens = texts[1].split()
        sched_date = sched_tokens[0] if sched_tokens and _DATE_RE.match(sched_tokens[0]) else None

        records.append({
            "order_id":                  order_token,
            "dispatch_date":             sched_date,
            "dispatch_tech":             ", ".join(people) if people else None,
            "dispatch_calendar_context": texts[0][:120],
            "dispatch_notes":            texts[5][:300] if texts[5] else None,
            "dispatch_status":           texts[8] if texts[8] else None,
            "dispatch_scraped_utc":      now,
        })

    return records


def fetch_dispatch_data(session: requests.Session) -> list[dict[str, Any]]:
    """
    Phase 3: fetch dispatch.cgi.

    Step 1 — GET the bare page to parse Man-Hour Summary CSV.
    Step 2 — POST with hosted calendar + current week to get the weekly schedule.
    Both results are merged by order_id.
    """
    LOGGER.info("Phase 3: GET %s (man-hour summary)", DISPATCH_URL)
    get_resp = session.get(DISPATCH_URL, timeout=20, allow_redirects=True)
    get_resp.raise_for_status()

    dbg = _debug_dir()
    (dbg / "dispatch_get_debug.html").write_bytes(get_resp.content)

    manhour  = _parse_manhour_csv(get_resp.text)
    LOGGER.info("Phase 3: man-hour summary → %d closed order records", len(manhour))

    # Discover available weeks from the form
    soup      = BeautifulSoup(get_resp.text, "html.parser")
    week_sel  = soup.find("select", {"name": "web_week"})
    weeks     = []
    if week_sel:
        weeks = [o.get("value", o.get_text(strip=True)) for o in week_sel.find_all("option")]
        # Use current week (second option after "summary")
        calendar_weeks = [w for w in weeks if _DATE_RE.match(w)]

    cal_records: list[dict[str, Any]] = []
    if calendar_weeks:
        # Fetch the next 6 weeks (current + 5 upcoming) to capture upcoming installs
        weeks_to_fetch = calendar_weeks[:6]
        LOGGER.info("Phase 3: fetching calendar for %d weeks: %s", len(weeks_to_fetch), weeks_to_fetch)
        for wi, week in enumerate(weeks_to_fetch):
            payload = {
                "web_calendar": _HOSTED_CALENDAR,
                "web_week":     week,
            }
            try:
                post_resp = session.post(DISPATCH_URL, data=payload, timeout=30)
                post_resp.raise_for_status()
                if wi == 0:
                    (dbg / "dispatch_post_debug.html").write_bytes(post_resp.content)
                week_records = _parse_calendar_html(post_resp.text)
                LOGGER.info("Phase 3: week %s → %d records", week, len(week_records))
                cal_records.extend(week_records)
                time.sleep(0.3)
            except Exception as exc:
                LOGGER.warning("Phase 3: calendar POST week=%s failed: %s", week, exc)

    # Merge: man-hour is authoritative for order_id, calendar adds context
    merged: dict[str, dict[str, Any]] = {r["order_id"]: r for r in manhour}
    for rec in cal_records:
        oid = rec["order_id"]
        if oid in merged:
            for k, v in rec.items():
                if k not in merged[oid]:
                    merged[oid][k] = v
        else:
            merged[oid] = rec

    return list(merged.values())


# ── Orchestrator ───────────────────────────────────────────────────────────────


def fetch_all_enriched(pm: str | None = None) -> list[dict[str, Any]]:
    """
    Full three-phase scrape. Returns enriched dispatch-type order records.

    Phase 1: orders_web_admin.cgi — full inline parse (summary + DETABLE)
    Phase 2: account_edit.cgi     — per-order account detail (concurrent)
    Phase 3: dispatch.cgi         — man-hour summary + weekly calendar

    Controls:
      ORDERS_PHASE2=0   skip account_edit phase
      ORDERS_PHASE3=0   skip dispatch phase
      ORDERS_WORKERS=N  concurrent workers for Phase 2 (default 4, max 10)
    """
    session = _build_session()
    if not pm:
        pm = os.environ.get("ORDERS_123NET_PM", os.environ.get("ORDERS_123NET_USERNAME", "")).strip()
    if not pm:
        raise RuntimeError("Set ORDERS_123NET_PM or ORDERS_123NET_USERNAME env var.")

    run_phase2 = os.environ.get("ORDERS_PHASE2", "1").strip() != "0"
    run_phase3 = os.environ.get("ORDERS_PHASE3", "1").strip() != "0"
    workers    = max(1, min(int(os.environ.get("ORDERS_WORKERS", "4")), 10))

    # ── Phase 1 ──────────────────────────────────────────────────────────────
    LOGGER.info("=== Phase 1: orders list + inline DETABLE (pm=%s) ===", pm)
    all_rows      = _fetch_orders_with_session(session, pm)
    dispatch_rows = [r for r in all_rows if r.get("row_type") == "dispatch"]
    LOGGER.info(
        "Phase 1 done: %d total rows (%d dispatch, %d task), %d with MRC data, %d with logs",
        len(all_rows),
        len(dispatch_rows),
        len(all_rows) - len(dispatch_rows),
        sum(1 for r in all_rows if r.get("bill_mrc")),
        sum(1 for r in all_rows if r.get("log_count", 0) > 0),
    )

    # Include all rows (task + dispatch) — Phase 3 will supply install dates for
    # orders that show as "N days" in the Phase 1 engineer view.
    enriched: dict[str, dict[str, Any]] = {r["order_id"]: dict(r) for r in all_rows}

    # ── Phase 2: Account detail (concurrent) ─────────────────────────────────
    if run_phase2 and all_rows:
        LOGGER.info("=== Phase 2: account detail (%d orders, %d workers) ===", len(all_rows), workers)
        done = 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="acct") as pool:
            futures = {
                pool.submit(_fetch_account_for_order, session, row): row["order_id"]
                for row in all_rows
            }
            for future in as_completed(futures):
                oid = futures[future]
                try:
                    acct = future.result()
                    if acct:
                        # Don't overwrite Phase 1 data with account data
                        for k, v in acct.items():
                            if k not in enriched[oid] or not enriched[oid][k]:
                                enriched[oid][k] = v
                except Exception as exc:
                    LOGGER.warning("Phase 2 error order=%s: %s", oid, exc)
                done += 1
                if done % 5 == 0:
                    LOGGER.info("Phase 2: %d/%d accounts fetched", done, len(all_rows))
        LOGGER.info("Phase 2 done: %d accounts processed", done)
    elif not run_phase2:
        LOGGER.info("Phase 2: skipped (ORDERS_PHASE2=0)")

    # ── Phase 3: Dispatch man-hour summary + calendar ─────────────────────────
    if run_phase3:
        LOGGER.info("=== Phase 3: dispatch man-hour summary + calendar ===")
        try:
            dispatch_records = fetch_dispatch_data(session)
            matched = 0
            for drec in dispatch_records:
                oid = drec.get("order_id", "")
                if not oid:
                    continue
                if oid in enriched:
                    for k, v in drec.items():
                        if k not in ("order_id", "row_type") and not enriched[oid].get(k):
                            enriched[oid][k] = v
                    matched += 1
                else:
                    # Closed order not in Phase 1 listing (already dispatched)
                    enriched[oid] = {
                        **drec,
                        "row_type":    "dispatch",
                        "scraped_utc": drec.get("dispatch_scraped_utc", _now_utc()),
                    }
            LOGGER.info(
                "Phase 3 done: %d dispatch records, %d matched to Phase 1",
                len(dispatch_records), matched,
            )
        except Exception as exc:
            LOGGER.warning("Phase 3 failed (non-fatal): %s", exc)
    else:
        LOGGER.info("Phase 3: skipped (ORDERS_PHASE3=0)")

    # Drop task-only rows that Phase 3 never matched — they have no date
    # and would show up in the UI with blank install/dispatch dates.
    # Dispatch-type Phase 1 rows always have install_date; task rows that
    # appeared in the Phase 3 calendar have dispatch_date or dispatch_bill_date.
    pre_filter = len(enriched)
    result = [
        r for r in enriched.values()
        if r.get("install_date") or r.get("dispatch_date") or r.get("dispatch_bill_date")
    ]
    dropped = pre_filter - len(result)
    if dropped:
        LOGGER.info("Dropped %d task-only rows with no date (not yet scheduled)", dropped)
    LOGGER.info("=== Total enriched orders: %d ===", len(result))
    return result


# ── Ingest ─────────────────────────────────────────────────────────────────────


def ingest_orders(records: list[dict[str, Any]]) -> int:
    """Push records to the ticket API (local SQLite or remote via CLIENT_MODE=1)."""
    if not records:
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    now         = _now_utc()
    client_mode = os.environ.get("CLIENT_MODE", "").strip() == "1"

    if client_mode:
        from webscraper.ticket_api import db_client as db_mod  # type: ignore[import]
        db_path = ""
    else:
        from webscraper.ticket_api import db as db_mod  # type: ignore[import]
        db_path = str(Path(__file__).resolve().parents[1] / "var" / "db" / "tickets.sqlite")

    if not client_mode:
        db_mod.ensure_indexes(db_path)

    return db_mod.upsert_orders(db_path, records, now)


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    pm = os.environ.get("ORDERS_123NET_PM", os.environ.get("ORDERS_123NET_USERNAME", "")).strip()
    if not pm:
        print("Set ORDERS_123NET_USERNAME env var.", file=sys.stderr)
        sys.exit(1)

    enriched = fetch_all_enriched(pm=pm)
    n        = ingest_orders(enriched)
    LOGGER.info("Ingested %d enriched order records", n)

    out = _debug_dir() / "orders.json"
    out.write_text(json.dumps(enriched, indent=2, default=str), encoding="utf-8")
    LOGGER.info("Wrote %s", out)


if __name__ == "__main__":
    main()
