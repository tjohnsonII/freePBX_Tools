"""Ingest API routes — accept scraped data POSTed from a remote client.

Authentication: set INGEST_API_KEY env var on the server. Clients must pass
the same value in the X-Ingest-Key header. If the env var is empty the
endpoints fall back to localhost-only (safe for local dev / the Server branch).
"""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


# ── Auth ──────────────────────────────────────────────────────────────────────

_LOCALHOST = {"127.0.0.1", "::1"}


def _require_ingest_auth(request: Request) -> None:
    key = os.getenv("INGEST_API_KEY", "").strip()
    client_host = (request.client.host if request.client else "") or ""
    if not key:
        if client_host not in _LOCALHOST:
            raise HTTPException(
                status_code=403,
                detail="Set INGEST_API_KEY on the server to allow remote ingest.",
            )
        return
    provided = request.headers.get("X-Ingest-Key", "")
    if not hmac.compare_digest(key, provided):
        raise HTTPException(status_code=403, detail="Invalid ingest API key.")


# ── Pydantic bodies ───────────────────────────────────────────────────────────


class _TicketIngestBody(BaseModel):
    handle: str
    tickets: list[dict[str, Any]]


class _HandleRowsBody(BaseModel):
    rows: list[dict[str, Any]]


class _HandleProgressBody(BaseModel):
    handle: str
    status: str
    error: str | None = None
    last_updated_utc: str | None = None
    ticket_count: int | None = None
    last_run_id: str | None = None


class _EventBody(BaseModel):
    created_utc: str
    level: str
    handle: str | None = None
    message: str
    meta: dict[str, Any] | None = None


class _JobCreateBody(BaseModel):
    job_id: str
    handle: str | None = None
    mode: str
    ticket_limit: int | None = None
    status: str
    created_utc: str
    ticket_id: str | None = None
    handles: list[str] | None = None


class _JobUpdateBody(BaseModel):
    job_id: str
    status: str
    progress_completed: int
    progress_total: int
    started_utc: str | None = None
    finished_utc: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


class _JobEventBody(BaseModel):
    job_id: str
    ts_utc: str
    level: str
    event: str
    message: str
    data: dict[str, Any] | None = None


class _NocQueueBody(BaseModel):
    records: list[dict[str, Any]]
    now_utc: str


class _VpbxRecordsBody(BaseModel):
    records: list[dict[str, Any]]
    now_utc: str


class _VpbxDeviceConfigsBody(BaseModel):
    records: list[dict[str, Any]]
    now_utc: str


class _VpbxSiteConfigsBody(BaseModel):
    records: list[dict[str, Any]]
    now_utc: str


# ── Routes ────────────────────────────────────────────────────────────────────
# db and db_path are injected at registration time to avoid circular imports.

_db: Any = None
_db_path_fn: Any = None


def register(app_or_router: Any, db_module: Any, db_path_callable: Any) -> None:
    """Call from app.py after creating the FastAPI app."""
    global _db, _db_path_fn
    _db = db_module
    _db_path_fn = db_path_callable
    app_or_router.include_router(router)


def _dp() -> str:
    return _db_path_fn()


@router.post("/tickets")
def ingest_tickets(body: _TicketIngestBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_tickets_batch(_dp(), body.handle, body.tickets)
    return {"inserted": n}


@router.post("/handles")
def ingest_handles(body: _HandleRowsBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_discovered_handles(_dp(), body.rows)
    return {"inserted": n}


@router.post("/handle-progress")
def ingest_handle_progress(body: _HandleProgressBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    _db.update_handle_progress(
        _dp(),
        body.handle,
        status=body.status,
        error=body.error,
        last_updated_utc=body.last_updated_utc,
        ticket_count=body.ticket_count,
        last_run_id=body.last_run_id,
    )
    return {"ok": True}


@router.post("/event")
def ingest_event(body: _EventBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    _db.add_event(_dp(), body.created_utc, body.level, body.handle, body.message, body.meta)
    return {"ok": True}


@router.post("/job/create")
def ingest_job_create(body: _JobCreateBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    _db.create_scrape_job(
        _dp(),
        body.job_id,
        body.handle,
        body.mode,
        body.ticket_limit,
        body.status,
        body.created_utc,
        ticket_id=body.ticket_id,
        handles=body.handles,
    )
    return {"ok": True}


@router.post("/job/update")
def ingest_job_update(body: _JobUpdateBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    _db.update_scrape_job(
        _dp(),
        body.job_id,
        status=body.status,
        progress_completed=body.progress_completed,
        progress_total=body.progress_total,
        started_utc=body.started_utc,
        finished_utc=body.finished_utc,
        error_message=body.error_message,
        result=body.result,
    )
    return {"ok": True}


@router.post("/job/event")
def ingest_job_event(body: _JobEventBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    _db.add_scrape_event(
        _dp(),
        body.job_id,
        body.ts_utc,
        body.level,
        body.event,
        body.message,
        body.data,
    )
    return {"ok": True}


@router.post("/noc-queue")
def ingest_noc_queue(body: _NocQueueBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_noc_queue_tickets(_dp(), body.records, body.now_utc)
    return {"inserted": n}


@router.post("/vpbx/records")
def ingest_vpbx_records(body: _VpbxRecordsBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_vpbx_records(_dp(), body.records, body.now_utc)
    return {"inserted": n}


@router.post("/vpbx/device-configs")
def ingest_vpbx_device_configs(body: _VpbxDeviceConfigsBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_vpbx_device_configs(_dp(), body.records, body.now_utc)
    return {"inserted": n}


@router.post("/vpbx/site-configs")
def ingest_vpbx_site_configs(body: _VpbxSiteConfigsBody, request: Request) -> dict[str, Any]:
    _require_ingest_auth(request)
    n = _db.upsert_vpbx_site_configs(_dp(), body.records, body.now_utc)
    return {"inserted": n}
