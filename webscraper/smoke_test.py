"""CMD-friendly smoke test for webscraper package imports and Selenium startup."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_output_probe() -> str:
    out_dir = os.path.join("webscraper", "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "smoke_test_output.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"smoke_test_ok { _iso_utc_now() }\n")
    return out_path


def _selenium_headless_check() -> None:
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions

    options = EdgeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = webdriver.Edge(options=options)
    try:
        driver.get("https://example.com")
        title = driver.title or ""
        if not title:
            raise RuntimeError("Edge did not return a page title.")
    finally:
        driver.quit()


def main() -> int:
    print("[SMOKE] Starting webscraper smoke test")
    import webscraper.auth  # noqa: F401
    import webscraper.site_selectors  # noqa: F401
    print("[SMOKE] Imports ok (webscraper.auth, webscraper.site_selectors)")

    try:
        _selenium_headless_check()
        print("[SMOKE] Selenium headless startup ok")
    except Exception as exc:
        print(f"[SMOKE] Selenium check failed: {exc}")
        return 1

    try:
        out_path = _write_output_probe()
        print(f"[SMOKE] Output write ok: {out_path}")
    except Exception as exc:
        print(f"[SMOKE] Output write failed: {exc}")
        return 1

    print("[SMOKE] Success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
