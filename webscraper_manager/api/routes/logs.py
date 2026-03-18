from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["logs"])


@router.get("/api/logs/recent")
async def recent_logs(request: Request) -> dict:
    return {"events": await request.app.state.event_bus.recent(limit=300)}


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
