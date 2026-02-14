"""Backward-compatible module shim for the ultimate scraper CLI/runtime.

Primary entrypoint remains:
    python -m webscraper.ultimate_scraper
"""

from webscraper.ultimate_scraper_legacy import *  # noqa: F401,F403
from webscraper.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
