#!/usr/bin/env python3
"""Manual cookie visibility check using an existing Edge profile."""

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

    profile_name = os.getenv("EDGE_PROFILE_NAME", "Default")

    opts = Options()
    opts.add_argument("--user-data-dir=" + profile_dir)
    opts.add_argument("--profile-directory=" + profile_name)

    driver = webdriver.Edge(options=opts)
    try:
        driver.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
        time.sleep(2)

        print("TITLE =", driver.title)
        print("URL   =", driver.current_url)

        cookies = driver.get_cookies()
        print("Cookie count:", len(cookies))
        print("First few cookie names:", [c.get("name") for c in cookies[:10]])
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
