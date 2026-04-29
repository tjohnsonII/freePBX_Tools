"""orders.py — proxy to the ticket API's /api/orders endpoint.

Orders are scraped by the client laptop (scrape_orders.py) and ingested into
the ticket API via POST /api/ingest/orders. This route reads the stored data.
"""
from __future__ import annotations

import logging
import os

import requests as _req
from fastapi import APIRouter, Query

LOGGER = logging.getLogger("webscraper.orders")

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _ticket_api_base() -> str:
    return os.getenv("TICKET_API_URL", "http://127.0.0.1:8788").rstrip("/")


@router.get("")
async def get_orders(
    assigned_to: str = Query(default="", description="Filter by username, e.g. tjohnson"),
    order_type: str = Query(default="", description="Filter by order type, e.g. HOSTED"),
    from_date: str = Query(default="", description="Earliest install date, YYYY-MM-DD"),
) -> dict:
    """
    Return scraped orders for display in the Order Tracker tab.
    Data is populated by the client scraper; this endpoint reads from the DB.
    """
    params: dict[str, str] = {}
    if assigned_to:
        params["assigned_to"] = assigned_to
    if order_type:
        params["order_type"] = order_type
    if from_date:
        params["from_date"] = from_date

    try:
        resp = _req.get(
            f"{_ticket_api_base()}/api/orders",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        LOGGER.warning("Failed to fetch orders from ticket API: %s", exc)
        return {"ok": False, "error": str(exc), "orders": [], "count": 0}


@router.post("/refresh")
async def refresh_orders() -> dict:
    """Trigger the client orders scraper via the ticket API."""
    try:
        resp = _req.post(
            f"{_ticket_api_base()}/api/orders/refresh",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        LOGGER.warning("Failed to trigger orders refresh: %s", exc)
        return {"ok": False, "error": str(exc)}
