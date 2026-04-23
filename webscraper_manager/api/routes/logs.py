from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["logs"])

# Root of the workspace — two levels up from this file's package
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOG_DIR = _REPO_ROOT / "var" / "web-app-launcher" / "logs"

_TAIL_LINES = 200


def _tail(path: Path, n: int = _TAIL_LINES) -> list[str]:
    """Return up to *n* lines from the end of *path* without loading the whole file."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()[-n:]
    except OSError:
        return []


@router.get("/api/logs/recent")
async def recent_logs(request: Request) -> dict:
    return {"events": await request.app.state.event_bus.recent(limit=300)}


@router.get("/api/logs/files")
async def service_log_files() -> dict:
    """Return the last lines of every service log file in the launcher log directory."""
    result: dict[str, list[str]] = {}
    if _LOG_DIR.is_dir():
        for log_file in sorted(_LOG_DIR.glob("*.log")):
            service = log_file.stem
            result[service] = [l.rstrip("\n") for l in _tail(log_file)]
    return {"services": result}


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = websocket.app.state.event_bus.subscribe()
    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=15)
            await websocket.send_json(event)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    finally:
        websocket.app.state.event_bus.unsubscribe(queue)


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await ws_logs(websocket)
