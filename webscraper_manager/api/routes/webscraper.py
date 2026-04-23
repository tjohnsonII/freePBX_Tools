from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter

TICKET_API = "http://127.0.0.1:8788"
TIMEOUT = 5

router = APIRouter(prefix="/api/webscraper", tags=["webscraper"])


def _get(path: str) -> dict:
    req = Request(f"{TICKET_API}{path}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _fetch_all() -> dict:
    health: dict | None = None
    status: dict | None = None
    state: dict | None = None
    errors: list[str] = []

    try:
        health = _get("/health")
    except (URLError, OSError) as exc:
        errors.append(f"health: {exc}")

    try:
        status = _get("/api/system/status")
    except (URLError, OSError) as exc:
        errors.append(f"status: {exc}")

    try:
        state = _get("/api/scrape/state")
    except (URLError, OSError) as exc:
        errors.append(f"state: {exc}")

    api_ok = health is not None and health.get("ok", False)
    db_counts = (status or {}).get("db_counts", {})
    current_job = (status or {}).get("current_job")

    return {
        "api_ok": api_ok,
        "api_target": TICKET_API,
        "db_tickets": db_counts.get("tickets", 0),
        "db_handles": db_counts.get("handles", 0),
        "current_state": (status or {}).get("state", "unknown"),
        "backend_health": (status or {}).get("backend_health", "unknown"),
        "last_error": (status or {}).get("last_error"),
        "last_successful_scrape": (status or {}).get("last_successful_scrape"),
        "last_scraped_handle": (state or {}).get("last_completed_handle"),
        "active_job": {
            "job_id": current_job["job_id"],
            "state": current_job.get("current_state"),
            "step": current_job.get("current_step"),
            "records_found": current_job.get("records_found", 0),
            "records_written": current_job.get("records_written", 0),
        } if current_job else None,
        "fetch_errors": errors,
        "checked_at": datetime.now(UTC).isoformat(),
    }


@router.get("/status")
async def webscraper_status() -> dict:
    return _fetch_all()


@router.get("/handles")
async def webscraper_handles(q: str = "", limit: int = 500) -> dict:
    try:
        result = _get(f"/api/handles/summary?q={q}&limit={limit}")
    except (URLError, OSError) as exc:
        return {"items": [], "error": str(exc)}
    return {"items": result if isinstance(result, list) else []}


@router.get("/company/{handle}")
async def webscraper_company(handle: str) -> dict:
    detail: dict = {}
    tickets: dict = {}
    timeline: dict = {}
    errors: list[str] = []
    try:
        detail = _get(f"/companies/{handle}")
    except (URLError, OSError) as exc:
        errors.append(f"detail: {exc}")
    try:
        tickets = _get(f"/companies/{handle}/tickets?limit=200")
    except (URLError, OSError) as exc:
        errors.append(f"tickets: {exc}")
    try:
        timeline = _get(f"/companies/{handle}/timeline?limit=200")
    except (URLError, OSError) as exc:
        errors.append(f"timeline: {exc}")
    return {
        "handle": handle,
        "company": detail.get("company"),
        "latest": detail.get("latest"),
        "tickets": tickets.get("items", []),
        "timeline": timeline.get("items", []),
        "errors": errors,
    }


@router.post("/company/{handle}/build-timeline")
async def webscraper_build_timeline(handle: str) -> dict:
    import urllib.request as _ur
    req = _ur.Request(
        f"{TICKET_API}/jobs/build-timeline",
        data=json.dumps({"handle": handle}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except (URLError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/events")
async def webscraper_events() -> dict:
    """Return recent events from the most recent scrape job, normalized to the manager event shape."""
    try:
        jobs_resp = _get("/api/jobs")
    except (URLError, OSError):
        return {"events": [], "job_id": None}

    items = jobs_resp.get("items", [])
    if not items:
        return {"events": [], "job_id": None}

    job_id = items[0].get("job_id")
    try:
        ev_resp = _get(f"/api/jobs/{job_id}/events?limit=100")
    except (URLError, OSError):
        return {"events": [], "job_id": job_id}

    normalized = [
        {
            "timestamp": ev.get("ts_utc", ""),
            "level": ev.get("level", "info"),
            "category": "scraper",
            "event_type": ev.get("event", ""),
            "message": ev.get("message", ""),
            "details": ev.get("data") or {},
        }
        for ev in ev_resp.get("events", [])
    ]
    return {"events": normalized, "job_id": job_id}
