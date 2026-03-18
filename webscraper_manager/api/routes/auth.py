from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    browser: str = "chrome"
    profile: str = "Profile 1"
    domain: str = "secure.123.net"


@router.get("/status")
async def auth_status(request: Request) -> dict:
    return request.app.state.state_store.auth


@router.post("/seed")
async def seed_auth(request: Request, payload: AuthRequest) -> dict:
    return await request.app.state.auth_inspector.seed_auth(payload.browser, payload.profile, payload.domain)


@router.post("/validate")
async def validate_auth(request: Request, payload: AuthRequest) -> dict:
    return await request.app.state.auth_inspector.validate(payload.domain)


@router.post("/sync/chrome")
async def sync_chrome(request: Request) -> dict:
    return await request.app.state.auth_inspector.seed_auth("chrome", "Profile 1", "secure.123.net")


@router.post("/sync/edge")
async def sync_edge(request: Request) -> dict:
    return await request.app.state.auth_inspector.seed_auth("edge", "Default", "secure.123.net")


@router.post("/import")
async def import_cookies(request: Request, payload: AuthRequest) -> dict:
    return await request.app.state.auth_inspector.seed_auth(payload.browser, payload.profile, payload.domain)


@router.post("/clear")
async def clear_cookies(request: Request) -> dict:
    state = request.app.state.state_store
    state.cookies["cookie_count"] = 0
    state.cookies["domains"] = []
    state.cookies["missing_required_cookie_names"] = ["sessionid", "csrftoken"]
    state.auth["authenticated"] = False
    state.auth["cookie_count"] = 0
    return {"success": True}


@router.get("/cookies/summary")
async def cookies_summary(request: Request) -> dict:
    return request.app.state.auth_inspector.cookie_summary()


@router.get("/cookies/detail")
async def cookies_detail(request: Request) -> dict:
    return {"cookies": request.app.state.auth_inspector.cookie_summary(), "note": "integration point for raw cookie dump"}


@router.get("/history")
async def auth_history(request: Request) -> dict:
    events = await request.app.state.event_bus.recent(limit=200)
    return {"events": [e for e in events if e["category"] == "auth"]}
