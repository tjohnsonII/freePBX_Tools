from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("/status")
async def tickets_status(request: Request) -> dict:
    return {"pipeline": request.app.state.ticket_pipeline.pipeline(), "worker_paused": request.app.state.state_store.worker_paused}


@router.post("/test-fetch")
async def test_fetch(request: Request) -> dict:
    return await request.app.state.ticket_pipeline.test_ticket_fetch()


@router.post("/test-handles")
async def test_handles(request: Request) -> dict:
    return await request.app.state.ticket_pipeline.test_handles()


@router.post("/run-once")
async def run_once(request: Request) -> dict:
    return await request.app.state.ticket_pipeline.run_once()


@router.get("/recent")
async def recent_tickets(request: Request) -> dict:
    return {"tickets": request.app.state.ticket_pipeline.recent_tickets}


@router.get("/failures")
async def ticket_failures(request: Request) -> dict:
    return {"failures": request.app.state.ticket_pipeline.failed_jobs}


@router.get("/pipeline")
async def pipeline(request: Request) -> dict:
    return request.app.state.ticket_pipeline.pipeline()
