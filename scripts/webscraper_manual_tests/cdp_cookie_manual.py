#!/usr/bin/env python3
# Manual / integration script; not run by pytest.
"""Manual cookie diagnostics using Selenium and CDP."""

from __future__ import annotations

import os
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options


def main() -> int:
    profile_dir = os.getenv("EDGE_PROFILE_DIR")
    if not profile_dir:
        print("Missing EDGE_PROFILE_DIR. Set it to your Edge user-data directory.")
        return 1

    opts = Options()
    opts.add_argument("--user-data-dir=" + profile_dir)

    driver = webdriver.Edge(options=opts)
    try:
        driver.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
        time.sleep(2)

        print("TITLE =", driver.title)
        print("URL   =", driver.current_url)

        selenium_cookies = driver.get_cookies()
        print("selenium_cookie_count =", len(selenium_cookies))

        try:
            driver.execute_cdp_cmd("Network.enable", {})
            all_cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})
            cookies = all_cookies.get("cookies", [])
            interesting = [c for c in cookies if "123.net" in c.get("domain", "")]
            print("cdp_cookie_count_total =", len(cookies))
            print("cdp_cookie_count_123net =", len(interesting))
            print("cdp_cookie_domains_sample =", sorted({c.get("domain") for c in interesting})[:10])
        except Exception as exc:
            print("CDP failed:", repr(exc))
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
