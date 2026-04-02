from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_header(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    aliases = {
        "name": "name",
        "status": "account_status",
        "account status": "account_status",
        "web order": "web_order",
        "deployment id": "deployment_id",
        "switch": "switch",
        "devices": "devices",
        "ip": "ip",
        "handle": "handle",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _parse_vpbx_page_source(page_source: str) -> list[dict[str, str]]:
    """Parse the VPBX handles table from raw HTML source."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    table = None
    for candidate in soup.find_all("table"):
        headers = [_normalize_header(th.get_text(" ", strip=True)) for th in candidate.find_all("th")]
        if "handle" in headers:
            table = candidate
            break
    if table is None:
        raise RuntimeError("Unable to find VPBX handles table on vpbx.cgi")

    headers = [_normalize_header(th.get_text(" ", strip=True)) for th in table.find_all("th")]
    discovered: dict[str, dict[str, str]] = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells]
        payload = {headers[idx]: values[idx] for idx in range(min(len(headers), len(values)))}
        handle = (payload.get("handle") or "").strip()
        if not handle:
            continue
        discovered[handle] = {
            "handle": handle,
            "name": payload.get("name") or "",
            "account_status": payload.get("account_status") or payload.get("status") or "",
            "ip": payload.get("ip") or "",
            "web_order": payload.get("web_order") or "",
            "deployment_id": payload.get("deployment_id") or "",
            "switch": payload.get("switch") or "",
            "devices": payload.get("devices") or "",
            "last_seen_utc": _iso_now(),
        }
    return list(discovered.values())


def fetch_handles_selenium(
    base_url: str,
    *,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Open a visible Chrome window, wait for SSO auth, scrape vpbx.cgi, return records."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    target_url = urljoin(base_url.rstrip("/") + "/", "cgi-bin/web_interface/admin/vpbx.cgi")

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    try:
        _emit("launched_browser")
        driver.get(target_url)
        _emit("waiting_for_login")

        # Wait until SSO is done AND the real data table is loaded.
        # We check for a vpbx_detail link, which only appears once the handles
        # table has rendered — not just any layout table on the login page.
        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        # vpbx.cgi uses DataTables which defaults to showing a limited number of rows.
        # Use the DataTables JS API to set page length to -1 (show all) then wait for redraw.
        try:
            driver.execute_script(
                "try { $('table').DataTable().page.len(-1).draw(); } catch(e) {}"
            )
            time.sleep(2)  # wait for DataTables to re-render all rows
            _emit("datatables_expanded")
        except Exception:
            pass  # non-fatal — fall through and capture whatever is visible

        page_source = driver.page_source
        _emit("page_source_captured")
    finally:
        driver.quit()

    records = _parse_vpbx_page_source(page_source)
    _emit(f"parsed_records count={len(records)}")
    return records
