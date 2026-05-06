"""
Deep inspection script for secure.123.net orders_web_admin.cgi.

Loads the page using the existing Edge profile (already authenticated),
submits the PM filter, then:
  1. Saves the initial page HTML (orders_inspect_initial.html)
  2. Finds all clickable expand links/buttons and lists them
  3. Clicks each one, waits for DOM change, saves the resulting HTML
  4. For each ORDER ID link found, visits the detail page and saves its HTML
  5. Writes a summary of all discovered links and data shapes

Usage:
    Set EDGE_PROFILE_DIR env var (or add to .env), then:
        python webscraper/scripts/debug/inspect_orders_page.py

Output goes to webscraper/var/orders/inspect/
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Load .env
_env_file = Path(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ORDERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"
OUT_DIR = Path(__file__).resolve().parents[3] / "var" / "orders" / "inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PM = os.environ.get("ORDERS_123NET_PM") or os.environ.get("ORDERS_123NET_USERNAME", "tjohnson")


def _save(name: str, html: str) -> Path:
    p = OUT_DIR / name
    p.write_text(html, encoding="utf-8")
    print(f"  saved → {p}")
    return p


def _driver() -> webdriver.Edge:
    profile = os.environ.get("EDGE_PROFILE_DIR", "")
    opts = Options()
    if profile:
        opts.add_argument(f"--user-data-dir={profile}")
    opts.add_argument("--window-size=1600,1000")
    # Run visible so you can watch and interact if needed
    return webdriver.Edge(options=opts)


def main() -> None:
    print(f"PM filter: {PM}")
    print(f"Output:    {OUT_DIR}")

    driver = _driver()
    wait = WebDriverWait(driver, 20)

    try:
        # ── Step 1: Load and submit the filter form ────────────────────────────
        print("\n[1] Loading orders page...")
        driver.get(ORDERS_URL)
        time.sleep(3)

        # Try to set the engineer filter via JS (the select may have the PM name)
        try:
            # Find the netopsengineer select and choose PM
            selects = driver.find_elements(By.TAG_NAME, "select")
            for sel in selects:
                opts_els = sel.find_elements(By.TAG_NAME, "option")
                for opt in opts_els:
                    if opt.get_attribute("value") == PM or opt.text.strip() == PM:
                        sel.find_element(By.XPATH, f"option[@value='{PM}']").click()
                        print(f"  set engineer filter to {PM}")
                        break

            # Submit the form
            forms = driver.find_elements(By.TAG_NAME, "form")
            if forms:
                forms[0].submit()
                time.sleep(4)
        except Exception as e:
            print(f"  filter form error (continuing): {e}")

        _save("01_initial.html", driver.page_source)
        print(f"  page title: {driver.title}")

        # ── Step 2: Inventory all links and buttons ────────────────────────────
        print("\n[2] Inventorying clickable elements...")
        links = driver.find_elements(By.TAG_NAME, "a")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        inputs_btn = driver.find_elements(By.CSS_SELECTOR, "input[type='button'],input[type='submit']")

        print(f"  links: {len(links)}  buttons: {len(buttons)}  input-buttons: {len(inputs_btn)}")

        summary_lines: list[str] = []
        order_detail_links: list[tuple[str, str]] = []  # (order_id, href)

        for lnk in links:
            href = lnk.get_attribute("href") or ""
            text = lnk.text.strip()
            if not href and not text:
                continue
            summary_lines.append(f"LINK  text={text!r:<40} href={href}")
            # Collect order ID links (match the order ID pattern)
            import re
            if re.match(r"^[A-Z0-9]{3}-[A-F0-9]+$", text, re.IGNORECASE):
                order_detail_links.append((text, href))

        for btn in buttons + inputs_btn:
            text = btn.text.strip() or btn.get_attribute("value") or ""
            summary_lines.append(f"BTN   text={text!r}")

        (OUT_DIR / "02_link_inventory.txt").write_text(
            "\n".join(summary_lines), encoding="utf-8"
        )
        print(f"  found {len(order_detail_links)} order ID links")
        print(f"  link inventory → {OUT_DIR / '02_link_inventory.txt'}")

        # ── Step 3: Click expand-style links/buttons ───────────────────────────
        print("\n[3] Clicking expand controls...")
        # Look for anything that looks like an expand trigger (+ icons, "expand", "details", etc.)
        expand_candidates = driver.find_elements(
            By.CSS_SELECTOR,
            "a.expand, a[class*='expand'], a[class*='toggle'], "
            "button.expand, span.expand, td.expand, "
            "[onclick*='expand'], [onclick*='toggle'], [onclick*='show']"
        )
        print(f"  expand candidates via CSS: {len(expand_candidates)}")

        # Also look for any <a> with no href or href="#" (often expand triggers)
        inline_links = driver.find_elements(By.CSS_SELECTOR, "a[href='#'], a:not([href])")
        print(f"  inline links (#/no-href): {len(inline_links)}")

        for i, el in enumerate(inline_links[:10]):  # cap at 10 to avoid runaway
            try:
                text = el.text.strip()
                print(f"    clicking inline link {i}: {text!r}")
                driver.execute_script("arguments[0].click();", el)
                time.sleep(1)
                _save(f"03_expand_{i:02d}.html", driver.page_source)
            except Exception as e:
                print(f"    error: {e}")

        # ── Step 4: Visit detail pages for first 3 orders ─────────────────────
        print(f"\n[4] Visiting order detail pages (first 3 of {len(order_detail_links)})...")
        for i, (order_id, href) in enumerate(order_detail_links[:3]):
            print(f"  [{i+1}] {order_id} → {href}")
            try:
                driver.get(href if href.startswith("http") else f"https://secure.123.net{href}")
                time.sleep(3)
                _save(f"04_detail_{i+1:02d}_{order_id}.html", driver.page_source)

                # Look for sub-links/expand on detail page
                sub_links = driver.find_elements(By.TAG_NAME, "a")
                sub_btns = driver.find_elements(By.CSS_SELECTOR, "a[href='#'], button")
                print(f"    links: {len(sub_links)}  expand candidates: {len(sub_btns)}")

                # Save a text summary of the detail page content
                body_text = driver.find_element(By.TAG_NAME, "body").text
                (OUT_DIR / f"04_detail_{i+1:02d}_{order_id}_text.txt").write_text(
                    body_text, encoding="utf-8"
                )
            except Exception as e:
                print(f"    error visiting {order_id}: {e}")

        # ── Step 5: Full page text dump ────────────────────────────────────────
        print("\n[5] Saving full text dump of list page...")
        driver.get(ORDERS_URL)
        time.sleep(4)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        _save("05_list_text.txt", body_text)  # type: ignore[arg-type]

        print("\nDone. Inspect files in:", OUT_DIR)

    finally:
        input("\nPress Enter to close the browser...")
        driver.quit()


if __name__ == "__main__":
    main()
