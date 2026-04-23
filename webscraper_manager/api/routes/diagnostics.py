from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["diagnostics"])


@router.get("/debug/report")
async def debug_report(request: Request) -> dict:
    return {
        "health": {"ok": True},
        "auth": request.app.state.state_store.auth,
        "cookies": request.app.state.state_store.cookies,
        "ticket_pipeline": request.app.state.ticket_pipeline.pipeline(),
        "db_summary": request.app.state.db_inspector.summary(),
        "ports": request.app.state.system_inspector.ports(),
        "env_summary": request.app.state.system_inspector.paths(),
        "recent_failures": request.app.state.ticket_pipeline.failed_jobs[-20:],
        "recent_logs_tail": await request.app.state.event_bus.recent(limit=100),
    }


@router.get("/diagnostics/ticket-ingestion")
async def ticket_ingestion_diagnostics(request: Request) -> dict:
    state = request.app.state.state_store
    db_summary = request.app.state.db_inspector.summary()
    checks = [
        {"name": "cookie_count", "ok": state.cookies.get("cookie_count", 0) > 0, "details": f"count={state.cookies.get('cookie_count', 0)}"},
        {
            "name": "required_cookie_names",
            "ok": len(state.cookies.get("missing_required_cookie_names", [])) == 0,
            "details": f"missing={state.cookies.get('missing_required_cookie_names', [])}",
        },
        {"name": "auth_validation", "ok": state.auth.get("validation", {}).get("ok", False), "details": str(state.auth.get("validation", {}))},
        {"name": "handles_present", "ok": len(request.app.state.ticket_pipeline.recent_handles) > 0, "details": f"count={len(request.app.state.ticket_pipeline.recent_handles)}"},
        {
            "name": "ticket_fetch_recent_success",
            "ok": state.ticket_pipeline["ticket_fetch_succeeded"]["status"] == "success",
            "details": state.ticket_pipeline["ticket_fetch_succeeded"]["message"],
        },
        {"name": "db_recent_insert", "ok": db_summary.get("tickets_count", 0) > 0, "details": f"tickets_count={db_summary.get('tickets_count', 0)}"},
    ]
    failures = [c for c in checks if not c["ok"]]
    overall = "healthy" if not failures else f"blocked_at_{failures[0]['name']}"
    probable = [f"{f['name']} failed: {f['details']}" for f in failures] or ["no blocking failures"]
    return {
        "overall_state": overall,
        "probable_causes": probable,
        "checks": checks,
        "recommended_actions": [
            "re-sync cookies from Chrome Profile 1",
            "run Validate Auth",
            "run Test Ticket Fetch",
            "inspect raw response body from failed validation",
        ],
    }


@router.get("/diagnostics/auth")
async def auth_diag(request: Request) -> dict:
    return {"auth": request.app.state.state_store.auth, "cookies": request.app.state.state_store.cookies}


@router.get("/diagnostics/db")
async def db_diag(request: Request) -> dict:
    return {"summary": request.app.state.db_inspector.summary(), "integrity": request.app.state.db_inspector.integrity()}


@router.get("/diagnostics/system")
async def system_diag(request: Request) -> dict:
    return {
        "ports": request.app.state.system_inspector.ports(),
        "paths": request.app.state.system_inspector.paths(),
        "processes": request.app.state.system_inspector.processes(),
    }
