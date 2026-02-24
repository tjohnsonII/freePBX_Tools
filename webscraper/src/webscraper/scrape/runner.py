"""Top-level scrape orchestration entrypoint."""

from __future__ import annotations

from typing import Any

from webscraper import ultimate_scraper_legacy as legacy


def run_scrape(config: dict[str, Any]) -> None:
    """Dispatch to the existing selenium runtime preserving behavior."""
    legacy.selenium_scrape_tickets(**config)


__all__ = ["run_scrape"]
