from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_bulk_config(text: str) -> str:
    """Normalize a bulk config string for equality comparison.

    Strips leading/trailing whitespace, normalizes line endings to \\n,
    and strips trailing whitespace from each line. Two configs that differ
    only in whitespace/CRLF are considered identical.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


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


def _js_extract_device_properties(driver: Any) -> str:
    """Use JavaScript on the live Selenium DOM to extract Device Properties.

    Table detection strategy (most-reliable first):
      1. Find a known form input (mac, dir_name, etc.) and walk up to its <table>.
      2. Fall back to: first table in the form that does NOT contain "arbitrary"
         in any cell text and DOES contain at least one form element.

    Row parsing handles both common FreePBX layouts:
      Layout A: <tr><th>Label</th><td>input/static</td></tr>
      Layout B: <tr><td>Label</td><td>input/static</td></tr>
    Rows with zero <td> elements (pure header rows) are skipped.
    """
    return driver.execute_script(
        r"""
        function readRows(tbl) {
            var lines = [];
            var rows = tbl.querySelectorAll('tr');
            for (var r = 0; r < rows.length; r++) {
                var tds = rows[r].querySelectorAll('td');
                if (tds.length === 0) continue;  // pure <th> header row

                var labelEl, valCell;
                var thEl = rows[r].querySelector('th');
                if (thEl) {
                    // Layout A: <th>Label</th><td>value</td>
                    labelEl = thEl;
                    valCell = tds[0];
                } else if (tds.length >= 2) {
                    // Layout B: <td>Label</td><td>value</td>
                    labelEl = tds[0];
                    valCell = tds[1];
                } else {
                    continue;
                }

                var label = labelEl.textContent.trim();
                if (!label) continue;
                var key = 'device.' + label.toLowerCase().replace(/\s+/g, '_');

                // Checkboxes (OPTIONS row) — one line per checkbox
                var cbs = valCell.querySelectorAll('input[type="checkbox"]');
                if (cbs.length > 0) {
                    for (var c = 0; c < cbs.length; c++) {
                        var cbLabel = '';
                        var n = cbs[c].nextSibling;
                        while (n) {
                            var t = n.textContent ? n.textContent.trim() : '';
                            if (t) { cbLabel = t; break; }
                            n = n.nextSibling;
                        }
                        if (!cbLabel) cbLabel = cbs[c].name || 'option';
                        var cbKey = (key + '.' + cbLabel.toLowerCase().replace(/\s+/g, '_').replace(/:$/, '')).replace(/\.+$/, '');
                        lines.push(cbKey + '=' + (cbs[c].checked ? 'true' : 'false'));
                    }
                    continue;
                }

                // Select dropdowns
                var sel = valCell.querySelector('select');
                if (sel) {
                    var opt = sel.options[sel.selectedIndex];
                    lines.push(key + '=' + (opt ? opt.text.trim() : ''));
                    continue;
                }

                // Text/number inputs
                var inp = valCell.querySelector('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"])');
                if (inp) {
                    lines.push(key + '=' + inp.value.trim());
                    continue;
                }

                // Static text (Device ID, Make, Model)
                var val = valCell.textContent.trim();
                if (val) lines.push(key + '=' + val);
            }
            return lines;
        }

        // Strategy 1: find a known device form input and walk up to its table
        var anchors = ['input[name*="mac"]', 'input[name*="dir_name"]', 'input[name*="directory"]',
                        'input[name*="extension"]', 'select[name*="template"]'];
        for (var a = 0; a < anchors.length; a++) {
            var el = document.querySelector(anchors[a]);
            if (el) {
                var tbl = el.closest('table');
                if (tbl) return readRows(tbl).join('\n');
            }
        }

        // Strategy 2: first table in the form with form elements that isn't arbitrary
        var tables = document.querySelectorAll('form table, table');
        for (var t = 0; t < tables.length; t++) {
            var tbl = tables[t];
            // skip if it contains "arbitrary" in any header text
            var hasArb = false;
            var hdrEls = tbl.querySelectorAll('th');
            for (var h = 0; h < hdrEls.length; h++) {
                if (hdrEls[h].textContent.toLowerCase().indexOf('arbitrary') >= 0) {
                    hasArb = true; break;
                }
            }
            if (hasArb) continue;
            // must have at least one form element
            if (!tbl.querySelector('input, select, textarea')) continue;
            var result = readRows(tbl);
            if (result.length > 0) return result.join('\n');
        }
        return '';
        """
    ) or ""


def _js_extract_arbitrary_attributes(driver: Any) -> str:
    """Use JavaScript on the live Selenium DOM to extract Arbitrary Attributes.

    Strategy 1 — named inputs matching several common FreePBX naming patterns.
    Strategy 2 — find "arbitrary" text in ANY element (th, td, caption, h*, div, span),
                 locate the nearest table, then read key/value input pairs from data rows.
                 Also checks key/value column headers using both <th> and <td>.
    Returns key=value lines, empty string if none configured.
    """
    return driver.execute_script(
        r"""
        var lines = [];

        // Strategy 0: FreePBX stores arbitrary attributes as
        //   <td>key_name</td><td><input name="attrib-key_name" value="val"></td>
        // The value inputs have name="attrib-{key}" so we read key from the name attribute.
        var attribInputs = document.querySelectorAll('input[name^="attrib-"]');
        for (var i = 0; i < attribInputs.length; i++) {
            var k = attribInputs[i].getAttribute('name').slice('attrib-'.length);
            var v = attribInputs[i].value.trim();
            if (k) lines.push(k + '=' + v);
        }
        if (lines.length > 0) return lines.join('\n');

        // Strategy 1: try several common FreePBX naming patterns for attrib inputs
        var namePairs = [
            ['input[name*="attrib_key"]', 'input[name*="attrib_val"]'],
            ['textarea[name*="attrib_key"]', 'textarea[name*="attrib_val"]'],
            ['input[name="key[]"]', 'input[name="val[]"]'],
            ['input[name*="_key[]"]', 'input[name*="_val[]"]'],
            ['input[name*="[key]"]', 'input[name*="[val]"]'],
        ];
        for (var p = 0; p < namePairs.length; p++) {
            var ks = document.querySelectorAll(namePairs[p][0]);
            var vs = document.querySelectorAll(namePairs[p][1]);
            if (ks.length > 0 && vs.length > 0) {
                var n = Math.min(ks.length, vs.length);
                for (var i = 0; i < n; i++) {
                    var k = ks[i].value.trim();
                    var v = vs[i] ? vs[i].value.trim() : '';
                    if (k) lines.push(k + '=' + v);
                }
                if (lines.length > 0) return lines.join('\n');
            }
        }

        // Strategy 2: find "Arbitrary Attributes" text in ANY element, then find its table
        // Search th, td, caption, h2-h4, legend, label, span, div (in that order of likelihood)
        var searchTags = ['caption', 'legend', 'th', 'td', 'h2', 'h3', 'h4', 'label', 'span', 'div'];
        var arbTable = null;
        for (var s = 0; s < searchTags.length && !arbTable; s++) {
            var candidates = document.querySelectorAll(searchTags[s]);
            for (var c = 0; c < candidates.length; c++) {
                var txt = candidates[c].textContent.trim().toLowerCase();
                if (txt.indexOf('arbitrary') >= 0 && txt.length < 60) {
                    // Found the "Arbitrary Attributes" label — find its table
                    // 1. Ancestor table
                    var tbl = candidates[c].closest('table');
                    if (tbl) { arbTable = tbl; break; }
                    // 2. Next sibling or cousin table
                    var el = candidates[c];
                    for (var up = 0; up < 4 && !arbTable; up++) {
                        var sib = el.nextElementSibling;
                        while (sib && !arbTable) {
                            if (sib.tagName === 'TABLE') { arbTable = sib; }
                            else {
                                var inner = sib.querySelector('table');
                                if (inner) arbTable = inner;
                            }
                            sib = sib.nextElementSibling;
                        }
                        if (!arbTable) el = el.parentElement;
                    }
                    if (arbTable) break;
                }
            }
        }

        if (arbTable) {
            // Find key/value column indices — check BOTH <th> and <td> header cells
            var keyIdx = 0, valIdx = 1;
            var allRows = arbTable.querySelectorAll('tr');
            for (var r = 0; r < allRows.length; r++) {
                var hcells = allRows[r].querySelectorAll('th, td');
                var foundKey = false, foundVal = false;
                for (var h = 0; h < hcells.length; h++) {
                    var ht = hcells[h].textContent.trim().toLowerCase();
                    // Only treat as header if cell has no inputs (pure label cell)
                    if (hcells[h].querySelector('input, textarea')) continue;
                    if (ht === 'key' || ht === 'key:') { keyIdx = h; foundKey = true; }
                    else if (ht === 'value' || ht === 'value:') { valIdx = h; foundVal = true; }
                }
                if (foundKey || foundVal) break;
            }

            // Read data rows: rows that have inputs in the key column.
            // FreePBX renders data rows with <th> cells (not <td>), so we must
            // query both to avoid missing every data row.
            for (var r = 0; r < allRows.length; r++) {
                var cells = allRows[r].querySelectorAll('td, th');
                if (cells.length <= Math.max(keyIdx, valIdx)) continue;
                var kInp = cells[keyIdx].querySelector('input:not([type="hidden"]), textarea');
                var vInp = cells[valIdx] ? cells[valIdx].querySelector('input:not([type="hidden"]), textarea') : null;
                if (!kInp) continue;
                var k = kInp.value.trim();
                var v = vInp ? vInp.value.trim() : '';
                if (k) lines.push(k + '=' + v);
            }
        }

        return lines.join('\n');
        """
    ) or ""


def _js_debug_arbitrary_table(driver: Any) -> str:
    """Return a short diagnostic string about the Arbitrary Attributes table on the page.

    Used for logging only — not part of normal extraction.
    """
    return driver.execute_script(
        r"""
        // Find the arbitrary attributes section and return its outer HTML (truncated)
        var searchTags = ['caption', 'legend', 'th', 'td', 'h2', 'h3', 'h4', 'label', 'span'];
        for (var s = 0; s < searchTags.length; s++) {
            var candidates = document.querySelectorAll(searchTags[s]);
            for (var c = 0; c < candidates.length; c++) {
                var txt = candidates[c].textContent.trim().toLowerCase();
                if (txt.indexOf('arbitrary') >= 0 && txt.length < 60) {
                    var tbl = candidates[c].closest('table');
                    if (!tbl) {
                        var el = candidates[c].parentElement;
                        if (el) {
                            var sib = el.nextElementSibling;
                            while (sib) {
                                if (sib.tagName === 'TABLE') { tbl = sib; break; }
                                var inner = sib.querySelector('table');
                                if (inner) { tbl = inner; break; }
                                sib = sib.nextElementSibling;
                            }
                        }
                    }
                    var html = tbl ? tbl.outerHTML : candidates[c].parentElement.outerHTML;
                    return 'found_via:' + searchTags[s] + ' html_len=' + html.length;
                }
            }
        }
        return 'not_found';
        """
    ) or "js_error"


def _read_modal_textarea(driver: Any, emit_fn: Any, label: str) -> str:
    """Read textarea/Ace/pre content from an open modal dialog.

    Looks specifically inside jQuery UI dialog containers (.ui-dialog-content,
    .ui-dialog) and Bootstrap modal containers (.modal.show, .modal-body) first,
    then falls back to any visible textarea on the page. This prevents stray
    form textareas on the main page from being mistaken for modal content.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    def _log(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    # Known FreePBX placeholder strings that should never be stored as real config data
    _PLACEHOLDERS = {"place holder text", "placeholder text", "placeholder", "enter config here"}

    def _is_placeholder(t: str) -> bool:
        return t.strip().lower() in _PLACEHOLDERS

    # JS snippet to read the current dialog textarea/pre/ace content (returns None if no dialog)
    _READ_JS = r"""
        function isVisible(el) {
            if (!el) return false;
            var r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }
        function readDialog() {
            var dlg = document.querySelector('.ui-dialog');
            if (isVisible(dlg)) {
                var content = dlg.querySelector('.ui-dialog-content') || dlg;
                var ta = content.querySelector('textarea');
                if (ta && ta.value && ta.value.trim()) return ta.value.trim();
                var pre = content.querySelector('pre');
                if (pre && pre.textContent && pre.textContent.trim().length > 5)
                    return pre.textContent.trim();
                var aces = content.querySelectorAll('.ace_editor');
                for (var i = 0; i < aces.length; i++) {
                    try { var v = window.ace.edit(aces[i]).getValue();
                          if (v && v.trim()) return v.trim(); } catch(e) {}
                }
                return '';
            }
            var modal = document.querySelector('.modal.show') || document.querySelector('.modal.in');
            if (isVisible(modal)) {
                var body = modal.querySelector('.modal-body') || modal;
                var ta = body.querySelector('textarea');
                if (ta && ta.value && ta.value.trim()) return ta.value.trim();
                var pre = body.querySelector('pre');
                if (pre && pre.textContent && pre.textContent.trim().length > 5)
                    return pre.textContent.trim();
                var aces = body.querySelectorAll('.ace_editor');
                for (var i = 0; i < aces.length; i++) {
                    try { var v = window.ace.edit(aces[i]).getValue();
                          if (v && v.trim()) return v.trim(); } catch(e) {}
                }
                return '';
            }
            return null;
        }
        return readDialog();
    """

    # Wait for a modal dialog to appear with REAL content (ignore placeholders, require > 1 line
    # OR length > 40 chars so a single meaningful line still counts)
    try:
        WebDriverWait(driver, 12).until(lambda d: d.execute_script(
            r"""
            function isVisible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            var placeholders = ["place holder text", "placeholder text", "placeholder"];
            function isPlaceholder(t) { return placeholders.indexOf(t.trim().toLowerCase()) >= 0; }
            // jQuery UI dialog
            var dlg = document.querySelector('.ui-dialog');
            if (isVisible(dlg)) {
                var content = dlg.querySelector('.ui-dialog-content') || dlg;
                var ta = content.querySelector('textarea');
                if (ta && ta.value) {
                    var v = ta.value.trim();
                    if (v.length > 0 && !isPlaceholder(v)) return true;
                }
                var pre = content.querySelector('pre');
                if (pre && pre.textContent && pre.textContent.trim().length > 5) return true;
                var aces = content.querySelectorAll('.ace_editor');
                for (var i = 0; i < aces.length; i++) {
                    try { var v = window.ace.edit(aces[i]).getValue();
                          if (v && v.trim().length > 0) return true; } catch(e) {}
                }
                // Dialog is open but has only placeholder/empty — signal "opened" so we don't
                // time out, but return false to keep waiting (handled below with fallback)
                return 'open_empty';
            }
            var modal = document.querySelector('.modal.show') || document.querySelector('.modal.in');
            if (isVisible(modal)) {
                var body = modal.querySelector('.modal-body') || modal;
                var ta = body.querySelector('textarea');
                if (ta && ta.value && ta.value.trim().length > 0 && !isPlaceholder(ta.value)) return true;
            }
            var aces = document.querySelectorAll('.ui-dialog .ace_editor, .modal .ace_editor');
            for (var i = 0; i < aces.length; i++) {
                try { var v = window.ace.edit(aces[i]).getValue();
                      if (v && v.trim().length > 0) return true; } catch(e) {}
            }
            return false;
            """
        ))
    except Exception:
        _log(f"{label}_modal_wait_timeout")

    # Wait for content to STABILIZE — poll until two consecutive reads match.
    # This ensures we don't grab partial content when FreePBX loads async.
    prev_text = None
    stable_count = 0
    for _attempt in range(20):  # up to 4 seconds
        current = driver.execute_script(_READ_JS)
        if current is None:
            break  # dialog closed or never opened
        if current == prev_text:
            stable_count += 1
            if stable_count >= 2:
                break  # stable for 0.4s — good enough
        else:
            stable_count = 0
        prev_text = current
        time.sleep(0.2)

    # Use the stabilized value from the poll loop above
    text = prev_text  # None if dialog never opened; '' if opened but empty; str if content found

    if text is None:
        # Capture a quick DOM snapshot to help diagnose what's on the page
        try:
            dom_info = driver.execute_script(r"""
                var parts = [];
                var dlg = document.querySelector('.ui-dialog');
                if (dlg) {
                    var r = dlg.getBoundingClientRect();
                    parts.push('ui-dialog:' + (r.width>0?'visible':'hidden'));
                }
                var modals = document.querySelectorAll('.modal');
                for (var i=0; i<modals.length; i++) {
                    var r = modals[i].getBoundingClientRect();
                    parts.push('modal[' + (modals[i].className||'') + ']:' + (r.width>0?'visible':'hidden'));
                }
                var textareas = document.querySelectorAll('textarea');
                if (textareas.length) parts.push('textareas=' + textareas.length);
                return parts.join(' | ') || 'nothing_visible';
            """) or "js_error"
        except Exception:
            dom_info = "js_error"
        _log(f"{label}_no_dialog_opened dom={dom_info}")
        return ""

    # Filter out known FreePBX placeholder strings
    if _is_placeholder(text):
        _log(f"{label}_placeholder_discarded val={text!r}")
        return ""

    if text:
        _log(f"{label}_captured len={len(text)} lines={text.count(chr(10)) + 1}")
    else:
        _log(f"{label}_dialog_opened_empty")
    return text.strip()


def _close_modal(driver: Any) -> None:
    """Click Cancel/Close to dismiss the open modal."""
    from selenium.webdriver.common.by import By
    try:
        driver.execute_script(
            r"""
            // Try jQuery UI dialog close button first
            var closeBtn = document.querySelector('.ui-dialog-titlebar-close, .ui-dialog .ui-button');
            if (closeBtn) { closeBtn.click(); return; }
            // Bootstrap modal dismiss
            var dismiss = document.querySelector('[data-dismiss="modal"], .modal .close');
            if (dismiss) { dismiss.click(); return; }
            """
        )
        time.sleep(0.2)
    except Exception:
        pass
    try:
        from selenium.webdriver.common.by import By
        cancel = driver.find_element(
            By.XPATH,
            "//button[normalize-space()='Cancel'] | //button[normalize-space()='Close']"
            " | //input[@value='Cancel'] | //input[@value='Close']",
        )
        cancel.click()
        time.sleep(0.2)
    except Exception:
        pass


def _capture_device_page_data(driver: Any, edit_url: str, emit_fn: Any = None) -> dict:
    """Navigate to the edit_device page and capture all four config fields.

    Returns dict with keys:
        device_properties    — key=value lines from Device Properties table
        arbitrary_attributes — key=value lines from Arbitrary Attributes table
        bulk_config          — text from Bulk Attribute Edit modal
        view_config          — text/XML from View Config modal (empty if absent)

    All DOM reads use JavaScript on the live Selenium-rendered page so JS-rendered
    content (attribute inputs, modal dialogs) is always visible.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _log(msg: str) -> None:
        if emit_fn:
            emit_fn(msg)

    result = {
        "device_properties": "",
        "arbitrary_attributes": "",
        "bulk_config": "",
        "view_config": "",
    }

    driver.get(edit_url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )
        # Extra pause for JS to finish rendering attribute inputs
        time.sleep(0.5)
    except Exception:
        _log(f"edit_page_no_form url={edit_url[:80]}")
        return result

    # ── Step 1: Device Properties (JS live DOM) ───────────────────────────────
    dp = _js_extract_device_properties(driver)
    result["device_properties"] = dp
    dp_lines = dp.count("\n") + 1 if dp else 0

    # ── Step 2: Arbitrary Attributes (JS live DOM) ────────────────────────────
    aa = _js_extract_arbitrary_attributes(driver)
    result["arbitrary_attributes"] = aa
    aa_lines = aa.count("\n") + 1 if aa else 0

    # Always log the diagnostic so we can see what the page structure looks like
    aa_debug = _js_debug_arbitrary_table(driver)
    _log(f"edit_page_parsed dp_lines={dp_lines} aa_lines={aa_lines} aa_debug={aa_debug}")

    # ── Step 3: Bulk Attribute Edit modal ─────────────────────────────────────
    bulk_btn = None
    for sel in ["#bulk_attrib_edit", ".bulk_attrib_edit", "button[name='bulk_attrib_edit']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
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
            pass

    if bulk_btn:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", bulk_btn)
            time.sleep(0.3)
            try:
                bulk_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", bulk_btn)
            bulk_text = _read_modal_textarea(driver, emit_fn, "bulk_config")
            result["bulk_config"] = bulk_text
            _close_modal(driver)
            time.sleep(0.3)
        except Exception as exc:
            _log(f"bulk_config_click_failed err={exc}")
    else:
        _log("bulk_config_btn_not_found")

    # ── Step 4: View Config modal (best-effort) ───────────────────────────────
    view_btn = None
    for sel in ["#view_config", ".view_config", "#view_config_button", ".view_config_button"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            view_btn = els[0]
            break
    if not view_btn:
        try:
            view_btn = driver.find_element(
                By.XPATH,
                "//button[contains(normalize-space(),'View Config')]"
                " | //input[@value='View Config']"
                " | //a[contains(normalize-space(),'View Config')]",
            )
        except Exception:
            pass

    if view_btn:
        try:
            # Log button attributes so we know what mechanism it uses
            btn_tag   = view_btn.tag_name or "?"
            btn_class = (view_btn.get_attribute("class") or "")[:80]
            btn_href  = (view_btn.get_attribute("href") or view_btn.get_attribute("data-url") or "")[:80]
            btn_onclick = (view_btn.get_attribute("onclick") or "")[:80]
            _log(f"view_config_btn tag={btn_tag} class={btn_class!r} href={btn_href!r} onclick={btn_onclick!r}")

            handles_before = set(driver.window_handles)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", view_btn)
            time.sleep(0.3)
            try:
                view_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", view_btn)

            # Check if a new window/tab opened
            time.sleep(0.5)
            handles_after = set(driver.window_handles)
            new_windows = handles_after - handles_before
            if new_windows:
                _log(f"view_config_new_window count={len(new_windows)} — switching to read content")
                orig_handle = driver.current_window_handle
                for new_win in new_windows:
                    driver.switch_to.window(new_win)
                    time.sleep(0.5)
                    page_text = driver.find_element(By.TAG_NAME, "body").text[:2000].strip()
                    if page_text:
                        result["view_config"] = page_text
                        _log(f"view_config_captured_from_popup len={len(page_text)}")
                    driver.close()
                driver.switch_to.window(orig_handle)
            else:
                view_text = _read_modal_textarea(driver, emit_fn, "view_config")
                result["view_config"] = view_text
                _close_modal(driver)
                time.sleep(0.3)
        except Exception as exc:
            _log(f"view_config_click_failed err={exc}")
    else:
        _log("view_config_btn_not_found")

    return result


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
    existing_configs: dict | None = None,
    on_handle_done: Any = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Scrape bulk device configs from vpbx.cgi.

    Device-level comparison logic:
      1. If no existing row for a device  → scrape and save.
      2. If existing row has empty config → scrape and save.
      3. If existing row has non-empty config AND scraped config is non-empty AND
         normalize_bulk_config(scraped) == normalize_bulk_config(stored) → skip DB write.
      4. If scraped config is empty and stored is non-empty → keep stored (upsert SQL
         protects non-empty from being overwritten by empty).

    Args:
        skip_handles: Handle strings (uppercase) to skip entirely — used only for
            targeted single-handle runs or explicit resume. Do NOT pass this for
            all-handles refresh; use existing_configs instead so device-level
            comparison drives the skip decision.
        existing_configs: Dict keyed by (device_id, vpbx_id) → stored bulk_config
            text. When provided, after scraping each device the scraped config is
            normalized and compared to the stored value. Identical configs skip the
            DB write; new or changed configs are included in the returned records.
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
    # skip_handles is intentionally unused — every handle is always visited.
    # Comparison against existing_configs drives whether the DB is written, not
    # whether the handle is scraped.

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

        if not vpbx_list:
            _emit("complete — no handles to scrape")
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

                # Capture all four config fields in a single page visit.
                # Retry once on WebDriverException (Chrome tab crash, navigation error).
                try:
                    data = _capture_device_page_data(driver, device["edit_url"], emit_fn=emit_fn)
                except Exception as _dev_exc:
                    exc_msg = str(_dev_exc)
                    if "tab crashed" in exc_msg or "no such window" in exc_msg or "invalid session" in exc_msg.lower():
                        _emit(f"device_tab_crashed handle={handle} device={device_id} — retrying once")
                        try:
                            time.sleep(2)
                            driver.get("about:blank")
                            time.sleep(1)
                            data = _capture_device_page_data(driver, device["edit_url"], emit_fn=emit_fn)
                        except Exception as _retry_exc:
                            _emit(f"device_tab_crashed_retry_failed handle={handle} device={device_id} err={_retry_exc}")
                            continue
                    else:
                        _emit(f"device_capture_failed handle={handle} device={device_id} err={_dev_exc}")
                        continue

                dp = data["device_properties"]
                aa = data["arbitrary_attributes"]
                bulk = data["bulk_config"]
                view = data["view_config"]

                # Device-level comparison: combine all four fields so any change
                # in any field triggers a DB write.
                # existing_configs values are pre-concatenated in the same order.
                _scraped_combined = normalize_bulk_config(f"{dp}\n{aa}\n{bulk}\n{view}")
                _stored_combined = normalize_bulk_config(
                    (existing_configs or {}).get((device_id, vpbx_id), "")
                )
                if _scraped_combined and _stored_combined and _scraped_combined == _stored_combined:
                    _emit(
                        f"device_config_unchanged handle={handle} device={device_id} "
                        f"len={len(_scraped_combined)} — skipping DB write"
                    )
                    continue

                now = _iso_now()
                device["device_properties"] = dp
                device["arbitrary_attributes"] = aa
                device["bulk_config"] = bulk
                device["view_config"] = view
                # config_status reflects whether we got any useful data at all
                has_data = bool(dp or aa or bulk)
                device["config_status"] = "ok" if has_data else "empty"
                device["config_length"] = str(len(dp) + len(aa) + len(bulk))
                device["config_scraped_utc"] = now

                _emit(
                    f"device_config_saved handle={handle} device={device_id} "
                    f"dp={len(dp)} aa={len(aa)} bulk={len(bulk)} view={len(view)}"
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
    existing_configs: dict | None = None,
    on_handle_done: Any = None,
    login_timeout_seconds: int = 300,
    emit_fn: Any = None,
) -> list[dict[str, str]]:
    """Scrape site-specific configs from vpbx.cgi.

    Handle-level comparison logic (mirrors device-config behaviour):
      1. If no existing row for a handle          → scrape and save.
      2. If existing row has empty site_config    → scrape and save.
      3. If existing row has non-empty config AND scraped config is non-empty AND
         normalize_bulk_config(scraped) == normalize_bulk_config(stored) → skip DB write.
      4. If scraped config is empty and stored is non-empty → keep stored (upsert SQL
         protects non-empty from being overwritten by empty).

    Args:
        skip_handles: Handles (uppercase) to skip entirely — kept for backward
            compatibility. Do NOT pass for all-handles refresh; use existing_configs
            so comparison drives the skip decision, not handle existence.
        existing_configs: Dict keyed by handle (uppercase) → stored site_config text.
            After scraping each handle the result is normalized and compared; identical
            configs skip the DB write, new or changed configs are saved.
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
    # skip_handles is intentionally unused — every handle is always visited.
    # Comparison against existing_configs drives whether the DB is written.

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

        for vpbx_entry in vpbx_list:
            vpbx_id = vpbx_entry["vpbx_id"]
            handle = vpbx_entry["handle"]
            detail_url = vpbx_entry["detail_url"]
            _emit(f"site_config handle={handle} vpbx_id={vpbx_id}")

            config_text = _capture_site_config(driver, detail_url)
            _emit(f"site_config_done handle={handle} lines={len(config_text.splitlines())}")

            # Handle-level comparison: skip DB write if scraped == stored (normalized).
            # Same logic as device configs — existence alone is NOT a reason to skip.
            _stored_raw = (existing_configs or {}).get(handle.upper(), "")
            _scraped_norm = normalize_bulk_config(config_text)
            _stored_norm = normalize_bulk_config(_stored_raw)
            if _scraped_norm and _stored_norm and _scraped_norm == _stored_norm:
                _emit(
                    f"site_config_unchanged handle={handle} "
                    f"len={len(_scraped_norm)} — skipping DB write"
                )
                continue  # Identical — no DB update needed

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
