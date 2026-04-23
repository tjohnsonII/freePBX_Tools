from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlencode


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

        # Paginate through all DataTables pages (100 rows each, no "Show All" option)
        all_records: dict[str, dict[str, str]] = {}
        page_num = 1
        while True:
            page_records = _parse_vpbx_page_source(driver.page_source)
            for r in page_records:
                all_records[r["handle"]] = r
            _emit(f"page={page_num} this_page={len(page_records)} total={len(all_records)}")

            # Check for a non-disabled Next button (id="vpbx_list_next")
            next_btns = driver.find_elements(By.ID, "vpbx_list_next")
            if not next_btns:
                break
            classes = next_btns[0].get_attribute("class") or ""
            if "disabled" in classes or "ui-state-disabled" in classes:
                break

            # Capture first row text to detect page change
            first_row_text = ""
            rows = driver.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr")
            if rows:
                first_row_text = rows[0].text

            next_btn = next_btns[0]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(0.3)
            try:
                next_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_btn)

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: (
                        d.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr") and
                        d.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr")[0].text != first_row_text
                    )
                )
            except Exception:
                time.sleep(1.5)

            page_num += 1

    finally:
        driver.quit()

    records = list(all_records.values())
    _emit(f"parsed_records count={len(records)}")
    return records
