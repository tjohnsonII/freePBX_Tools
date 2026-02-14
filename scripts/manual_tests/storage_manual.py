#!/usr/bin/env python3
"""Manual storage diagnostics using an existing Edge profile."""

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

        local_storage = driver.execute_script(
            "let o={}; for (let i=0;i<localStorage.length;i++){let k=localStorage.key(i); o[k]=localStorage.getItem(k);} return o;"
        )
        session_storage = driver.execute_script(
            "let o={}; for (let i=0;i<sessionStorage.length;i++){let k=sessionStorage.key(i); o[k]=sessionStorage.getItem(k);} return o;"
        )

        print("localStorage keys:", list(local_storage.keys())[:50])
        print("sessionStorage keys:", list(session_storage.keys())[:50])
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
