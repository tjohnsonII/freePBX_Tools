"""Cookie persistence helpers for Selenium sessions.

These functions maintain compatibility with the historical cookie JSON format.
"""

from typing import Any

from webscraper.ultimate_scraper_legacy import load_cookies_json, save_cookies_json

__all__ = ["save_cookies_json", "load_cookies_json"]
