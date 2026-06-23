from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/services", tags=["services"])

# ── friendly labels & groups for known services ───────────────────────────────
_LABELS: dict[str, str] = {
    "webscraper_manager_api":  "Manager API",
    "manager_ui_frontend":     "Manager UI",
    "webscraper_ticket_api":   "Ticket API",
    "webscraper_ticket_ui":    "Ticket UI",
    "webscraper_worker_service": "Scraper Worker",
    "homelab_network_mapping": "HomeLab Network",
    "traceroute_ui":           "Traceroute UI",
    "freepbx_web_manager":     "FreePBX Web Manager",
    "freepbx_deploy_backend":  "Deploy Backend",
}

_GROUPS: dict[str, str] = {
    "webscraper_manager_api":    "manager",
    "manager_ui_frontend":       "manager",
    "webscraper_ticket_api":     "scraper",
    "webscraper_ticket_ui":      "scraper",
    "webscraper_worker_service": "scraper",
    "homelab_network_mapping":   "extras",
    "traceroute_ui":             "extras",
    "freepbx_web_manager":       "extras",
    "freepbx_deploy_backend":    "extras",
}

# Fallback start commands when run_state.json has no entry for a service
_RESTART_FALLBACKS: dict[str, dict[str, Any]] = {
    "webscraper_manager_api": {
        "script": "scripts/run_web_manager_app.py", "args": [],
    },
    "manager_ui_frontend": {
        "script": "scripts/run_manager_ui_app.py", "args": [],
    },
    "webscraper_ticket_api": {
        "script": "scripts/run_all_web_apps.py", "args": ["--webscraper-mode", "api"],
    },
    "webscraper_ticket_ui": {
        "script": "scripts/run_all_web_apps.py", "args": ["--webscraper-mode", "ui"],
    },
    # webscraper_worker_service intentionally omitted — status comes from client heartbeat
}

LOG_LINES = 150
_FULL_RESTART_LOG = Path("/var/www/freePBX_Tools/var/logs/startup/full_restart_latest.log")


# ── helpers ───────────────────────────────────────────────────────────────────
def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _kill_pid(pid: int) -> None:
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _kill_port_pids(port: int) -> None:
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr and conn.laddr.port == port and conn.pid:
                try:
                    psutil.Process(conn.pid).kill()
                except Exception:
                    pass
    except Exception:
        pass


def _load_run_state(repo_root: Path) -> dict[str, Any]:
    state_path = repo_root / "var" / "web-app-launcher" / "run_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8")).get("services", {})
    except Exception:
        return {}


def _save_service_entry(repo_root: Path, name: str, entry: dict[str, Any]) -> None:
    state_path = repo_root / "var" / "web-app-launcher" / "run_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:
        existing = {}
    existing.setdefault("services", {})[name] = entry
    state_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _tail_log(path: str | None, n: int = LOG_LINES) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            return [l.rstrip("\n") for l in fh.readlines()[-n:]]
    except Exception:
        return []


# ── client heartbeat ──────────────────────────────────────────────────────────
def _fetch_client_heartbeats() -> list[dict[str, Any]]:
    try:
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:8788/api/clients", timeout=2) as r:
            import json as _json
            return _json.loads(r.read()).get("items", [])
    except Exception:
        return []


def _primary_client(heartbeats: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    """Return (most-recent active heartbeat, age_seconds). Active = seen within 600s."""
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc)
    for hb in heartbeats:
        try:
            seen = datetime.fromisoformat(hb.get("server_seen_utc", "").replace("Z", "+00:00"))
            age = (now - seen).total_seconds()
            if age < 600:
                return hb, age
        except Exception:
            pass
    return None, 9999


# ── system infra status ───────────────────────────────────────────────────────
def _system_services(heartbeats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    services = []

    # Apache
    try:
        r = subprocess.run(["systemctl", "is-active", "apache2"], capture_output=True, text=True)
        apache_up = r.stdout.strip() == "active"
    except Exception:
        apache_up = False
    services.append({
        "name": "apache", "label": "Apache (httpd)", "group": "system",
        "port": 80, "port_up": apache_up, "pid": None, "pid_alive": apache_up,
        "log": "/var/log/apache2/error.log", "started_at": None, "cmd": None,
    })

    # VPN — sourced from client heartbeat, not server interface
    client, _ = _primary_client(heartbeats)
    vpn_up = bool(client and client.get("vpn_connected"))
    vpn_ip = client.get("vpn_ip") if client else None
    services.append({
        "name": "vpn", "label": f"VPN{f' ({vpn_ip})' if vpn_ip else ''}",
        "group": "system", "port": None, "port_up": None,
        "pid": None, "pid_alive": vpn_up, "log": None, "started_at": None, "cmd": None,
    })

    return services


# ── main list ─────────────────────────────────────────────────────────────────
def _build_service_list(repo_root: Path) -> list[dict[str, Any]]:
    run_state = _load_run_state(repo_root)
    heartbeats = _fetch_client_heartbeats()
    client, client_age_s = _primary_client(heartbeats)
    services: list[dict[str, Any]] = []

    # All services tracked in run_state.json
    for name, entry in run_state.items():
        pid = int(entry.get("pid", 0) or 0)
        port: int | None = None
        url = entry.get("url", "")
        for seg in (entry.get("cmd") or []):
            if seg.isdigit() and 1000 < int(seg) < 65000:
                port = int(seg)
                break
        if not port and url:
            import re
            m = re.search(r":(\d{4,5})", url)
            if m:
                port = int(m.group(1))

        pid_alive = _is_pid_alive(pid) if pid else False
        port_up = _is_port_open(port) if port else None

        services.append({
            "name": name,
            "label": _LABELS.get(name, name.replace("_", " ").title()),
            "group": _GROUPS.get(name, "extras"),
            "pid": pid or None,
            "pid_alive": pid_alive,
            "port": port,
            "port_up": port_up,
            "log": entry.get("log"),
            "started_at": entry.get("started_at"),
            "cmd": entry.get("cmd"),
        })

    # Add any known services missing from run_state
    existing_names = {s["name"] for s in services}
    for name in _RESTART_FALLBACKS:
        if name not in existing_names:
            port_map = {"webscraper_manager_api": 8787, "manager_ui_frontend": 3004,
                        "webscraper_ticket_api": 8788, "webscraper_ticket_ui": 3005}
            port = port_map.get(name)
            services.append({
                "name": name,
                "label": _LABELS.get(name, name),
                "group": _GROUPS.get(name, "extras"),
                "pid": None, "pid_alive": False,
                "port": port, "port_up": _is_port_open(port) if port else None,
                "log": None, "started_at": None, "cmd": None,
            })

    # Scraper Worker — reflect client heartbeat status, not a local process
    worker_up = client_age_s < 120
    worker_status = client.get("status", "offline") if client else "offline"
    worker_label = f"Scraper Worker ({worker_status})" if client else "Scraper Worker"
    services.append({
        "name": "webscraper_worker_service",
        "label": worker_label,
        "group": "scraper",
        "pid": None, "pid_alive": worker_up,
        "port": None, "port_up": None,
        "log": None, "started_at": None, "cmd": None,
    })

    services.extend(_system_services(heartbeats))
    return services


# ── routes ────────────────────────────────────────────────────────────────────
@router.get("")
async def list_services(request: Request) -> dict:
    repo_root: Path = request.app.state.state_store.repo_root
    svcs = _build_service_list(repo_root)
    # group ordering for UI
    order = {"manager": 0, "scraper": 1, "extras": 2, "system": 3}
    svcs.sort(key=lambda s: (order.get(s["group"], 9), s["label"]))
    return {"services": svcs}


@router.post("/full-restart")
async def full_restart() -> dict:
    """Launch FULL_START.sh in background; returns immediately."""
    script = Path("/var/www/freePBX_Tools/FULL_START.sh")
    if not script.exists():
        raise HTTPException(status_code=404, detail="FULL_START.sh not found")
    _FULL_RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _FULL_RESTART_LOG.open("a", encoding="utf-8") as lf:
        lf.write(f"\n--- full-restart triggered at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ---\n")
        proc = subprocess.Popen(
            ["bash", str(script)],
            cwd="/var/www/freePBX_Tools",
            stdin=subprocess.DEVNULL,
            stdout=lf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return {"ok": True, "pid": proc.pid, "log": str(_FULL_RESTART_LOG)}


@router.post("/{name}/restart")
async def restart_service(name: str, request: Request) -> dict:
    repo_root: Path = request.app.state.state_store.repo_root

    # ── system services ───────────────────────────────────────────────────────
    if name == "apache":
        try:
            r = subprocess.run(["systemctl", "reload", "apache2"], capture_output=True)
            if r.returncode != 0:
                subprocess.run(["systemctl", "restart", "apache2"], check=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"ok": True, "service": "apache"}

    if name == "vpn":
        try:
            subprocess.run(["openvpn3", "session-manage", "--disconnect", "--config", "work"],
                           capture_output=True)
            time.sleep(2)
            subprocess.run(["openvpn3", "session-start", "--config", "work"], check=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"ok": True, "service": "vpn"}

    # ── web app services ──────────────────────────────────────────────────────
    run_state = _load_run_state(repo_root)
    entry = run_state.get(name, {})

    # Kill existing PID
    pid = int(entry.get("pid", 0) or 0)
    if pid:
        _kill_pid(pid)
        time.sleep(0.8)

    # Infer and clear port
    cmd_stored: list[str] | None = entry.get("cmd")
    cwd_stored: str | None = entry.get("cwd")
    port: int | None = None
    for seg in (cmd_stored or []):
        if seg.isdigit() and 1000 < int(seg) < 65000:
            port = int(seg)
            break
    if port and _is_port_open(port):
        _kill_port_pids(port)
        time.sleep(0.5)

    # Build command
    if cmd_stored and cwd_stored:
        cmd = cmd_stored
        cwd = Path(cwd_stored)
    elif name in _RESTART_FALLBACKS:
        defn = _RESTART_FALLBACKS[name]
        cmd = [sys.executable, str(repo_root / defn["script"])] + defn["args"]
        cwd = repo_root
    else:
        raise HTTPException(status_code=404, detail=f"No restart command known for: {name}")

    logs_dir = repo_root / "var" / "web-app-launcher" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{name}.log"

    with log_path.open("a", encoding="utf-8") as lf:
        lf.write(f"\n--- restart at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ---\n")
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=lf, stderr=subprocess.STDOUT, start_new_session=True,
        )

    new_entry: dict[str, Any] = {
        **entry,
        "service": name,
        "pid": proc.pid,
        "cmd": cmd,
        "command": " ".join(cmd),
        "cwd": str(cwd),
        "log": str(log_path),
        "started_at": int(time.time()),
    }
    _save_service_entry(repo_root, name, new_entry)

    return {
        "ok": True, "service": name,
        "label": _LABELS.get(name, name),
        "pid": proc.pid, "log": str(log_path),
    }


@router.get("/{name}/logs")
async def service_logs(name: str, request: Request, lines: int = LOG_LINES) -> dict:
    repo_root: Path = request.app.state.state_store.repo_root
    run_state = _load_run_state(repo_root)
    entry = run_state.get(name, {})
    log_path = entry.get("log")

    # System service special paths
    if name == "apache":
        log_path = "/var/log/apache2/error.log"
    if name == "full-restart":
        log_path = str(_FULL_RESTART_LOG)

    return {
        "service": name,
        "log": log_path,
        "lines": _tail_log(log_path, lines),
    }
