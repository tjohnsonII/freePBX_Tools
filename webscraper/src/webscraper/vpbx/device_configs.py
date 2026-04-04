from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _vpbx_cgi_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/cgi-bin/web_interface/admin/vpbx.cgi"


def _collect_all_vpbx_ids_by_paging(driver: Any, base_url: str, emit_fn: Any = None) -> list[dict[str, str]]:
    """Collect all vpbx_detail entries by clicking the DataTables Next button repeatedly.

    The vpbx.cgi table shows 100 rows per page with no "Show All" option.
    The Next button has id="vpbx_list_next" and gets class "ui-state-disabled"
    when there are no more pages.

    Accumulates parsed entries from every page and returns the full deduplicated list.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    all_entries: dict[str, dict[str, str]] = {}
    page_num = 1

    while True:
        # Parse current page
        entries = _parse_vpbx_ids(driver.page_source, base_url)
        for e in entries:
            all_entries[e["vpbx_id"]] = e
        _emit(f"scanning page {page_num} — {len(all_entries)} handles found so far")

        # Check if Next button exists and is not disabled
        try:
            next_btn = driver.find_element(By.ID, "vpbx_list_next")
        except Exception:
            # No Next button — single page table
            break

        classes = next_btn.get_attribute("class") or ""
        if "disabled" in classes or "ui-state-disabled" in classes:
            break

        # Click Next and wait for the table to re-render (row count changes)
        current_first_row_text = ""
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr")
            if rows:
                current_first_row_text = rows[0].text
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(0.3)
            try:
                next_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_btn)
        except Exception as exc:
            _emit(f"next_click_failed page={page_num} error={exc}")
            break

        # Wait for table to update — first row text changes
        try:
            WebDriverWait(driver, 10).until(
                lambda d: (
                    d.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr") and
                    d.find_elements(By.CSS_SELECTOR, "#vpbx_list tbody tr")[0].text != current_first_row_text
                )
            )
        except Exception:
            time.sleep(1.5)  # fallback wait

        page_num += 1

    _emit(f"found {len(all_entries)} handles across {page_num} page(s)")
    return list(all_entries.values())


def _parse_vpbx_ids(page_source: str, base_url: str) -> list[dict[str, str]]:
    """Scan the vpbx.cgi list page for links to vpbx_detail pages.

    Returns [{vpbx_id, handle, detail_url}, ...].
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    seen: set[str] = set()
    results: list[dict[str, str]] = []

    # Find the table that contains vpbx_detail links, then locate the "Handle" column index
    target_table = None
    handle_col_idx = 1  # fallback: column 1 is Handle in the standard vpbx.cgi layout
    for table in soup.find_all("table"):
        if not table.find("a", href=lambda h: h and "command=vpbx_detail" in h):
            continue
        target_table = table
        # Find the header row to determine which column is "Handle"
        for row in table.find_all("tr"):
            ths = row.find_all("th")
            if not ths:
                continue
            for idx, th in enumerate(ths):
                if "handle" in th.get_text(" ", strip=True).lower():
                    handle_col_idx = idx
                    break
            break
        break

    if target_table is None:
        return results

    for tr in target_table.find_all("tr"):
        # Find the vpbx_detail link in this row
        detail_link = None
        for a in tr.find_all("a", href=True):
            if "command=vpbx_detail" in a["href"]:
                detail_link = a
                break
        if not detail_link:
            continue

        params = parse_qs(urlparse(detail_link["href"]).query)
        vpbx_id = (params.get("id") or [None])[0]
        if not vpbx_id or vpbx_id in seen:
            continue
        seen.add(vpbx_id)

        cells = tr.find_all("td")
        if handle_col_idx < len(cells):
            handle = cells[handle_col_idx].get_text(" ", strip=True)
        else:
            handle = detail_link.get_text(strip=True)

        full_url = urljoin(_vpbx_cgi_url(base_url), detail_link["href"])
        results.append({"vpbx_id": vpbx_id, "handle": handle, "detail_url": full_url})

    return results


def _parse_device_rows(page_source: str, base_url: str, vpbx_id: str, handle: str) -> list[dict[str, str]]:
    """Scan a vpbx_detail page for device edit links and row metadata.

    Returns [{device_id, vpbx_id, handle, directory_name, extension, mac, make, model,
              site_code, edit_url}, ...].
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_source, "lxml")
    devices: list[dict[str, str]] = []
    seen_device_ids: set[str] = set()

    # Find the device table: look for the table that has edit_device links
    device_table = None
    for table in soup.find_all("table"):
        if table.find("a", href=lambda h: h and "command=edit_device" in h):
            device_table = table
            break

    if device_table is None:
        return []

    # Parse headers from <thead> or first <tr> with <th>
    headers: list[str] = []
    for row in device_table.find_all("tr"):
        ths = row.find_all("th")
        if ths:
            headers = [th.get_text(" ", strip=True).lower().strip() for th in ths]
            break

    def _col(cells: list, *names: str) -> str:
        for name in names:
            for idx, h in enumerate(headers):
                if name in h and idx < len(cells):
                    return cells[idx].get_text(" ", strip=True)
        return ""

    for tr in device_table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue

        # Find the edit link in this row
        edit_link = None
        for a in tr.find_all("a", href=True):
            if "command=edit_device" in a["href"]:
                edit_link = a
                break
        if not edit_link:
            continue

        params = parse_qs(urlparse(edit_link["href"]).query)
        device_id = (params.get("device_id") or [None])[0]
        if not device_id or device_id in seen_device_ids:
            continue
        seen_device_ids.add(device_id)

        edit_url = urljoin(_vpbx_cgi_url(base_url), edit_link["href"])

        devices.append({
            "device_id": device_id,
            "vpbx_id": vpbx_id,
            "handle": handle,
            "directory_name": _col(cells, "directoryname", "directory"),
            "extension": _col(cells, "cid-911cid", "cid", "extension"),
            "mac": _col(cells, "mac"),
            "make": _col(cells, "make"),
            "model": _col(cells, "model"),
            "site_code": _col(cells, "site code", "site"),
            "edit_url": edit_url,
            "bulk_config": "",
            "last_seen_utc": _iso_now(),
        })

    return devices


def _extract_bulk_config_from_html(html: str) -> str:
    """Parse the bulk attribute config out of an edit_device page without browser interaction.

    The edit_device form contains a hidden/visible textarea whose value is what the
    Bulk Attribute Edit modal shows. We try the most common names/ids first, then fall
    back to any textarea whose content looks like key=value config lines.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    # Try known textarea ids/names for the options field
    for sel in [
        "textarea[name='options']",
        "textarea#options",
        "textarea[name='bulk_options']",
        "textarea#bulk_options",
        "textarea[name='attrib']",
        "textarea[name='bulk_attrib']",
    ]:
        el = soup.select_one(sel)
        if el:
            text = (el.get("value") or el.get_text() or "").strip()
            if text:
                return text

    # Fallback: any textarea whose content looks like key=value config lines
    for ta in soup.find_all("textarea"):
        text = (ta.get("value") or ta.get_text() or "").strip()
        if text and "=" in text and "\n" in text:
            return text

    return ""


def _read_textarea_value(driver: Any, ta: Any) -> str:
    """Read the current value of a textarea element.

    Uses JavaScript first (bypasses Selenium's visibility/stale checks) then falls
    back to get_attribute('value') and .text in order.
    """
    try:
        val = driver.execute_script("return arguments[0].value", ta) or ""
        if val.strip():
            return val.strip()
    except Exception:
        pass
    try:
        val = ta.get_attribute("value") or ""
        if val.strip():
            return val.strip()
    except Exception:
        pass
    try:
        return (ta.text or "").strip()
    except Exception:
        return ""


def _capture_bulk_config(driver: Any, edit_url: str, emit_fn: Any = None) -> str:
    """Navigate to the edit_device page and extract the Bulk Attribute Config text.

    Strategy:
      1. Navigate to edit_url and try static HTML extraction first (fast, no clicking).
         The textarea is often pre-rendered in the DOM even before the modal opens.
      2. If the HTML parse returns empty, find and click the 'Bulk Attribute Edit'
         button to open the jQuery UI dialog.
      3. Wait (with a separate try/except) for a textarea to become populated.
      4. Read all textareas via JavaScript — first pass: visible textareas only;
         second pass: any textarea with content (handles opacity-transition modals).

    DOM assumption: button has id="bulk_attrib_edit" (most reliable selector).

    CRITICAL BUG FIXED: previously the extraction loop was INSIDE the same try block
    as the WebDriverWait. When the wait raised TimeoutException the extraction loop
    was silently skipped and config_text remained "". The wait and extraction are now
    in separate try blocks so a timeout still allows the read attempt.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _log(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    driver.get(edit_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )
    except Exception:
        _log(f"bulk_config_no_form url={edit_url[:80]}")
        return ""

    # ── Step 1: try static HTML extraction before clicking anything ────────────
    # The textarea is often pre-rendered in the hidden jQuery UI dialog DOM with
    # its content already set server-side, so we can read it without opening the modal.
    config_text = _extract_bulk_config_from_html(driver.page_source)
    if config_text:
        _log(f"bulk_config_from_html len={len(config_text)}")
        return config_text

    # ── Step 2: find the Bulk Attribute Edit button ────────────────────────────
    # DOM assumption: id="bulk_attrib_edit" is the primary selector; class and
    # name attributes are secondary fallbacks added by some FreePBX versions.
    bulk_btn = None
    for selector in ["#bulk_attrib_edit", ".bulk_attrib_edit", "button[name='bulk_attrib_edit']"]:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        if els:
            bulk_btn = els[0]
            break

    if not bulk_btn:
        try:
            bulk_btn = driver.find_element(
                By.XPATH,
                "//button[contains(normalize-space(),'Bulk Attribute Edit')]"
                " | //input[@value='Bulk Attribute Edit']",
            )
        except Exception:
            _log("bulk_config_btn_not_found")
            return ""

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bulk_btn)
        time.sleep(0.4)
        try:
            bulk_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", bulk_btn)
    except Exception as exc:
        _log(f"bulk_config_click_failed err={exc}")
        return ""

    # ── Step 3: wait for a textarea to be populated ────────────────────────────
    # NOTE: This wait is in its OWN try block. A TimeoutException here must NOT
    # prevent the extraction attempt in Step 4 — the modal may be fully populated
    # even if the wait condition never returned True (e.g. due to a stale element
    # reference mid-iteration in the lambda).
    # We use execute_script to read .value inside the lambda to avoid StaleElement
    # exceptions that can fire when the DOM updates during iteration.
    try:
        WebDriverWait(driver, 10).until(
            lambda d: any(
                (d.execute_script("return arguments[0].value", ta) or "").strip()
                for ta in d.find_elements(By.CSS_SELECTOR, "textarea")
            )
        )
    except Exception:
        # Timeout or stale element — fall through and attempt extraction anyway
        _log("bulk_config_wait_timeout — attempting read anyway")

    # ── Step 4: read textarea value ────────────────────────────────────────────
    # Two-pass approach:
    #   Pass 1 — visible textareas only (the modal textarea should be visible now)
    #   Pass 2 — all textareas via JS (catches opacity/transform-hidden modals where
    #             is_displayed() returns False despite the dialog being "open")
    config_text = ""

    # Pass 1: visible textareas (most precise — excludes pre-rendered hidden fields)
    for ta in driver.find_elements(By.CSS_SELECTOR, "textarea"):
        try:
            if not ta.is_displayed():
                continue
            val = _read_textarea_value(driver, ta)
            if val:
                config_text = val
                _log(f"bulk_config_pass1_visible len={len(val)}")
                break
        except Exception:
            continue

    # Pass 2: any textarea with content (fallback for non-standard modal display)
    if not config_text:
        for ta in driver.find_elements(By.CSS_SELECTOR, "textarea"):
            try:
                val = _read_textarea_value(driver, ta)
                if val and len(val) >= 10:
                    config_text = val
                    _log(f"bulk_config_pass2_any len={len(val)}")
                    break
            except Exception:
                continue

    # Pass 3: Ace editor (some FreePBX pages render the config inside an Ace editor
    #          div rather than a plain textarea — the textarea stays empty while the
    #          visible content lives in the Ace model).
    if not config_text:
        try:
            ace_value = driver.execute_script(
                """
                var editors = document.querySelectorAll('.ace_editor');
                for (var i = 0; i < editors.length; i++) {
                    try {
                        var val = window.ace.edit(editors[i]).getValue();
                        if (val && val.trim().length >= 10) return val.trim();
                    } catch(e) {}
                }
                return '';
                """
            )
            if ace_value and ace_value.strip():
                config_text = ace_value.strip()
                _log(f"bulk_config_pass3_ace len={len(config_text)}")
        except Exception:
            pass

    _log(
        f"bulk_config_result len={len(config_text)} "
        f"preview={config_text[:80]!r}"
    )

    # Close the modal so the page is clean for the next device
    try:
        cancel = driver.find_element(
            By.XPATH,
            "//button[normalize-space()='Cancel'] | //input[@value='Cancel']",
        )
        cancel.click()
        time.sleep(0.3)
    except Exception:
        pass

    return config_text.strip()


def _capture_site_config(driver: Any, detail_url: str) -> str:
    """Navigate to a vpbx_detail page, click Site Specific Config, return the config text.

    The button is: <button id="site_editor_button" class="site_editor_button">Site Specific Config</button>
    It opens an in-page modal with a <textarea> containing the site-wide XML/key-value config
    (Polycom site config, admin passwords, SNTP settings, etc.).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(detail_url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
    except Exception:
        return ""

    # Find the Site Specific Config button by id/class (primary), then fall back to XPath text
    site_btn = None
    for selector in [
        "#site_editor_button",
        ".site_editor_button",
        "button[name='site_editor_button']",
    ]:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        if els:
            site_btn = els[0]
            break

    if not site_btn:
        try:
            site_btn = driver.find_element(
                By.XPATH,
                "//button[contains(normalize-space(),'Site Specific Config')]"
                " | //input[@value='Site Specific Config']",
            )
        except Exception:
            return ""

    try:
        site_btn.click()
    except Exception:
        return ""

    # Wait for the config textarea to appear
    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "textarea"))
        )
        config_text = textarea.get_attribute("value") or textarea.text or ""
    except Exception:
        config_text = ""

    # Close the modal by clicking Cancel
    try:
        cancel = driver.find_element(
            By.XPATH,
            "//button[normalize-space()='Cancel'] | //input[@value='Cancel']",
        )
        cancel.click()
        time.sleep(0.3)
    except Exception:
        pass

    return config_text.strip()


def fetch_device_configs(
    base_url: str,
    *,
    handles: list[str] | None = None,
    skip_handles: set[str] | None = None,
    on_handle_done: Any = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Scrape bulk device configs from vpbx.cgi.

    Strategy: use Selenium only for SSO authentication and the initial list page,
    then switch to a requests.Session (seeded with the browser's cookies) for all
    detail and edit-device page fetches. This is 10-50x faster than driving every
    page through the browser.

    Navigation path:
      [Selenium] vpbx.cgi list → extract cookies → requests.Session
      [requests] vpbx_detail&id=X  →  edit_device&device_id=Y  → parse HTML for config

    Falls back to Selenium browser interaction for any device where the config is not
    found in the page HTML (e.g. rendered entirely by JS).

    Args:
        skip_handles: Set of handle strings (uppercase) to skip — already scraped.
            Pass the set of handles already in the DB to resume an interrupted run.
        on_handle_done: Optional callback(handle, records) called immediately after
            each handle's devices are scraped. Use this to flush records to the DB
            incrementally so progress is not lost if the job is interrupted.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    target_url = _vpbx_cgi_url(base_url)
    handle_filter = {h.upper() for h in handles} if handles else None
    already_done = {h.upper() for h in skip_handles} if skip_handles else set()

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    all_records: list[dict[str, str]] = []

    try:
        driver.get(target_url)
        _emit("waiting_for_login")

        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        vpbx_list = _collect_all_vpbx_ids_by_paging(driver, base_url, emit_fn=_emit)
        _emit(f"found {len(vpbx_list)} handles to scrape")

        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered to {len(vpbx_list)} handle(s)")

        if already_done:
            skipped = [v for v in vpbx_list if v["handle"].upper() in already_done]
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() not in already_done]
            _emit(f"resuming — {len(skipped)} already done, {len(vpbx_list)} remaining")

        if not vpbx_list:
            _emit("complete — no new devices to scrape")
            return []

        total = len(vpbx_list)
        for vpbx_idx, vpbx_entry in enumerate(vpbx_list):
            vpbx_id = vpbx_entry["vpbx_id"]
            handle = vpbx_entry["handle"]
            _emit(f"[{vpbx_idx + 1}/{total}] {handle} — loading device list")

            driver.get(vpbx_entry["detail_url"])
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
            except Exception:
                _emit(f"[{vpbx_idx + 1}/{total}] {handle} — no device table found")
                continue

            devices = _parse_device_rows(driver.page_source, base_url, vpbx_id, handle)
            _emit(f"[{vpbx_idx + 1}/{total}] {handle} — {len(devices)} devices")

            handle_records: list[dict[str, str]] = []
            for dev_idx, device in enumerate(devices):
                name = device.get("directory_name") or device["device_id"]
                device_id = device["device_id"]
                _emit(
                    f"[{vpbx_idx + 1}/{total}] {handle} "
                    f"device {dev_idx + 1}/{len(devices)}: {name} (id={device_id})"
                )

                # Pass emit_fn so _capture_bulk_config logs each sub-step
                config_text = _capture_bulk_config(driver, device["edit_url"], emit_fn=emit_fn)

                # Validation: configs shorter than 20 chars are almost certainly noise
                # (e.g. a stray textarea with a button label). Log and discard them so
                # they don't overwrite a previously saved real config.
                if config_text and len(config_text) < 20:
                    _emit(
                        f"bulk_config_too_short handle={handle} device={device_id} "
                        f"len={len(config_text)} val={config_text!r} — discarding"
                    )
                    config_text = ""

                now = _iso_now()
                device["bulk_config"] = config_text
                device["config_status"] = "ok" if config_text else "empty"
                device["config_length"] = str(len(config_text))
                device["config_scraped_utc"] = now

                _emit(
                    f"bulk_config_saved handle={handle} device={device_id} "
                    f"status={device['config_status']} len={len(config_text)}"
                )
                handle_records.append(device)

            all_records.extend(handle_records)
            if on_handle_done and handle_records:
                on_handle_done(handle, handle_records)
                _emit(f"[{vpbx_idx + 1}/{total}] {handle} saved — {len(handle_records)} configs")

    finally:
        driver.quit()

    _emit(f"complete — {len(all_records)} device configs saved")
    return all_records


def _extract_site_config_from_html(html: str) -> str:
    """Parse the site-specific config out of a vpbx_detail page without browser interaction.

    The Site Specific Config button opens a modal whose content comes from a textarea
    already present in the page HTML. We try known names/ids first.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    for sel in [
        "textarea[name='site_config']",
        "textarea#site_config",
        "textarea[name='site_specific_config']",
        "textarea[name='config']",
        "textarea#config",
    ]:
        el = soup.select_one(sel)
        if el:
            text = (el.get("value") or el.get_text() or "").strip()
            if text:
                return text

    # Fallback: any textarea with XML-looking content (Polycom site config is XML)
    for ta in soup.find_all("textarea"):
        text = (ta.get("value") or ta.get_text() or "").strip()
        if text and ("<" in text or ("=" in text and "\n" in text)):
            return text

    return ""


def fetch_site_configs(
    base_url: str,
    *,
    handles: list[str] | None = None,
    skip_handles: set[str] | None = None,
    on_handle_done: Any = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Scrape site-specific configs from vpbx.cgi.

    Uses Selenium only for SSO auth + list page, then switches to requests for
    all detail page fetches. Falls back to Selenium click-through for any handle
    where the config is not found in the static HTML.

    Navigation path:
      [Selenium] vpbx.cgi list → extract cookies → requests.Session
      [requests] vpbx_detail&id=X → parse HTML for site config textarea

    Args:
        skip_handles: Handles (uppercase) to skip — already scraped. Pass to resume.
        on_handle_done: Optional callback(handle, [record]) called after each handle
            completes so the caller can flush to DB incrementally.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _emit(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    target_url = _vpbx_cgi_url(base_url)
    handle_filter = {h.upper() for h in handles} if handles else None
    already_done = {h.upper() for h in skip_handles} if skip_handles else set()

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    all_records: list[dict[str, str]] = []

    try:
        driver.get(target_url)
        _emit("waiting_for_login")

        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        vpbx_list = _collect_all_vpbx_ids_by_paging(driver, base_url, emit_fn=_emit)
        _emit(f"found_vpbx_entries count={len(vpbx_list)}")

        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered_to count={len(vpbx_list)}")

        if already_done:
            skipped = [v for v in vpbx_list if v["handle"].upper() in already_done]
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() not in already_done]
            _emit(f"resuming skipped={len(skipped)} remaining={len(vpbx_list)}")

        for vpbx_entry in vpbx_list:
            vpbx_id = vpbx_entry["vpbx_id"]
            handle = vpbx_entry["handle"]
            detail_url = vpbx_entry["detail_url"]
            _emit(f"site_config handle={handle} vpbx_id={vpbx_id}")

            config_text = _capture_site_config(driver, detail_url)
            _emit(f"site_config_done handle={handle} lines={len(config_text.splitlines())}")

            record = {
                "vpbx_id": vpbx_id,
                "handle": handle,
                "detail_url": detail_url,
                "site_config": config_text,
                "last_seen_utc": _iso_now(),
            }
            all_records.append(record)
            if on_handle_done:
                on_handle_done(handle, [record])
                _emit(f"flushed handle={handle}")

    finally:
        driver.quit()

    _emit(f"complete total_handles={len(all_records)}")
    return all_records
