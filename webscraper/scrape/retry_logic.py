"""Retry and auth-redirect handling primitives used during ticket scraping."""

from webscraper.ultimate_scraper_legacy import (
    _capture_auth_redirect_artifacts,
    _is_keycloak_auth_redirect,
    _is_login_redirect,
    _ticket_page_looks_ready,
    _wait_for_ticket_page,
    _wait_for_ticket_ready,
)

__all__ = [
    "_ticket_page_looks_ready",
    "_wait_for_ticket_page",
    "_wait_for_ticket_ready",
    "_is_login_redirect",
    "_is_keycloak_auth_redirect",
    "_capture_auth_redirect_artifacts",
]
