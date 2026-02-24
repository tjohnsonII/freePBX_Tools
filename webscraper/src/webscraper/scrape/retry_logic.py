"""Retry and auth-redirect handling primitives used during ticket scraping."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from webscraper.ultimate_scraper_legacy import (
    _capture_auth_redirect_artifacts,
    _is_keycloak_auth_redirect,
    _is_login_redirect,
    _ticket_page_looks_ready,
    _wait_for_ticket_page,
    _wait_for_ticket_ready,
)

T = TypeVar("T")


def run_with_retry(action: Callable[[], T], retries: int = 2, delay_s: float = 0.5) -> T:
    """Run ``action`` with simple retry semantics."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - preserve legacy behavior
            last_exc = exc
            if attempt >= retries:
                raise
            time.sleep(delay_s)
    assert last_exc is not None
    raise last_exc


__all__ = [
    "run_with_retry",
    "_ticket_page_looks_ready",
    "_wait_for_ticket_page",
    "_wait_for_ticket_ready",
    "_is_login_redirect",
    "_is_keycloak_auth_redirect",
    "_capture_auth_redirect_artifacts",
]
