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


def _capture_bulk_config(driver: Any, edit_url: str) -> str:
    """Navigate to a device edit page, click Bulk Attribute Edit, return the config text.

    The button is: <button id="bulk_attrib_edit" class="bulk_attrib_edit">Bulk Attribute Edit</button>
    It opens an in-page modal with a <textarea> containing the Polycom/Yealink
    SIP configuration parameters. We capture the textarea value then close the modal.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(edit_url)

    # Wait for the page to settle
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )
    except Exception:
        return ""

    # Find the Bulk Attribute Edit button by id/class (primary), then fall back to XPath text
    bulk_btn = None
    for selector in [
        "#bulk_attrib_edit",
        ".bulk_attrib_edit",
        "button[name='bulk_attrib_edit']",
    ]:
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

    # Wait for a textarea to appear (the modal with the config)
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
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Open Chrome, authenticate via SSO, then scrape bulk device configs from vpbx.cgi.

    Navigation path for each device:
      vpbx.cgi (list) → vpbx_detail&id=X → edit_device&device_id=Y → Bulk Attribute Edit

    Pass `handles` to limit scraping to specific company handles (e.g. ["ACG", "AEG"]).
    Omit to scrape all handles — this can take a long time (one page load per device).
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

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    all_records: list[dict[str, str]] = []

    try:
        driver.get(target_url)
        _emit("waiting_for_login")

        # Wait until SSO is done AND the real handles table is loaded.
        # A vpbx_detail link only appears once the data table has rendered.
        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        # vpbx.cgi uses DataTables — expand to show all rows before parsing
        try:
            driver.execute_script(
                "try { $('table').DataTable().page.len(-1).draw(); } catch(e) {}"
            )
            time.sleep(2)
            _emit("datatables_expanded")
        except Exception:
            pass

        # Parse the VPBX list to get all handles and their detail URLs
        vpbx_list = _parse_vpbx_ids(driver.page_source, base_url)
        _emit(f"found_vpbx_entries count={len(vpbx_list)}")

        # Filter by requested handles
        if handle_filter:
            vpbx_list = [v for v in vpbx_list if v["handle"].upper() in handle_filter]
            _emit(f"filtered_to count={len(vpbx_list)}")

        for vpbx_entry in vpbx_list:
            vpbx_id = vpbx_entry["vpbx_id"]
            handle = vpbx_entry["handle"]
            _emit(f"detail handle={handle} vpbx_id={vpbx_id}")

            # Navigate to the detail page for this VPBX
            driver.get(vpbx_entry["detail_url"])
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
            except Exception:
                _emit(f"no_table handle={handle}")
                continue

            devices = _parse_device_rows(driver.page_source, base_url, vpbx_id, handle)
            _emit(f"devices handle={handle} count={len(devices)}")

            for device in devices:
                device_id = device["device_id"]
                _emit(f"config handle={handle} device_id={device_id} make={device.get('make','?')}")

                config_text = _capture_bulk_config(driver, device["edit_url"])
                device["bulk_config"] = config_text

                _emit(f"config_done device_id={device_id} lines={len(config_text.splitlines())}")
                all_records.append(device)

                time.sleep(0.2)  # brief pause between device requests

    finally:
        driver.quit()

    _emit(f"complete total_devices={len(all_records)}")
    return all_records


def fetch_site_configs(
    base_url: str,
    *,
    handles: list[str] | None = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Open Chrome, authenticate via SSO, then scrape site-specific configs from vpbx.cgi.

    Navigation path for each handle:
      vpbx.cgi (list) → vpbx_detail&id=X → Site Specific Config button

    Returns [{vpbx_id, handle, detail_url, site_config, last_seen_utc}, ...].

    Pass `handles` to limit scraping to specific company handles (e.g. ["ACG", "AEG"]).
    Omit to scrape all handles.
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

    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    all_records: list[dict[str, str]] = []

    try:
        driver.get(target_url)
        _emit("waiting_for_login")

        # Wait until SSO is done AND the real handles table is loaded.
        WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0).until(
            lambda d: "vpbx.cgi" in (d.current_url or "")
            and len(d.find_elements(By.XPATH, "//a[contains(@href,'command=vpbx_detail')]")) > 0
        )
        _emit("login_confirmed")

        # vpbx.cgi uses DataTables — expand to show all rows before parsing
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

        for vpbx_entry in vpbx_list:
            vpbx_id = vpbx_entry["vpbx_id"]
            handle = vpbx_entry["handle"]
            detail_url = vpbx_entry["detail_url"]
            _emit(f"site_config handle={handle} vpbx_id={vpbx_id}")

            config_text = _capture_site_config(driver, detail_url)
            _emit(f"site_config_done handle={handle} lines={len(config_text.splitlines())}")

            all_records.append({
                "vpbx_id": vpbx_id,
                "handle": handle,
                "detail_url": detail_url,
                "site_config": config_text,
                "last_seen_utc": _iso_now(),
            })

            time.sleep(0.2)

    finally:
        driver.quit()

    _emit(f"complete total_handles={len(all_records)}")
    return all_records
