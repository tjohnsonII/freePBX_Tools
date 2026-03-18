from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/db", tags=["db"])


@router.get("/summary")
async def db_summary(request: Request) -> dict:
    return request.app.state.db_inspector.summary()


@router.get("/handles")
async def db_handles(request: Request) -> dict:
    return {"rows": request.app.state.ticket_pipeline.recent_handles}


@router.get("/tickets")
async def db_tickets(request: Request) -> dict:
    return {"rows": request.app.state.ticket_pipeline.recent_tickets}


@router.get("/failures")
async def db_failures(request: Request) -> dict:
    return {"rows": request.app.state.ticket_pipeline.failed_jobs}


@router.get("/integrity")
async def db_integrity(request: Request) -> dict:
    return request.app.state.db_inspector.integrity()
