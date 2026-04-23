"""Ticket discovery and ticket URL loading helpers."""

from webscraper.ultimate_scraper_legacy import (
    _coerce_ticket_entry,
    _load_ticket_urls_for_handle,
    _load_tickets_json,
    build_ticket_url_entry,
    classify_url,
    parse_ticket_id,
)

__all__ = [
    "parse_ticket_id",
    "classify_url",
    "build_ticket_url_entry",
    "_coerce_ticket_entry",
    "_load_tickets_json",
    "_load_ticket_urls_for_handle",
]
