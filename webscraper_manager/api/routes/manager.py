from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _manager_command(action: str) -> list[str]:
    return ["python", "-m", "webscraper_manager", action, "--json"]


@router.post("/start")
async def start_manager(request: Request) -> dict:
    result = await request.app.state.command_runner.run(_manager_command("start"))
    request.app.state.state_store.manager_running = result["success"]
    return result


@router.post("/stop")
async def stop_manager(request: Request) -> dict:
    result = await request.app.state.command_runner.run(_manager_command("stop"))
    request.app.state.state_store.manager_running = not result["success"]
    return result


@router.post("/restart")
async def restart_manager(request: Request) -> dict:
    return await request.app.state.command_runner.run(_manager_command("restart"))


@router.post("/doctor")
async def doctor(request: Request) -> dict:
    return await request.app.state.command_runner.run(_manager_command("doctor"))


@router.post("/test-smoke")
async def test_smoke(request: Request) -> dict:
    return await request.app.state.command_runner.run(_manager_command("test"))


@router.post("/pause-worker")
async def pause_worker(request: Request) -> dict:
    request.app.state.state_store.worker_paused = True
    return {"success": True, "worker_paused": True}


@router.post("/resume-worker")
async def resume_worker(request: Request) -> dict:
    request.app.state.state_store.worker_paused = False
    return {"success": True, "worker_paused": False}
