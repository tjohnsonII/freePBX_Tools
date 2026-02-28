from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "webscraper" / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from webscraper.auth.chrome_profile import get_driver_reusing_profile
from webscraper.auth.probe import TARGET_URL, probe_auth
from webscraper.auth.session import build_authenticated_session

LOGGER = logging.getLogger("webscraper.auth_probe")


def _run_requests_probe() -> dict[str, Any]:
    try:
        session = build_authenticated_session()
        return probe_auth(session, url=TARGET_URL)
    except Exception as exc:
        LOGGER.warning("Requests auth probe failed: %s", exc)
        return {
            "ok": False,
            "status_code": 0,
            "detected_login_page": False,
            "cookie_names": [],
            "url": TARGET_URL,
            "notes": f"requests probe error: {exc}",
        }


def _run_selenium_probe() -> dict[str, Any]:
    driver = None
    try:
        driver = get_driver_reusing_profile(headless=False)
        return probe_auth(driver, url=TARGET_URL)
    except Exception as exc:
        LOGGER.warning("Selenium auth probe failed: %s", exc)
        return {
            "ok": False,
            "status_code": 0,
            "detected_login_page": False,
            "cookie_names": [],
            "url": TARGET_URL,
            "notes": f"selenium probe error: {exc}",
        }
    finally:
        if driver is not None:
            driver.quit()


def run_auth_probe() -> dict[str, Any]:
    requests_result = _run_requests_probe()
    selenium_result = _run_selenium_probe()

    if requests_result.get("ok"):
        recommended = "requests"
    elif selenium_result.get("ok"):
        recommended = "selenium"
    else:
        recommended = "none"

    return {
        "ok": bool(requests_result.get("ok") or selenium_result.get("ok")),
        "recommended_method": recommended,
        "requests": requests_result,
        "selenium": selenium_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Auth probe for secure.123.net")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = run_auth_probe()

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Overall auth check: {'PASS' if result.get('ok') else 'FAIL'}")
        print(f"Recommended method: {result.get('recommended_method')}")
        for method in ("requests", "selenium"):
            payload = result.get(method, {})
            print(f"[{method}] ok={payload.get('ok')} status={payload.get('status_code')} url={payload.get('url')}")
            print(f"[{method}] cookie_names={payload.get('cookie_names', [])}")
            print(f"[{method}] notes={payload.get('notes')}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
