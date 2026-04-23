from __future__ import annotations

import os
import subprocess
from pathlib import Path

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
    """VPN, VNC, Chrome profile, and key service health at a glance."""
    # VPN — check for tun0 interface
    vpn_up = False
    vpn_ip = None
    try:
        addrs = psutil.net_if_addrs()
        for iface, addr_list in addrs.items():
            if iface.startswith("tun"):
                for a in addr_list:
                    if a.family.name == "AF_INET":
                        vpn_up = True
                        vpn_ip = a.address
    except Exception:
        pass

    # VNC — check for x11vnc on port 5900
    vnc_port = 5900
    vnc_pid = None
    vnc_all_interfaces = False
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr and conn.laddr.port == vnc_port:
                vnc_pid = conn.pid
                vnc_all_interfaces = conn.laddr.ip in ("0.0.0.0", "")
                break
    except Exception:
        pass

    # Chrome profile auth cookies
    chrome_profile = Path(os.getenv("WEBSCRAPER_CHROME_PROFILE_DIR", "/var/www/freePBX_Tools/webscraper/var/chrome-profile"))
    cookies_file = chrome_profile / "Default" / "Cookies"
    chrome_profile_ok = cookies_file.exists()
    try:
        cookies_age_days = int((os.path.getmtime(str(cookies_file)) and
                                (os.stat(str(cookies_file)).st_mtime > 0) and
                                ((__import__("time").time() - os.stat(str(cookies_file)).st_mtime) / 86400))) if chrome_profile_ok else -1
    except Exception:
        cookies_age_days = -1

    # Webscraper worker process
    worker_pid = None
    try:
        for p in psutil.process_iter(["pid", "cmdline"]):
            cmdline = " ".join(p.info.get("cmdline") or [])
            if "webscraper" in cmdline and "headless" in cmdline and "uvicorn" not in cmdline:
                worker_pid = p.info["pid"]
                break
    except Exception:
        pass

    return {
        "vpn": {"up": vpn_up, "ip": vpn_ip, "interface": "tun0"},
        "vnc": {"listening": vnc_pid is not None, "port": vnc_port, "pid": vnc_pid, "all_interfaces": vnc_all_interfaces},
        "chrome_profile": {"exists": chrome_profile_ok, "path": str(chrome_profile), "cookies_age_days": cookies_age_days},
        "worker": {"running": worker_pid is not None, "pid": worker_pid},
    }
