from __future__ import annotations

import psutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/system", tags=["system"])


class KillPortPayload(BaseModel):
    port: int


@router.get("/ports")
async def ports(request: Request) -> dict:
    return request.app.state.system_inspector.ports()


@router.post("/kill-port")
async def kill_port(request: Request, payload: KillPortPayload) -> dict:
    killed = []
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == payload.port and conn.pid:
            try:
                psutil.Process(conn.pid).kill()
                killed.append(conn.pid)
            except psutil.Error as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "port": payload.port, "killed_pids": killed}


@router.get("/processes")
async def processes(request: Request) -> dict:
    return {"processes": request.app.state.system_inspector.processes()}


@router.get("/env")
async def env(request: Request) -> dict:
    return {"env": request.app.state.system_inspector.env()}


@router.get("/paths")
async def paths(request: Request) -> dict:
    return request.app.state.system_inspector.paths()


@router.get("/infra")
async def infra(request: Request) -> dict:
    """Key service health at a glance."""
    # Ticket API reachability
    ticket_api_ok = False
    try:
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:8788/health", timeout=3) as r:
            ticket_api_ok = r.status == 200
    except Exception:
        pass

    return {
        "ticket_api": {"up": ticket_api_ok, "port": 8788},
    }
