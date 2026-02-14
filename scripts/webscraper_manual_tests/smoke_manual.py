#!/usr/bin/env python3
# Manual / integration script; not run by pytest.
"""Manual smoke check for the legacy Selenium scraping path."""

from __future__ import annotations

from pathlib import Path

from webscraper.scrape.selenium_runner import selenium_scrape_tickets


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "webscraper" / "test-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    selenium_scrape_tickets(
        url="https://example.com",
        output_dir=str(output_dir),
        handles=["demo"],
        headless=True,
        vacuum=False,
        aggressive=False,
        cookie_file=None,
    )
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
