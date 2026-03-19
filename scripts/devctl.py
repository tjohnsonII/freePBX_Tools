from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / ".webscraper_manager" / "devctl"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_PATH = RUNTIME_DIR / "state.json"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8787
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3004
BACKEND_HEALTH = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
FRONTEND_HEALTH = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}/"
LOGIN_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"


@dataclass
class ServiceSpec:
    name: str
    cmd: list[str]
    cwd: Path
    port: int
    health_url: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"services": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("services", {})
            return payload
    except json.JSONDecodeError:
        pass
    return {"services": {}}


def _write_state(state: dict[str, Any]) -> None:
    _ensure_dirs()
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with url_request.urlopen(url, timeout=timeout) as response:
            return int(response.status) == 200
    except (url_error.URLError, TimeoutError, ValueError):
        return False


def _wait_for_health(url: str, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _http_ok(url):
            return True
        time.sleep(0.5)
    return _http_ok(url)


def _post_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = url_request.Request(url=url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with url_request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def _get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    with url_request.urlopen(url, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def _service_specs() -> dict[str, ServiceSpec]:
    py = sys.executable
    backend_cmd = [py, "-m", "uvicorn", "webscraper.ticket_api.app:app", "--host", BACKEND_HOST, "--port", str(BACKEND_PORT)]
    npm = "npm.cmd" if os.name == "nt" else "npm"
    frontend_cmd = [npm, "--prefix", "manager-ui", "run", "dev"]
    return {
        "backend": ServiceSpec("backend", backend_cmd, REPO_ROOT, BACKEND_PORT, BACKEND_HEALTH),
        "frontend": ServiceSpec("frontend", frontend_cmd, REPO_ROOT, FRONTEND_PORT, FRONTEND_HEALTH),
    }


def _start_service(name: str, timeout_s: int = 120) -> None:
    specs = _service_specs()
    spec = specs[name]
    state = _read_state()
    services = state.setdefault("services", {})
    existing = services.get(name, {})
    existing_pid = int(existing.get("pid", 0)) if str(existing.get("pid", "0")).isdigit() else 0
    if _is_alive(existing_pid) and _http_ok(spec.health_url):
        print(f"{name} already running pid={existing_pid} health=ok")
        return

    log_path = LOG_DIR / f"{name}.log"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            spec.cmd,
            cwd=str(spec.cwd),
            stdout=log_file,
            stderr=log_file,
            text=True,
            start_new_session=(os.name != "nt"),
        )

    services[name] = {
        "pid": proc.pid,
        "cmd": spec.cmd,
        "cwd": str(spec.cwd),
        "port": spec.port,
        "health_url": spec.health_url,
        "log": str(log_path),
        "started_at": _now_iso(),
    }
    _write_state(state)

    if not _wait_for_health(spec.health_url, timeout_s=timeout_s):
        raise RuntimeError(
            f"{name} failed readiness check. url={spec.health_url} pid={proc.pid} log={log_path}. "
            f"Run `python scripts/devctl.py logs --service {name}` for details."
        )
    print(f"{name} started pid={proc.pid} ready={spec.health_url}")


def _stop_service(name: str) -> None:
    state = _read_state()
    services = state.get("services", {})
    current = services.get(name, {})
    pid = int(current.get("pid", 0)) if str(current.get("pid", "0")).isdigit() else 0
    if pid <= 0:
        print(f"{name} not managed")
        return
    if _is_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
            else:
                os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    services.pop(name, None)
    _write_state(state)
    print(f"{name} stopped pid={pid}")


def cmd_doctor(_: argparse.Namespace) -> int:
    _ensure_dirs()
    checks = {
        "repo_root": REPO_ROOT.exists(),
        "backend_module": (REPO_ROOT / "webscraper" / "src" / "webscraper" / "ticket_api" / "app.py").exists(),
        "frontend_package": (REPO_ROOT / "manager-ui" / "package.json").exists(),
        "runtime_dir": RUNTIME_DIR.exists(),
    }
    failed = [name for name, ok in checks.items() if not ok]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 2


def cmd_start_backend(args: argparse.Namespace) -> int:
    _start_service("backend", timeout_s=args.timeout)
    return 0


def cmd_start_frontend(args: argparse.Namespace) -> int:
    _start_service("frontend", timeout_s=args.timeout)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    _start_service("backend", timeout_s=args.timeout)
    _start_service("frontend", timeout_s=args.timeout)
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    _stop_service("frontend")
    _stop_service("backend")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    return cmd_start(args)


def _service_status(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    pid = int(entry.get("pid", 0)) if str(entry.get("pid", "0")).isdigit() else 0
    alive = _is_alive(pid)
    health_url = str(entry.get("health_url") or "")
    health_ok = _http_ok(health_url) if health_url else False
    return {
        "service": name,
        "pid": pid,
        "alive": alive,
        "health_ok": health_ok,
        "port": entry.get("port"),
        "health_url": health_url,
        "log": entry.get("log"),
        "started_at": entry.get("started_at"),
    }


def cmd_status(_: argparse.Namespace) -> int:
    state = _read_state()
    statuses = [_service_status(name, entry) for name, entry in state.get("services", {}).items() if isinstance(entry, dict)]
    print(json.dumps({"services": statuses}, indent=2))
    failures = [item for item in statuses if not (item["alive"] and item["health_ok"])]
    return 0 if not failures else 1


def cmd_logs(args: argparse.Namespace) -> int:
    state = _read_state()
    services = state.get("services", {})
    selected = args.service or "backend"
    entry = services.get(selected, {}) if isinstance(services.get(selected), dict) else {}
    log_path = Path(entry.get("log") or (LOG_DIR / f"{selected}.log"))
    if not log_path.exists():
        print(f"log file missing: {log_path}")
        return 1
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-args.tail :]:
        print(line)
    return 0


def cmd_login(_: argparse.Namespace) -> int:
    webbrowser.open(LOGIN_URL, new=2)
    print(f"opened login page once: {LOGIN_URL}")
    return 0


def cmd_auth_check(_: argparse.Namespace) -> int:
    payload = _post_json(f"http://{BACKEND_HOST}:{BACKEND_PORT}/auth/check", {})
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("authenticated") or payload.get("ok") else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    payload = _post_json(
        f"http://{BACKEND_HOST}:{BACKEND_PORT}/jobs/ingest-handle",
        {"handle": args.handle, "ticket_limit": args.ticket_limit, "full": args.full},
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_timeline(args: argparse.Namespace) -> int:
    payload = _post_json(f"http://{BACKEND_HOST}:{BACKEND_PORT}/jobs/build-timeline", {"handle": args.handle})
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified dev supervisor for ticket scraping + KB timeline workflows")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")

    start = sub.add_parser("start")
    start.add_argument("--timeout", type=int, default=180)

    sb = sub.add_parser("start-backend")
    sb.add_argument("--timeout", type=int, default=120)

    sf = sub.add_parser("start-frontend")
    sf.add_argument("--timeout", type=int, default=180)

    sub.add_parser("stop")

    restart = sub.add_parser("restart")
    restart.add_argument("--timeout", type=int, default=180)

    sub.add_parser("status")

    logs = sub.add_parser("logs")
    logs.add_argument("--service", choices=["backend", "frontend"], default="backend")
    logs.add_argument("--tail", type=int, default=120)

    sub.add_parser("login")
    sub.add_parser("auth-check")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--handle", required=True)
    ingest.add_argument("--ticket-limit", type=int, default=50)
    ingest.add_argument("--full", action="store_true")

    timeline = sub.add_parser("timeline")
    timeline.add_argument("--handle", required=True)

    return parser


def main() -> int:
    _ensure_dirs()
    parser = build_parser()
    args = parser.parse_args()
    commands = {
        "doctor": cmd_doctor,
        "start": cmd_start,
        "start-backend": cmd_start_backend,
        "start-frontend": cmd_start_frontend,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "logs": cmd_logs,
        "login": cmd_login,
        "auth-check": cmd_auth_check,
        "ingest": cmd_ingest,
        "timeline": cmd_timeline,
    }
    try:
        return commands[args.command](args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
