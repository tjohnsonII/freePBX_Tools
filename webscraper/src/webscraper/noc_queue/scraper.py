from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


NOC_BASE_URL = "https://noc-tickets.123.net"
LOCAL_NOC_URL = "http://10.123.203.1/"

# Views served via SSO on noc-tickets.123.net
SSO_VIEWS: list[dict[str, str]] = [
    {"key": "hosted", "url": f"{NOC_BASE_URL}/view/hosted", "label": "Hosted"},
    {"key": "noc",    "url": f"{NOC_BASE_URL}/view_noc",    "label": "NOC"},
    {"key": "all",    "url": f"{NOC_BASE_URL}/view_all",    "label": "All"},
]

# Canonical column name aliases — includes known DataTables column names from noc-tickets.123.net
_HEADER_ALIASES: dict[str, str] = {
    # ticket id variants
    "ticket id": "ticket_id",
    "ticket": "ticket_id",
    "id": "ticket_id",
    "caseid": "ticket_id",
    "case id": "ticket_id",
    "incident id": "ticket_id",
    "#": "ticket_id",
    # subject/title
    "subject": "subject",
    "title": "subject",
    "summary": "subject",
    # status
    "status": "status",
    "ticket status": "status",
    "state": "status",
    # opened/created
    "opened": "opened",
    "created": "opened",
    "date": "opened",
    "created date": "opened",
    # last update
    "last update": "last_update",
    "last updated": "last_update",
    "updated": "last_update",
    "modified": "last_update",
    # customer/company
    "customer": "customer",
    "account": "customer",
    "client": "customer",
    "company": "customer",
    "handle": "customer",
    # priority
    "priority": "priority",
    # assigned tech
    "assigned": "assigned_to",
    "assigned to": "assigned_to",
    "owner": "assigned_to",
    "tech": "assigned_to",
    # ticket type
    "type": "ticket_type",
    "category": "ticket_type",
    # DataTables-specific columns on noc-tickets.123.net /view_all
    "external id": "external_id",
    "external": "external_id",
    "days": "days_open",
    "age": "days_open",
    "cft": "cft",
    "dispatch": "dispatch",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_header(raw: str) -> str:
    key = " ".join(raw.strip().lower().split())
    return _HEADER_ALIASES.get(key, key.replace(" ", "_"))


def _parse_queue_table(page_source: str, view_key: str, base_url: str = NOC_BASE_URL) -> list[dict[str, Any]]:
    """Parse the best-matching ticket table from a queue page's HTML source.

    Works for both noc-tickets.123.net (DataTables, SSO) and 10.123.203.1
    (Sphinx/Manticore search UI, form auth). The page_source is captured by
    Selenium after all JavaScript has rendered.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    now = _iso_now()

    score_keywords = (
        "ticket", "id", "subject", "status", "customer", "company",
        "tech", "dispatch", "cft", "days", "open",
    )

    best_table = None
    best_score = 0
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        score = sum(1 for h in headers if any(k in h for k in score_keywords))
        if score > best_score:
            best_score = score
            best_table = table

    if best_table is None or best_score == 0:
        return []

    headers = [_normalize_header(th.get_text(" ", strip=True)) for th in best_table.find_all("th")]
    rows: list[dict[str, Any]] = []

    for tr in best_table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        values = [td.get_text(" ", strip=True) for td in cells]

        # Capture href links (e.g. ticket_id_url); make relative URLs absolute
        href_map: dict[str, str] = {}
        for td, col in zip(cells, headers):
            link = td.find("a")
            if link and link.get("href"):
                href = link["href"]
                if href.startswith("/"):
                    href = base_url.rstrip("/") + href
                href_map[col + "_url"] = href

        payload: dict[str, Any] = {
            headers[i]: values[i]
            for i in range(min(len(headers), len(values)))
        }
        payload.update(href_map)
        payload["view"] = view_key
        payload["last_seen_utc"] = now
        payload["raw_json"] = json.dumps(payload, sort_keys=True)

        rows.append(payload)

    return rows


def _wait_for_data_rows(driver: Any, timeout: int = 30) -> bool:
    """Wait until the ticket table has actual data rows rendered in the DOM.

    noc-tickets.123.net uses DataTables which renders the <table> element immediately
    but populates <tbody> rows asynchronously via AJAX. Waiting on <table> presence
    alone captures the empty skeleton — we need rows with real content.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    def has_data_rows(d: Any) -> bool:
        cells = d.find_elements(By.CSS_SELECTOR, "table tbody tr td")
        return any(c.text.strip() for c in cells)

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(has_data_rows)
        return True
    except Exception:
        return False


def _form_login(driver: Any, username: str, password: str, emit_fn: Any = None) -> bool:
    """Attempt to fill and submit a standard username/password login form.

    Tries common input name/id patterns used by web UIs. Returns True if a
    form was found and submitted, False if no login form was detected.
    """
    from selenium.webdriver.common.by import By

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    user_selectors = [
        "input[name='username']", "input[name='user']", "input[name='login']",
        "input[id='username']", "input[id='user']",
        "input[type='text']",
    ]
    pass_selectors = [
        "input[name='password']", "input[name='pass']",
        "input[id='password']", "input[id='pass']",
        "input[type='password']",
    ]

    user_el = None
    for sel in user_selectors:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            user_el = els[0]
            break

    pass_el = None
    for sel in pass_selectors:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            pass_el = els[0]
            break

    if not user_el or not pass_el:
        _emit("no_login_form_detected")
        return False

    user_el.clear()
    user_el.send_keys(username)
    pass_el.clear()
    pass_el.send_keys(password)

    # Submit: prefer an explicit submit button, fall back to form submit
    submit_els = driver.find_elements(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], button")
    if submit_els:
        submit_els[0].click()
    else:
        pass_el.submit()

    _emit("login_form_submitted")
    return True


def fetch_local_noc(
    *,
    page_load_timeout: int = 20,
    emit_fn: Any = None,
) -> list[dict[str, Any]]:
    """Scrape the local NOC UI using form-based auth.

    This site runs a Sphinx/Manticore search UI with different page structure
    from noc-tickets.123.net. It requires its own Selenium session and login flow,
    separate from the SSO session used for the main NOC ticket views.
    """
    import time

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    VIEW_KEY = "local"

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    username = os.environ.get("LOCAL_NOC_USERNAME")
    password = os.environ.get("LOCAL_NOC_PASSWORD")  # pragma: allowlist secret

    if not username or not password:
        _emit("local_noc_credentials_missing")
        return []

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(LOCAL_NOC_URL)
        _emit("local_noc_loaded")

        # Give the page a moment to render the login form (if any)
        time.sleep(2)

        # Attempt form login if a login form is present
        logged_in = _form_login(driver, username, password, emit_fn=emit_fn)
        if logged_in:
            # Wait for page to transition away from the login form
            try:
                WebDriverWait(driver, page_load_timeout, poll_frequency=0.5).until(
                    lambda d: not d.find_elements(By.CSS_SELECTOR, "input[type='password']")
                    or len(d.find_elements(By.TAG_NAME, "table")) > 0
                )
            except Exception:
                pass

        # Wait for a table or any substantial content
        try:
            WebDriverWait(driver, page_load_timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
        except Exception:
            _emit("local_noc_no_table_found")
            return []

        _wait_for_data_rows(driver, timeout=10)

        records = _parse_queue_table(driver.page_source, VIEW_KEY, base_url=LOCAL_NOC_URL)
        _emit(f"local_noc_parsed count={len(records)}")
        return records

    finally:
        driver.quit()


def fetch_noc_queues(
    *,
    view_key: str | None = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, Any]]:
    """Scrape NOC queue views and return a combined list of ticket records.

    Pass view_key to scrape only one view (hosted | noc | all | local).
    Omit view_key to scrape all views.

    Two separate Selenium sessions are used:
      1. noc-tickets.123.net (SSO/Keycloak) — hosted, NOC, all queue views
      2. 10.123.203.1 (form auth, i123/sdxczvsdxczv) — local NOC view

    The customers.cgi scraper (secure.123.net) is entirely separate and unaffected.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    all_records: list[dict[str, Any]] = []

    # Determine which SSO views to scrape
    sso_views = [v for v in SSO_VIEWS if view_key is None or v["key"] == view_key]
    run_local = view_key is None or view_key == "local"

    # ── Session 1: noc-tickets.123.net (SSO) ─────────────────────────────────
    if sso_views:
        options = Options()
        options.add_argument("--start-maximized")
        driver = webdriver.Chrome(options=options)

        try:
            first_url = sso_views[0]["url"]
            driver.get(first_url)
            _emit("waiting_for_login")

            # Wait until SSO completes and a ticket table is visible
            WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
                lambda d: "noc-tickets.123.net" in (d.current_url or "")
                and len(d.find_elements(By.TAG_NAME, "table")) > 0
            )
            _emit("login_confirmed")

            for view in sso_views:
                _emit(f"scraping_view view={view['key']}")

                if driver.current_url.rstrip("/") != view["url"].rstrip("/"):
                    driver.get(view["url"])

                # DataTables renders rows async — wait for real data, not just <table>
                got_rows = _wait_for_data_rows(driver, timeout=30)
                if not got_rows:
                    _emit(f"no_data_rows view={view['key']}")

                records = _parse_queue_table(driver.page_source, view["key"])
                _emit(f"parsed view={view['key']} count={len(records)}")
                all_records.extend(records)

        finally:
            driver.quit()

    # ── Session 2: 10.123.203.1 (form auth) ──────────────────────────────────
    if run_local:
        _emit("starting_local_noc")
        try:
            local_records = fetch_local_noc(emit_fn=emit_fn)
            all_records.extend(local_records)
        except Exception as exc:
            _emit(f"local_noc_error: {exc}")

    return all_records
