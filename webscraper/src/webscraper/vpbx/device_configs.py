from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _vpbx_cgi_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/cgi-bin/web_interface/admin/vpbx.cgi"


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


def _capture_bulk_config(driver: Any, edit_url: str) -> str:
    """Selenium fallback: navigate to edit page, click Bulk Attribute Edit, return config.

    Only used when the HTTP/HTML path fails to find config text.
    The button is: <button id="bulk_attrib_edit" class="bulk_attrib_edit">Bulk Attribute Edit</button>
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(edit_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )
    except Exception:
        return ""

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
            return ""

    try:
        bulk_btn.click()
    except Exception:
        return ""

    try:
        textarea = WebDriverWait(driver, 8).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "textarea"))
        )
        config_text = textarea.get_attribute("value") or textarea.text or ""
    except Exception:
        config_text = ""

    try:
        cancel = driver.find_element(
            By.XPATH,
            "//button[normalize-space()='Cancel'] | //input[@value='Cancel']",
        )
        cancel.click()
        time.sleep(0.2)
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
    from selenium.webdriver.support.ui import WebDriverWait

    from webscraper.auth.session import selenium_driver_to_requests_session

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

        # Expand DataTables to show all rows
        try:
            driver.execute_script(
                "try { $('table').DataTable().page.len(-1).draw(); } catch(e) {}"
            )
            time.sleep(2)
            _emit("datatables_expanded")
        except Exception:
            pass

        vpbx_list = _parse_vpbx_ids(driver.page_source, base_url)
        _emit(f"found_vpbx_entries count={len(vpbx_list)}")

        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered_to count={len(vpbx_list)}")

        # Skip handles already in the DB (resume support)
        if already_done:
            skipped = [v for v in vpbx_list if v["handle"].upper() in already_done]
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() not in already_done]
            _emit(f"resuming skipped={len(skipped)} remaining={len(vpbx_list)}")

        # Hand off to requests — no more browser page loads needed
        session = selenium_driver_to_requests_session(driver, base_url)
        _emit("switched_to_requests_session")

    finally:
        driver.quit()

    # --- HTTP-only phase (fast) ---
    selenium_fallback_needed: list[dict[str, str]] = []

    for vpbx_entry in vpbx_list:
        vpbx_id = vpbx_entry["vpbx_id"]
        handle = vpbx_entry["handle"]
        _emit(f"detail handle={handle} vpbx_id={vpbx_id}")

        try:
            resp = session.get(vpbx_entry["detail_url"], timeout=15)
            resp.raise_for_status()
            detail_html = resp.text
        except Exception as exc:
            _emit(f"detail_fetch_failed handle={handle} error={exc}")
            continue

        devices = _parse_device_rows(detail_html, base_url, vpbx_id, handle)
        _emit(f"devices handle={handle} count={len(devices)}")

        handle_records: list[dict[str, str]] = []
        handle_fallbacks: list[dict[str, str]] = []

        for device in devices:
            device_id = device["device_id"]
            _emit(f"config handle={handle} device_id={device_id} make={device.get('make','?')}")

            try:
                resp = session.get(device["edit_url"], timeout=15)
                resp.raise_for_status()
                config_text = _extract_bulk_config_from_html(resp.text)
            except Exception as exc:
                _emit(f"edit_fetch_failed device_id={device_id} error={exc}")
                config_text = ""

            if config_text:
                device["bulk_config"] = config_text
                _emit(f"config_done device_id={device_id} lines={len(config_text.splitlines())}")
                handle_records.append(device)
            else:
                handle_fallbacks.append(device)
                _emit(f"config_queued_for_selenium_fallback device_id={device_id}")

        # Flush completed (non-fallback) devices for this handle immediately
        if handle_records:
            all_records.extend(handle_records)
            if on_handle_done and not handle_fallbacks:
                # Only flush if no fallbacks pending for this handle — avoids partial saves
                on_handle_done(handle, handle_records)
                _emit(f"flushed handle={handle} devices={len(handle_records)}")

        selenium_fallback_needed.extend(handle_fallbacks)

    # --- Selenium fallback for any devices whose config wasn't in the HTML ---
    if selenium_fallback_needed:
        _emit(f"selenium_fallback count={len(selenium_fallback_needed)}")
        options2 = Options()
        options2.add_argument("--start-maximized")
        driver2 = webdriver.Chrome(options=options2)
        try:
            driver2.get(target_url)
            for cookie in session.cookies:
                try:
                    driver2.add_cookie({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain or "",
                        "path": cookie.path or "/",
                    })
                except Exception:
                    pass

            # Group fallback devices by handle so we can flush per-handle
            fallback_by_handle: dict[str, list[dict[str, str]]] = {}
            for device in selenium_fallback_needed:
                fallback_by_handle.setdefault(device["handle"], []).append(device)

            for fb_handle, fb_devices in fallback_by_handle.items():
                fb_done: list[dict[str, str]] = []
                for device in fb_devices:
                    device_id = device["device_id"]
                    _emit(f"selenium_config handle={fb_handle} device_id={device_id}")
                    config_text = _capture_bulk_config(driver2, device["edit_url"])
                    device["bulk_config"] = config_text
                    _emit(f"selenium_config_done device_id={device_id} lines={len(config_text.splitlines())}")
                    fb_done.append(device)
                    all_records.append(device)

                if on_handle_done and fb_done:
                    on_handle_done(fb_handle, fb_done)
                    _emit(f"flushed handle={fb_handle} devices={len(fb_done)}")
        finally:
            driver2.quit()

    _emit(f"complete total_devices={len(all_records)}")
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
    from selenium.webdriver.support.ui import WebDriverWait

    from webscraper.auth.session import selenium_driver_to_requests_session

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

        try:
            driver.execute_script(
                "try { $('table').DataTable().page.len(-1).draw(); } catch(e) {}"
            )
            time.sleep(2)
            _emit("datatables_expanded")
        except Exception:
            pass

        vpbx_list = _parse_vpbx_ids(driver.page_source, base_url)
        _emit(f"found_vpbx_entries count={len(vpbx_list)}")

        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered_to count={len(vpbx_list)}")

        if already_done:
            skipped = [v for v in vpbx_list if v["handle"].upper() in already_done]
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() not in already_done]
            _emit(f"resuming skipped={len(skipped)} remaining={len(vpbx_list)}")

        session = selenium_driver_to_requests_session(driver, base_url)
        _emit("switched_to_requests_session")

    finally:
        driver.quit()

    # --- HTTP-only phase ---
    selenium_fallback_needed: list[dict[str, str]] = []

    for vpbx_entry in vpbx_list:
        vpbx_id = vpbx_entry["vpbx_id"]
        handle = vpbx_entry["handle"]
        detail_url = vpbx_entry["detail_url"]
        _emit(f"site_config handle={handle} vpbx_id={vpbx_id}")

        try:
            resp = session.get(detail_url, timeout=15)
            resp.raise_for_status()
            config_text = _extract_site_config_from_html(resp.text)
        except Exception as exc:
            _emit(f"site_fetch_failed handle={handle} error={exc}")
            config_text = ""

        if config_text:
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
        else:
            selenium_fallback_needed.append(vpbx_entry)
            _emit(f"site_config_queued_for_selenium_fallback handle={handle}")

    # --- Selenium fallback ---
    if selenium_fallback_needed:
        _emit(f"selenium_fallback count={len(selenium_fallback_needed)}")
        options2 = Options()
        options2.add_argument("--start-maximized")
        driver2 = webdriver.Chrome(options=options2)
        try:
            driver2.get(target_url)
            for cookie in session.cookies:
                try:
                    driver2.add_cookie({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain or "",
                        "path": cookie.path or "/",
                    })
                except Exception:
                    pass
            for vpbx_entry in selenium_fallback_needed:
                handle = vpbx_entry["handle"]
                detail_url = vpbx_entry["detail_url"]
                _emit(f"selenium_site_config handle={handle}")
                config_text = _capture_site_config(driver2, detail_url)
                _emit(f"selenium_site_config_done handle={handle} lines={len(config_text.splitlines())}")
                record = {
                    "vpbx_id": vpbx_entry["vpbx_id"],
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
            driver2.quit()

    _emit(f"complete total_handles={len(all_records)}")
    return all_records
