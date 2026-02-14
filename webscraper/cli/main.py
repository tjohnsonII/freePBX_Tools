"""CLI entrypoint for the webscraper ultimate scraper.

This module keeps argument parsing/dispatch behavior intact by delegating to the
legacy runtime module while preserving the canonical CLI invocation contract.
"""

from webscraper.ultimate_scraper_legacy import main

__all__ = ["main"]
