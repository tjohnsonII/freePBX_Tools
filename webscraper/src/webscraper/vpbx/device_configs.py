"""VPBX credential scraper.

Visits each vpbx_detail page on secure.123.net and extracts FTP/REST
credentials stored in the form fields (ftp_pass, ftp_host, ftp_user, rest_pass).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _vpbx_cgi_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/cgi-bin/web_interface/admin/vpbx.cgi"


def _extract_vpbx_detail_form_fields(page_source: str) -> dict[str, str]:
    """Parse a vpbx_detail page and return credential form field values.

    Looks for input/select elements with names matching ftp_pass, ftp_host,
    ftp_user, rest_pass (and common variants).  Returns a dict of whatever
    was found; missing fields are absent from the dict.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    result: dict[str, str] = {}

    _FIELD_MAP = {
        # canonical name → list of possible input name= values to try
        "ftp_pass":  ["ftp_pass", "ftppass", "ftp_password", "ftppassword"],
        "ftp_host":  ["ftp_host", "ftphost", "ftp_server", "ftpserver"],
        "ftp_user":  ["ftp_user", "ftpuser", "ftp_username", "ftpusername"],
        "rest_pass": ["rest_pass", "restpass", "rest_password", "admin_pass", "adminpass"],
    }

    for canonical, candidates in _FIELD_MAP.items():
        for name in candidates:
            tag = soup.find("input", {"name": name}) or soup.find("select", {"name": name})
            if tag:
                val = tag.get("value", "")
                if not val and tag.name == "select":
                    selected = tag.find("option", selected=True)
                    val = selected.get("value", "") if selected else ""
                if val:
                    result[canonical] = str(val).strip()
                    break

    return result


def _parse_vpbx_ids(page_source: str, base_url: str) -> list[dict[str, str]]:
    """Scan a vpbx.cgi list page for links to vpbx_detail pages."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    results: list[dict[str, str]] = []

    for table in soup.find_all("table"):
        if not table.find("a", href=lambda h: h and "command=vpbx_detail" in h):
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            detail_link = None
            for a in row.find_all("a", href=True):
                if "command=vpbx_detail" in a["href"]:
                    detail_link = a
                    break
            if not detail_link:
                continue
            params = parse_qs(urlparse(detail_link["href"]).query)
            vpbx_id = (params.get("vpbx_id") or params.get("id") or [""])[0]
            if not vpbx_id:
                continue
            handle = ""
            for cell in cells:
                txt = cell.get_text(strip=True)
                if txt and txt != detail_link.get_text(strip=True):
                    handle = txt
                    break
            if not handle:
                handle = detail_link.get_text(strip=True)
            full_url = urljoin(_vpbx_cgi_url(base_url), detail_link["href"])
            results.append({"vpbx_id": vpbx_id, "handle": handle.upper(), "detail_url": full_url})
    return results


def _collect_all_vpbx_ids_by_paging(
    driver: Any, base_url: str, emit_fn: Any = None
) -> list[dict[str, str]]:
    """Walk DataTables pages on vpbx.cgi and return all handle entries."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    all_entries: dict[str, dict[str, str]] = {}
    page_num = 1

    while True:
        entries = _parse_vpbx_ids(driver.page_source, base_url)
        for e in entries:
            all_entries[e["vpbx_id"]] = e
        _emit(f"scanning page {page_num} — {len(all_entries)} handles found so far")

        try:
            next_btn = driver.find_element(By.ID, "vpbx_list_next")
            if "ui-state-disabled" in (next_btn.get_attribute("class") or ""):
                break
            next_btn.click()
            page_num += 1
            WebDriverWait(driver, 10).until(
                EC.staleness_of(driver.find_element(By.CSS_SELECTOR, "table tr:last-child"))
            )
            import time
            time.sleep(0.5)
        except Exception:
            break

    return list(all_entries.values())


def fetch_vpbx_credentials(
    base_url: str,
    *,
    handles: list[str] | None = None,
    on_handle_done: Any = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Scrape FTP/REST credentials from each vpbx_detail page.

    Visits vpbx.cgi, waits for SSO login, then for each handle navigates to
    its vpbx_detail page and extracts form field values for ftp_pass, ftp_host,
    ftp_user, and rest_pass.

    Args:
        handles:               If given, only scrape these handles (uppercase).
        on_handle_done:        Callback(handle, cred_dict) called after each page.
        login_timeout_seconds: Seconds to wait for the user to complete SSO.
        emit_fn:               Callable(str) for progress messages.

    Returns:
        List of dicts with keys: handle, vpbx_id, ftp_pass, ftp_host, ftp_user,
        rest_pass, scraped_utc.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    import time

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    target_url = _vpbx_cgi_url(base_url)
    handle_filter = {h.upper() for h in handles} if handles else None

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    all_records: list[dict[str, str]] = []

    try:
        driver.get(target_url)
        _emit("waiting_for_login")

        # Wait until the user has logged in and the vpbx list table appears
        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        vpbx_list = _collect_all_vpbx_ids_by_paging(driver, base_url, emit_fn=_emit)
        _emit(f"found {len(vpbx_list)} handles on vpbx.cgi")

        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered to {len(vpbx_list)} handle(s)")

        for idx, entry in enumerate(vpbx_list, 1):
            handle    = entry["handle"]
            vpbx_id   = entry["vpbx_id"]
            detail_url = entry["detail_url"]
            _emit(f"[{idx}/{len(vpbx_list)}] {handle} — loading detail page")

            try:
                driver.get(detail_url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "form"))
                )
                time.sleep(0.4)

                fields = _extract_vpbx_detail_form_fields(driver.page_source)
                ftp_pass = fields.get("ftp_pass", "")

                if not ftp_pass:
                    _emit(f"  {handle}: no ftp_pass found — skipping")
                    continue

                record = {
                    "handle":       handle,
                    "vpbx_id":      vpbx_id,
                    "ftp_pass":     ftp_pass,
                    "ftp_host":     fields.get("ftp_host", ""),
                    "ftp_user":     fields.get("ftp_user", ""),
                    "rest_pass":    fields.get("rest_pass", ""),
                    "scraped_utc":  _iso_now(),
                }
                all_records.append(record)
                _emit(f"  {handle}: ftp_pass captured ({len(ftp_pass)} chars)")

                if on_handle_done:
                    on_handle_done(handle, record)

            except Exception as exc:
                _emit(f"  {handle}: error — {exc}")
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    _emit(f"credentials_done total={len(all_records)}")
    return all_records
