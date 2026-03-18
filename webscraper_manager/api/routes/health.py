from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    return {"ok": True, "time": datetime.now(UTC).isoformat(), "service": "webscraper-noc-api"}


@router.get("/status/summary")
async def status_summary(request: Request) -> dict:
    state = request.app.state.state_store
    return {
        "api": {"ok": True},
        "auth": state.auth,
        "worker": {"paused": state.worker_paused, "running": state.manager_running},
        "db": request.app.state.db_inspector.summary(),
    }


@router.get("/status/full")
async def status_full(request: Request) -> dict:
    return {
        "summary": await status_summary(request),
        "pipeline": request.app.state.ticket_pipeline.pipeline(),
        "cookies": request.app.state.auth_inspector.cookie_summary(),
        "ports": request.app.state.system_inspector.ports(),
    }
