from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "webscraper" / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from webscraper.auth.seeded_session import is_authenticated_html, seed_requests_session_with_selenium

DEFAULT_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
DEFAULT_OUTPUT = REPO_ROOT / "webscraper" / "var" / "seed_fetch.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed requests auth from Selenium and fetch customers.cgi")
    parser.add_argument("--url", default=DEFAULT_URL, help="Authenticated URL to open for cookie seeding")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge", help="Browser to use for auth seeding")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to save fetched HTML")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    session = seed_requests_session_with_selenium(url=args.url, headless=bool(args.headless), browser=str(args.browser))
    response = session.get(DEFAULT_URL, timeout=30, allow_redirects=True)
    authenticated = is_authenticated_html(response.text)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.text, encoding="utf-8")

    print(f"status_code: {response.status_code}")
    print(f"authenticated: {'true' if authenticated else 'false'}")
    print(f"output: {output_path}")

    return 0 if response.status_code == 200 and authenticated else 1


if __name__ == "__main__":
    raise SystemExit(main())
