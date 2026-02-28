from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from webscraper_manager import __version__
from webscraper_manager.util.ports import describe_process, find_listening_pids, kill_process_tree, should_kill

try:
    import typer

    TYPER_AVAILABLE = True
except Exception:
    typer = None  # type: ignore[assignment]
    TYPER_AVAILABLE = False

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:
    Console = Any  # type: ignore[assignment]
    RICH_AVAILABLE = False

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DOCTOR_ISSUES = 10
EXIT_SERVICES_UNHEALTHY = 1
EXIT_TEST_FAILED = 30
EXIT_AUTH_FAILED = 40
MANAGER_RUNTIME_MODULES = ["typer", "rich", "psutil", "packaging"]

TITLE_TEXT = "FreePBX Webscraper Manager"
SUBTITLE_TEXT = "CLI manager for status, tests, auth, API checks, and start/stop"


@dataclass
class AppState:
    quiet: bool = False
    verbose: bool = False
    in_menu: bool = False
    pure_json_mode: bool = False
    clear_screen: bool = False
    use_preferred_python: bool = True


@dataclass
class Finding:
    check: str
    ok: bool
    details: str
    warning: bool = False


@dataclass
class TestStep:
    name: str
    ok: bool
    details: str
    duration_ms: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_repo_root() -> Path:
    return _repo_root()


def get_preferred_python(repo_root: Path) -> Path:
    first_choice = repo_root / ".venv-webscraper" / "Scripts" / "python.exe"
    if first_choice.is_file():
        return first_choice

    second_choice = repo_root / "webscraper" / ".venv" / "Scripts" / "python.exe"
    if second_choice.is_file():
        return second_choice

    return Path(sys.executable)


def is_running_in_preferred_python(repo_root: Path) -> bool:
    current = Path(sys.executable).resolve()
    preferred = get_preferred_python(repo_root).resolve()
    return current == preferred


def get_runtime_python(state: AppState, repo_root: Path) -> Path:
    if state.use_preferred_python:
        return get_preferred_python(repo_root)
    return Path(sys.executable)


def ensure_manager_dirs() -> tuple[Path, Path, Path]:
    root = find_repo_root()
    manager_dir = root / ".webscraper_manager"
    logs_dir = manager_dir / "logs"
    day_dir = logs_dir / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    return manager_dir, logs_dir, day_dir


def _services_config_path(root: Path) -> Path:
    return root / ".webscraper_manager" / "services.json"


def _run_state_path(root: Path) -> Path:
    return root / ".webscraper_manager" / "run_state.json"


def _default_services_config(root: Path) -> dict[str, Any]:
    return {
        "api": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8787,
            "target": "webscraper.ticket_api.app:app",
        },
        "ui": {
            "enabled": True,
            "cwd": "webscraper/ticket-ui",
            "port": 3000,
            "health_url": "http://127.0.0.1:3000",
            "cmd": ["npm.cmd", "run", "dev"],
        },
        "worker": {
            "enabled": False,
            "cwd": "webscraper",
            "cmd": ["python", "-m", "webscraper", "--mode", "headless"],
        },
    }


def _load_services_config(root: Path) -> dict[str, Any]:
    config_path = _services_config_path(root)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(json.dumps(_default_services_config(root), indent=2) + "\n", encoding="utf-8")
    services_cfg = json.loads(config_path.read_text(encoding="utf-8"))

    # Compatibility migration: historical config used "webscraper-ui" at repo root.
    ui_cfg = services_cfg.get("ui") if isinstance(services_cfg, dict) else None
    if isinstance(ui_cfg, dict):
        ui_cwd = str(ui_cfg.get("cwd", "")).strip().replace("\\", "/")
        migrated = False
        if ui_cwd in {"webscraper-ui", "ticket-ui"}:
            ui_cfg["cwd"] = "webscraper/ticket-ui"
            migrated = True
        ui_cmd = ui_cfg.get("cmd")
        if isinstance(ui_cmd, list) and ui_cmd in (["npm", "run", "dev"], ["npm", "run", "dev:local-api"], ["npm.cmd", "run", "dev:local-api"]):
            ui_cfg["cmd"] = ["npm.cmd", "run", "dev"]
            migrated = True
        if ui_cfg.get("health_url") != "http://127.0.0.1:3000":
            ui_cfg["health_url"] = "http://127.0.0.1:3000"
            migrated = True
        if migrated:
            config_path.write_text(json.dumps(services_cfg, indent=2) + "\n", encoding="utf-8")

    return services_cfg


def _load_run_state(root: Path) -> dict[str, Any]:
    state_path = _run_state_path(root)
    if not state_path.exists():
        return {}
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(loaded, dict):
        return {}

    # Legacy compatibility: flatten {"services": {...}} into top-level entries.
    legacy_services = loaded.get("services")
    if isinstance(legacy_services, dict):
        flattened: dict[str, Any] = {}
        for service_name in ("api", "ui", "worker"):
            if service_name in legacy_services and isinstance(legacy_services[service_name], dict):
                flattened[service_name] = legacy_services[service_name]
        return flattened
    return loaded


def _save_run_state(root: Path, run_state: dict[str, Any]) -> None:
    state_path = _run_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(run_state, indent=2) + "\n", encoding="utf-8")


def load_run_state() -> dict[str, Any]:
    return _load_run_state(find_repo_root())


def save_run_state(run_state: dict[str, Any]) -> None:
    _save_run_state(find_repo_root(), run_state)


def _is_pid_alive(pid: int | None, expected_cmd: list[str] | None = None) -> bool:
    import psutil

    if not pid or pid <= 0:
        return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        if expected_cmd:
            cmdline = proc.cmdline()
            if not cmdline:
                return False
            expected0 = Path(expected_cmd[0]).name.lower()
            actual0 = Path(cmdline[0]).name.lower()
            if expected0 and actual0 and expected0 != actual0:
                return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _is_port_open(host: str, port: int, timeout_s: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_s)
        return sock.connect_ex((host, port)) == 0


def is_port_open(host: str, port: int) -> bool:
    return _is_port_open(host, port)


def _api_ready(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/healthz"
    try:
        with urllib_request.urlopen(url, timeout=2.0) as response:
            return int(response.status) == 200
    except (urllib_error.URLError, TimeoutError, ValueError):
        return False


def http_health_ok(url: str) -> bool:
    try:
        import httpx  # type: ignore[import-not-found]

        with httpx.Client(timeout=2.0) as client:
            return int(client.get(url).status_code) == 200
    except Exception:
        try:
            with urllib_request.urlopen(url, timeout=2.0) as response:
                return int(response.status) == 200
        except (urllib_error.URLError, TimeoutError, ValueError):
            return False


def _creation_flags_for_service() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return 0


def _stop_pid(pid: int) -> tuple[bool, str]:
    try:
        proc = subprocess.Popen(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) if os.name == "nt" else None
        if proc is not None:
            proc.communicate(timeout=5)
            return True, "terminated"
    except Exception:
        pass

    try:
        os.kill(pid, 15)
    except OSError:
        return True, "already-dead"

    deadline = time.time() + 5
    while time.time() < deadline:
        if not _is_pid_alive(pid):
            return True, "terminated"
        time.sleep(0.2)

    try:
        os.kill(pid, 9)
        return True, "killed"
    except OSError as exc:
        return False, f"failed: {exc}"


def _resolve_service_cwd(root: Path, service_cfg: dict[str, Any]) -> Path:
    cwd_value = str(service_cfg.get("cwd", "."))
    cwd_path = Path(cwd_value)
    if not cwd_path.is_absolute():
        cwd_path = root / cwd_path
    return cwd_path


def resolve_runner(runner: str) -> str | None:
    """Resolve a package runner executable that subprocess/CreateProcess can execute."""
    if os.name != "nt":
        found = shutil.which(runner)
        return str(Path(found).resolve()) if found else None

    if runner.lower() == "npm":
        cmd_candidate = shutil.which("npm.cmd")
        if cmd_candidate:
            return str(Path(cmd_candidate).resolve())

        appdata = os.environ.get("AppData") or os.environ.get("APPDATA") or ""
        fallbacks = [
            r"E:\DevTools\nodejs\npm.cmd",
            r"C:\Program Files\nodejs\npm.cmd",
        ]
        if appdata:
            fallbacks.append(str(Path(appdata) / "npm" / "npm.cmd"))

        for candidate in fallbacks:
            if Path(candidate).is_file():
                return str(Path(candidate).resolve())

    found = shutil.which(runner)
    if found and not found.lower().endswith(".ps1"):
        return str(Path(found).resolve())
    return None


def resolve_npm_cmd() -> str | None:
    """Resolve npm.cmd on Windows without triggering PowerShell npm.ps1 policy issues."""
    env_override = (os.environ.get("NPM_CMD") or "").strip().strip('"')
    if env_override:
        env_path = Path(env_override)
        if env_path.is_file():
            return str(env_path.resolve())

    from_path = shutil.which("npm.cmd")
    if from_path:
        return str(Path(from_path).resolve())

    fallbacks = [
        Path(r"E:\DevTools\nodejs\npm.cmd"),
        Path(r"C:\Program Files\nodejs\npm.cmd"),
    ]
    for candidate in fallbacks:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def resolve_node_executable() -> str | None:
    found = shutil.which("node")
    if not found:
        return None
    return str(Path(found).resolve())


def _has_ps1_runner_only(runner: str) -> bool:
    if os.name != "nt":
        return False
    ps1 = shutil.which(f"{runner}.ps1")
    cmd = shutil.which(f"{runner}.cmd")
    exe = shutil.which(f"{runner}.exe")
    return bool(ps1 and not cmd and not exe)


def _get_service_port(_service_name: str, cfg: dict[str, Any]) -> int | None:
    raw_port = cfg.get("port")
    if raw_port in (None, ""):
        return None
    try:
        return int(raw_port)
    except (TypeError, ValueError):
        return None


def _wait_for_tcp(host: str, port: int, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.25)
    return _is_port_open(host, port)


def _ensure_webscraper_runtime_dirs(root: Path) -> dict[str, Path]:
    webscraper_var_dir = root / "webscraper" / "var"
    runtime_dir = webscraper_var_dir / "runtime"
    logs_dir = webscraper_var_dir / "logs"
    auth_dir = webscraper_var_dir / "auth"
    chrome_profile_dir = webscraper_var_dir / "chrome-profile"
    edge_profile_dir = webscraper_var_dir / "edge-profile"

    for directory in (runtime_dir, logs_dir, auth_dir, chrome_profile_dir, edge_profile_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return {
        "var": webscraper_var_dir,
        "runtime": runtime_dir,
        "logs": logs_dir,
        "auth": auth_dir,
        "chrome_profile": chrome_profile_dir,
        "edge_profile": edge_profile_dir,
        "pids": runtime_dir / "pids.json",
    }


def _webscraper_runtime_paths(root: Path) -> tuple[Path, Path]:
    runtime_paths = _ensure_webscraper_runtime_dirs(root)
    return runtime_paths["pids"], runtime_paths["logs"]


def _load_webscraper_pids(root: Path) -> dict[str, Any]:
    pids_path, _ = _webscraper_runtime_paths(root)
    if not pids_path.exists():
        return {}
    try:
        payload = json.loads(pids_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        print(f"Warning: invalid JSON in pid state file {pids_path}; treating as empty state.")
        return {}


def _save_webscraper_pids(root: Path, payload: dict[str, Any]) -> None:
    pids_path, _ = _webscraper_runtime_paths(root)
    pids_path.parent.mkdir(parents=True, exist_ok=True)
    pids_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _wait_for_health(url: str, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if http_health_ok(url):
            return True
        time.sleep(0.5)
    return http_health_ok(url)


def _listening_pid_for_port(port: int) -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]

        for conn in psutil.net_connections(kind="inet"):
            laddr = getattr(conn, "laddr", None)
            if conn.status != "LISTEN" or not laddr:
                continue
            if int(getattr(laddr, "port", 0)) == int(port) and conn.pid:
                return int(conn.pid)
    except Exception:
        return None
    return None


def _find_worker_pid() -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]

        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = [str(part).lower() for part in (proc.info.get("cmdline") or [])]
            if "-m" in cmdline and "webscraper" in cmdline and "--mode" in cmdline:
                return int(proc.info.get("pid") or 0) or None
    except Exception:
        return None
    return None


def _shutdown_webscraper_children(root: Path, pids: dict[str, Any], reason: str) -> list[str]:
    messages: list[str] = []
    for name in ("worker", "ui", "api"):
        entry = pids.get(name, {}) if isinstance(pids.get(name), dict) else {}
        pid = int(entry.get("pid", 0)) if str(entry.get("pid", "0")).isdigit() else 0
        if pid <= 0:
            continue
        ok, detail = _stop_pid(pid)
        messages.append(f"{name}: {detail if ok else f'failed {detail}'} pid={pid} ({reason})")
        if ok:
            pids.pop(name, None)
    _save_webscraper_pids(root, pids)
    return messages


def _print_line(state: AppState, console: Console | None, message: str) -> None:
    if state.quiet:
        return
    (console.print(message) if console is not None else print(message))


def _preflight_kill_ports(
    state: AppState,
    console: Console | None,
    ports: list[int],
    *,
    kill_ports: bool,
    kill_scope: str,
) -> tuple[bool, str | None]:
    scope = str(kill_scope or "repo").strip().lower()
    repo_root = find_repo_root()
    if scope not in {"repo", "safe", "force"}:
        return False, f"Invalid --kill-scope value '{kill_scope}'. Expected: repo|safe|force"

    for port in ports:
        listener_pids = sorted(find_listening_pids(port))
        for pid in listener_pids:
            meta = describe_process(pid)
            cmdline = str(meta.get("cmdline_text") or "")
            name = str(meta.get("name") or "<unknown>")
            _print_line(state, console, f"[PORT] {port} in use by PID={pid} name={name} cmdline=\"{cmdline}\"")
            if not kill_ports:
                return False, f"Port {port} already in use and --kill-ports disabled. Stop PID {pid} or use --kill-ports."
            if not should_kill(pid, scope, repo_root):
                return (
                    False,
                    (
                        f"Refusing to kill PID {pid} on port {port}: does not match --kill-scope={scope}. "
                        "Use --kill-scope force to override."
                    ),
                )

            _print_line(state, console, f"[PORT] killing PID={pid} (scope={scope})")
            try:
                kill_process_tree(pid)
            except Exception as exc:
                return False, f"Failed killing PID {pid} on port {port}: {exc}. Resolve process and retry."

            if find_listening_pids(port):
                return False, f"Port {port} still has listeners after kill attempt. Resolve manually and retry."

    return True, None


def _start_webscraper_stack(
    state: AppState,
    console: Console | None,
    detach: bool = False,
    *,
    kill_ports: bool = True,
    kill_scope: str = "repo",
) -> int:
    root = find_repo_root()
    _ensure_webscraper_runtime_dirs(root)
    doctor_code, _ = run_doctor(console, state, json_out=False)
    if doctor_code != EXIT_OK:
        return doctor_code

    preferred_python = get_runtime_python(state, root)
    if not preferred_python.is_file():
        msg = f"Preferred Python was not found: {preferred_python}"
        if not state.quiet:
            (console.print(msg) if console is not None else print(msg))
        return EXIT_USAGE

    api_port = 8787
    ui_port = 3004
    kill_ok, kill_error = _preflight_kill_ports(
        state,
        console,
        [ui_port, api_port],
        kill_ports=kill_ports,
        kill_scope=kill_scope,
    )
    if not kill_ok:
        _print_line(state, console, str(kill_error))
        return EXIT_SERVICES_UNHEALTHY

    _, logs_dir = _webscraper_runtime_paths(root)
    pids = _load_webscraper_pids(root)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    stop_on_worker_exit = os.environ.get("WEBSCRAPER_STACK_STOP_ON_WORKER_EXIT", "0") == "1"
    strict_ui = os.environ.get("WEBSCRAPER_STACK_STRICT_UI", "0") == "1"
    auth_mode = (os.environ.get("WEBSCRAPER_AUTH_MODE") or "").strip().lower()
    seed_auth_enabled = os.environ.get("WEBSCRAPER_SEED_AUTH_AUTO", "0") == "1" or auth_mode in {"auto", "profile"}

    services = {
        "api": {
            "cmd": [str(preferred_python), "-m", "uvicorn", "webscraper.ticket_api.app:app", "--host", "127.0.0.1", "--port", "8787"],
            "cwd": root,
            "health": "http://127.0.0.1:8787/health",
        },
        "ui": {
            "cmd": [resolve_npm_cmd() or "npm.cmd", "run", "dev:ui"],
            "cwd": root / "webscraper" / "ticket-ui",
            "health": "http://127.0.0.1:3004",
            "env": {
                "PORT": "3004",
                "TICKET_API_PROXY_TARGET": "http://127.0.0.1:8787",
                "NEXT_PUBLIC_TICKET_API_PROXY_TARGET": "http://127.0.0.1:8787",
            },
        },
        "worker": {
            "cmd": [str(preferred_python), "-m", "webscraper", "--mode", "incremental"],
            "cwd": root,
            "health": None,
        },
    }

    monitored_pids: dict[str, int] = {}
    ui_skipped = False

    for name in ("api", "ui", "worker"):
        if name == "worker" and seed_auth_enabled:
            _print_line(state, console, "[AUTH] auto/profile auth mode detected. Running blocking seed-auth before worker start.")
            auth_code = run_seed_auth(state, json_out=False)
            if auth_code != EXIT_OK:
                _print_line(state, console, "[AUTH] seed-auth failed; aborting stack start.")
                return auth_code
        if name == "ui" and _is_port_open("127.0.0.1", 3004):
            ui_skipped = True
            if not state.quiet:
                message = "UI port 3004 already in use. Skipping UI start."
                (console.print(message) if console is not None else print(message))
            continue
        existing = pids.get(name, {}) if isinstance(pids.get(name), dict) else {}
        pid = int(existing.get("pid", 0)) if str(existing.get("pid", "0")).isdigit() else 0
        if _is_pid_alive(pid):
            monitored_pids[name] = pid
            continue
        log_path = logs_dir / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        service_env = env.copy()
        service_env.update(services[name].get("env", {}))
        if detach:
            with log_path.open("a", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    services[name]["cmd"],
                    cwd=str(services[name]["cwd"]),
                    env=service_env,
                    stdout=log_file,
                    stderr=log_file,
                    text=True,
                    creationflags=_creation_flags_for_service(),
                )
        else:
            proc = subprocess.Popen(
                services[name]["cmd"],
                cwd=str(services[name]["cwd"]),
                env=service_env,
                stdout=None,
                stderr=None,
                text=True,
                creationflags=_creation_flags_for_service(),
            )
        pids[name] = {"pid": proc.pid, "log": str(log_path), "cmd": services[name]["cmd"], "started_at": datetime.now().isoformat(timespec="seconds")}
        monitored_pids[name] = proc.pid
        _save_webscraper_pids(root, pids)
        if name == "api" and not _wait_for_health("http://127.0.0.1:8787/health", 45):
            return EXIT_SERVICES_UNHEALTHY
        if name == "ui" and not _wait_for_health("http://127.0.0.1:3004", 60):
            if strict_ui:
                return EXIT_SERVICES_UNHEALTHY
            ui_skipped = True
            pids.pop("ui", None)
            monitored_pids.pop("ui", None)
            _save_webscraper_pids(root, pids)
            if not state.quiet:
                message = (
                    "UI failed health check; WEBSCRAPER_STACK_STRICT_UI=0 so worker/API will remain running"
                )
                (console.print(message) if console is not None else print(message))
            continue
        if name == "worker":
            time.sleep(2)
            if not _is_pid_alive(proc.pid):
                return EXIT_SERVICES_UNHEALTHY

    if not _wait_for_health("http://127.0.0.1:8787/health", 5):
        return EXIT_SERVICES_UNHEALTHY
    if not ui_skipped and not _wait_for_health("http://127.0.0.1:3004", 5):
        return EXIT_SERVICES_UNHEALTHY

    if not state.quiet:
        started_message = "webscraper stack started"
        (console.print(started_message) if console is not None else print(started_message))
    if detach:
        return EXIT_OK

    try:
        while True:
            for name, pid in list(monitored_pids.items()):
                if not _is_pid_alive(pid):
                    message = f"{name} exited unexpectedly (pid={pid})"
                    if not state.quiet:
                        (console.print(message) if console is not None else print(message))
                    if name == "worker" and not stop_on_worker_exit:
                        keep_alive_message = (
                            "worker exited; WEBSCRAPER_STACK_STOP_ON_WORKER_EXIT=0 so API/UI will remain running"
                        )
                        if not state.quiet:
                            (console.print(keep_alive_message) if console is not None else print(keep_alive_message))
                        monitored_pids.pop(name, None)
                        pids.pop(name, None)
                        _save_webscraper_pids(root, pids)
                        continue
                    if name == "ui" and not strict_ui:
                        keep_alive_message = (
                            "ui exited; WEBSCRAPER_STACK_STRICT_UI=0 so worker/API will remain running"
                        )
                        if not state.quiet:
                            (console.print(keep_alive_message) if console is not None else print(keep_alive_message))
                        monitored_pids.pop(name, None)
                        pids.pop(name, None)
                        _save_webscraper_pids(root, pids)
                        continue
                    if not state.quiet:
                        for row in _shutdown_webscraper_children(root, pids, reason=f"{name}-exited"):
                            (console.print(row) if console is not None else print(row))
                    else:
                        _shutdown_webscraper_children(root, pids, reason=f"{name}-exited")
                    return EXIT_SERVICES_UNHEALTHY
            time.sleep(0.5)
    except KeyboardInterrupt:
        stopped = _shutdown_webscraper_children(root, pids, reason="ctrl-c")
        if not state.quiet:
            for row in stopped:
                (console.print(row) if console is not None else print(row))
        return EXIT_OK
    return EXIT_OK


def _stop_webscraper_stack(state: AppState, console: Console | None) -> int:
    root = find_repo_root()
    pids = _load_webscraper_pids(root)
    messages: list[str] = []

    discovered = {
        "api": _listening_pid_for_port(8787),
        "ui": _listening_pid_for_port(3004),
        "worker": _find_worker_pid(),
    }

    for name in ("worker", "ui", "api"):
        entry = pids.get(name, {}) if isinstance(pids.get(name), dict) else {}
        pid = int(entry.get("pid", 0)) if str(entry.get("pid", "0")).isdigit() else 0
        if pid <= 0:
            pid = int(discovered.get(name) or 0)
        if pid <= 0:
            continue
        ok, detail = _stop_pid(pid)
        messages.append(f"{name}: {detail if ok else f'failed {detail}'}")
        pids.pop(name, None)
    _save_webscraper_pids(root, pids)
    if not state.quiet:
        for row in messages or ["webscraper stack already stopped"]:
            (console.print(row) if console is not None else print(row))
    return EXIT_OK


def _status_webscraper_stack(state: AppState, console: Console | None) -> int:
    root = find_repo_root()
    pids = _load_webscraper_pids(root)
    api_listening = _is_port_open("127.0.0.1", 8787)
    ui_listening = _is_port_open("127.0.0.1", 3004)
    worker_pid = _find_worker_pid()
    worker_running = bool(worker_pid and _is_pid_alive(worker_pid))

    rows = [
        f"api: port 8787 {'listening' if api_listening else 'not-listening'}",
        f"ui: port 3004 {'listening' if ui_listening else 'not-listening'}",
        f"worker: {'running' if worker_running else 'not-running'} pid={worker_pid or '-'}",
        f"state file: {(_webscraper_runtime_paths(root)[0])}",
        f"state entries: {', '.join(sorted(pids.keys())) if pids else 'none'}",
    ]
    if not state.quiet:
        for row in rows:
            (console.print(row) if console is not None else print(row))
    return EXIT_OK if (api_listening and ui_listening and worker_running) else EXIT_SERVICES_UNHEALTHY


def _is_service_enabled(name: str, cfg: dict[str, Any]) -> bool:
    if name != "worker":
        return bool(cfg.get("enabled", False))
    if "enabled" in cfg:
        return bool(cfg.get("enabled"))
    return bool(cfg.get("cmd"))


def _normalize_service_selector(service: str | None) -> list[str]:
    valid = ("api", "ui", "worker")
    if service is None or service == "all":
        return list(valid)
    if service not in valid:
        raise ValueError(f"Unsupported service '{service}'. Choose one of: {', '.join(valid)}")
    return [service]


def _service_has_missing_cwd(service_name: str, cfg: dict[str, Any], root: Path) -> tuple[bool, Path | None]:
    if service_name == "api":
        return False, None
    cwd = _resolve_service_cwd(root, cfg)
    return not cwd.exists(), cwd


def _service_health_status(
    service_name: str,
    cfg: dict[str, Any],
    state_entry: dict[str, Any],
) -> dict[str, Any]:
    root = find_repo_root()
    enabled = _is_service_enabled(service_name, cfg)
    pid = int(state_entry.get("pid", 0)) if str(state_entry.get("pid", "0")).isdigit() else 0
    cmd = [str(part) for part in state_entry.get("cmd", [])] if isinstance(state_entry.get("cmd"), list) else None
    alive = _is_pid_alive(pid, expected_cmd=cmd)

    host = str(cfg.get("host", "127.0.0.1"))
    port = _get_service_port(service_name, cfg)
    port_open = bool(port and _is_port_open(host, port))
    managed = bool(state_entry)
    unmanaged = not managed and port_open
    healthz_ok = _api_ready(host, port) if service_name == "api" and port else None
    missing_cwd, missing_cwd_path = _service_has_missing_cwd(service_name, cfg, root)

    if not enabled:
        healthy = True
    elif missing_cwd:
        healthy = False
    elif service_name == "api":
        healthy = bool(port_open and healthz_ok)
    elif service_name == "ui":
        healthy = port_open
    else:
        healthy = alive

    return {
        "enabled": enabled,
        "pid": pid if managed else None,
        "alive": alive,
        "port": port,
        "port_open": port_open,
        "managed": managed,
        "unmanaged": unmanaged,
        "healthz_ok": healthz_ok,
        "log": str(state_entry.get("log", "-")) if managed else "-",
        "healthy": healthy,
        "missing_cwd": missing_cwd,
        "missing_cwd_path": str(missing_cwd_path) if missing_cwd_path else None,
    }


def _format_ui_start_error(cwd: Path, cmd: list[str], npm_cmd_path: str | None) -> str:
    npm_display = npm_cmd_path or "not found"
    return (
        "ui: failed to start (WinError 2 / command not found). "
        f"cwd={cwd} cmd={cmd} npm.cmd={npm_display}. "
        "Suggestion: run `E:\\DevTools\\nodejs\\npm.cmd install` in ticket-ui."
    )


def _resolve_ui_start_command(cfg: dict[str, Any], cwd: Path) -> tuple[list[str] | None, str | None, str | None]:
    raw_cmd = [str(part) for part in cfg.get("cmd", [])]
    if not raw_cmd:
        raw_cmd = ["npm.cmd", "run", "dev"]

    npm_cmd_path = resolve_npm_cmd()
    if not npm_cmd_path:
        return None, None, "ui: cannot start because npm.cmd was not found (set NPM_CMD or add npm.cmd to PATH)."

    # Always use npm.cmd on Windows to avoid execution-policy issues with npm.ps1.
    command = [npm_cmd_path]
    if len(raw_cmd) > 1:
        command.extend(raw_cmd[1:])
    else:
        command.extend(["run", "dev"])

    return command, npm_cmd_path, None


def _start_services(state: AppState, console: Console | None, service: str | None = None) -> int:
    root = find_repo_root()
    manager_dir, _, day_dir = ensure_manager_dirs()
    del manager_dir
    services_cfg = _load_services_config(root)
    run_state = _load_run_state(root)

    preferred_python = get_runtime_python(state, root)
    summary: list[str] = []

    failed_services: list[str] = []
    all_services_mode = service in (None, "all")
    api_failed = False

    try:
        selected_services = _normalize_service_selector(service)
    except ValueError as exc:
        if console is not None and not state.quiet:
            console.print(str(exc))
        elif not state.quiet:
            print(str(exc))
        return EXIT_USAGE

    for service_name in selected_services:
        cfg = services_cfg.get(service_name, {})
        if not _is_service_enabled(service_name, cfg):
            summary.append(f"{service_name}: disabled")
            continue

        existing = run_state.get(service_name, {}) if isinstance(run_state.get(service_name, {}), dict) else {}
        existing_pid = int(existing.get("pid", 0)) if str(existing.get("pid", "0")).isdigit() else 0
        host = str(cfg.get("host", "127.0.0.1"))
        port = _get_service_port(service_name, cfg)
        expected_cmd = [str(part) for part in existing.get("cmd", [])] if isinstance(existing.get("cmd"), list) else None
        alive = _is_pid_alive(existing_pid, expected_cmd=expected_cmd)
        port_open = bool(port and _is_port_open(host, port))

        if alive:
            summary.append(f"{service_name}: already running (managed pid={existing_pid})")
            run_state[service_name] = existing
            continue

        if port_open:
            summary.append(f"{service_name}: running-unmanaged (port {port} already open)")
            continue

        npm_cmd_path: str | None = None
        if service_name == "api":
            target = str(cfg.get("target", "webscraper.ticket_api.app:app"))
            cmd = [str(preferred_python), "-m", "uvicorn", target, "--host", host, "--port", str(port or 8787)]
            cwd = root
        else:
            cmd = [str(part) for part in cfg.get("cmd", [])]
            if cmd and cmd[0] in {"python", "py", "python3"}:
                cmd[0] = str(preferred_python)
            cwd = _resolve_service_cwd(root, cfg)

            if service_name == "ui":
                cwd = root / "webscraper" / "ticket-ui"
                cmd, npm_cmd_path, ui_cmd_error = _resolve_ui_start_command(cfg, cwd)
                if ui_cmd_error:
                    summary.append(ui_cmd_error)
                    failed_services.append(service_name)
                    continue
                summary.append(f"ui: npm.cmd resolved to {npm_cmd_path}")
                summary.append(f"ui: launching command {cmd} (cwd={cwd})")
            elif not cmd:
                summary.append(f"{service_name}: missing cmd")
                failed_services.append(service_name)
                if service_name == "api":
                    api_failed = True
                continue

        if not cwd.exists():
            if service_name == "ui":
                summary.append(
                    f"ui: UI working directory not found at {cwd}. "
                    "Set ui.cwd to 'webscraper/ticket-ui' in .webscraper_manager/services.json"
                )
            else:
                summary.append(f"{service_name}: cwd not found ({cwd})")
            run_state.pop(service_name, None)
            failed_services.append(service_name)
            if service_name == "api":
                api_failed = True
            continue

        log_path = day_dir / f"{service_name}_{datetime.now().strftime('%H%M%S')}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    env=os.environ.copy(),
                    stdout=log_file,
                    stderr=log_file,
                    text=True,
                    creationflags=_creation_flags_for_service(),
                )
        except FileNotFoundError:
            if service_name == "ui":
                summary.append(_format_ui_start_error(cwd=cwd, cmd=cmd, npm_cmd_path=npm_cmd_path))
            else:
                summary.append(f"{service_name}: failed to start. cmd={cmd} cwd={cwd}")
            failed_services.append(service_name)
            if service_name == "api":
                api_failed = True
            continue
        except OSError as exc:
            if service_name == "ui":
                summary.append(
                    f"ui: failed to start ({exc}). cwd={cwd} cmd={cmd} npm.cmd={npm_cmd_path or 'not found'}. "
                    "Suggestion: run `E:\\DevTools\\nodejs\\npm.cmd install` in ticket-ui."
                )
            else:
                summary.append(f"{service_name}: failed to start. cmd={cmd} cwd={cwd} err={exc}")
            failed_services.append(service_name)
            if service_name == "api":
                api_failed = True
            continue

        run_state[service_name] = {
            "pid": proc.pid,
            "cmd": cmd,
            "cwd": str(cwd),
            "log": str(log_path),
            "port": port,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        summary.append(f"{service_name}: started pid={proc.pid} log={log_path}")

        ready = False
        if service_name == "api" and port:
            ready = _wait_for_tcp(host, port, timeout_s=10.0) and _api_ready(host, port)
        elif service_name == "ui" and port:
            ready = _wait_for_tcp(host, port, timeout_s=30.0)
        else:
            time.sleep(3)
            ready = _is_pid_alive(proc.pid, expected_cmd=cmd)

        if not ready:
            summary.append(f"{service_name}: readiness failed")
            if service_name != "api":
                ok, detail = _stop_pid(proc.pid)
                summary.append(f"{service_name}: cleanup after failed readiness ({detail if ok else detail})")
                run_state.pop(service_name, None)
            failed_services.append(service_name)
            if service_name == "api":
                api_failed = True
            continue

    _save_run_state(root, run_state)

    if console is not None and not state.quiet:
        for row in summary:
            console.print(row)
    elif not state.quiet:
        for row in summary:
            print(row)
    if all_services_mode:
        if api_failed:
            return EXIT_SERVICES_UNHEALTHY
        return EXIT_OK
    return EXIT_OK if not failed_services else EXIT_SERVICES_UNHEALTHY


def _service_status_rows(state: AppState, service: str | None = None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    root = find_repo_root()
    services_cfg = _load_services_config(root)
    run_state = _load_run_state(root)
    rows: list[dict[str, str]] = []
    all_enabled_healthy = True

    selected_services = _normalize_service_selector(service)

    for service_name in selected_services:
        cfg = services_cfg.get(service_name, {})
        existing = run_state.get(service_name, {}) if isinstance(run_state.get(service_name), dict) else {}
        status = _service_health_status(service_name, cfg, existing)
        if status["enabled"] and not status["healthy"]:
            all_enabled_healthy = False
        if status["missing_cwd"]:
            process_status = "failed (missing cwd)"
        else:
            process_status = "unmanaged" if status["unmanaged"] else "running" if status["alive"] else "dead"
        port_status = "open" if status["port_open"] else ("closed" if status["port"] else "n/a")
        if status["missing_cwd"]:
            port_status = "n/a"
        rows.append(
            {
                "service": service_name,
                "enabled": "yes" if status["enabled"] else "no",
                "managed": "yes" if status["managed"] else ("unmanaged" if status["unmanaged"] else "no"),
                "pid": str(status["pid"]) if status["pid"] else "-",
                "process": process_status,
                "port": port_status,
                "healthz": "ok" if status["healthz_ok"] else ("fail" if service_name == "api" and status["enabled"] else "n/a"),
                "log": status["log"] if not status["missing_cwd"] else f"missing cwd: {status['missing_cwd_path']}",
                "healthy": "yes" if status["healthy"] else "no",
            }
        )

    return rows, {"run_state": run_state, "all_enabled_healthy": all_enabled_healthy}


def _print_service_status(state: AppState, console: Console | None, service: str | None = None) -> int:
    try:
        rows, status_meta = _service_status_rows(state, service=service)
    except ValueError as exc:
        if console is not None and not state.quiet:
            console.print(str(exc))
        elif not state.quiet:
            print(str(exc))
        return EXIT_USAGE
    if console is None or not sys.stdout.isatty():
        for row in rows:
            print(
                f"{row['service']}: enabled={row['enabled']} managed={row['managed']} pid={row['pid']} "
                f"alive={row['process']} port={row['port']} healthz={row['healthz']} log={row['log']} healthy={row['healthy']}"
            )
        return EXIT_OK if status_meta.get("all_enabled_healthy") else EXIT_SERVICES_UNHEALTHY

    table = Table(title="Managed services", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Service", no_wrap=True)
    table.add_column("Enabled", no_wrap=True)
    table.add_column("Managed", no_wrap=True)
    table.add_column("PID", no_wrap=True)
    table.add_column("Alive", no_wrap=True)
    table.add_column("Port", no_wrap=True)
    table.add_column("Healthz", no_wrap=True)
    table.add_column("Log", overflow="fold")
    table.add_column("Healthy", no_wrap=True)
    for row in rows:
        table.add_row(
            row["service"],
            row["enabled"],
            row["managed"],
            row["pid"],
            row["process"],
            row["port"],
            row["healthz"],
            row["log"],
            row["healthy"],
        )
    console.print(table)
    return EXIT_OK if status_meta.get("all_enabled_healthy") else EXIT_SERVICES_UNHEALTHY


def _stop_services(state: AppState, console: Console | None, service: str | None = None) -> int:
    root = find_repo_root()
    services_cfg = _load_services_config(root)
    run_state = _load_run_state(root)
    messages: list[str] = []

    try:
        selected = _normalize_service_selector(service)
    except ValueError as exc:
        if console is not None and not state.quiet:
            console.print(str(exc))
        elif not state.quiet:
            print(str(exc))
        return EXIT_USAGE
    stop_order = [name for name in ("worker", "ui", "api") if name in selected]

    for service_name in stop_order:
        cfg = services_cfg.get(service_name, {})
        existing = run_state.get(service_name, {}) if isinstance(run_state.get(service_name), dict) else {}
        pid = int(existing.get("pid", 0)) if str(existing.get("pid", "0")).isdigit() else 0
        if not pid:
            host = str(cfg.get("host", "127.0.0.1"))
            port = _get_service_port(service_name, cfg)
            if port and _is_port_open(host, port):
                messages.append(f"{service_name}: running-unmanaged on port {port}; not stopping")
            else:
                messages.append(f"{service_name}: not managed")
            continue
        ok, detail = _stop_pid(pid)
        if ok:
            run_state.pop(service_name, None)
        else:
            run_state[service_name] = existing
        messages.append(f"{service_name}: {detail} pid={pid}")

    _save_run_state(root, run_state)

    if console is not None and not state.quiet:
        for message in messages:
            console.print(message)
    elif not state.quiet:
        for message in messages:
            print(message)
    return EXIT_OK


def start_ticket_api(state: AppState, console: Console | None) -> int:
    root = find_repo_root()
    host = "127.0.0.1"
    port = 8787
    health_url = f"http://{host}:{port}/healthz"
    python_exe = get_runtime_python(state, root)

    if is_port_open(host, port):
        message = f"Ticket API already running on {host}:{port}; not starting another process."
        if not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_OK

    _, _, day_dir = ensure_manager_dirs()
    log_path = day_dir / f"ticket_api_{datetime.now().strftime('%H%M%S')}.log"
    cmd = [
        str(python_exe),
        "-m",
        "uvicorn",
        "webscraper.ticket_api.app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=_creation_flags_for_service(),
        )

    deadline = time.time() + 10
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        if http_health_ok(health_url):
            ready = True
            break
        time.sleep(0.25)

    if not ready:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        message = f"Ticket API failed readiness check within 10s (GET {health_url}). See log: {log_path}"
        if not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_TEST_FAILED

    run_state = load_run_state()
    run_state["ticket_api"] = {
        "pid": proc.pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "port": port,
        "log": str(log_path),
    }
    save_run_state(run_state)

    message = f"Ticket API started (pid={proc.pid}) on {host}:{port}; log={log_path}"
    if not state.quiet:
        (console.print(message) if console is not None else print(message))
    return EXIT_OK


def stop_ticket_api(state: AppState, console: Console | None) -> int:
    import psutil

    host = "127.0.0.1"
    port = 8787
    run_state = load_run_state()
    api_state = run_state.get("ticket_api") if isinstance(run_state, dict) else None
    managed_pid = int(api_state.get("pid", 0)) if isinstance(api_state, dict) and str(api_state.get("pid", "0")).isdigit() else 0

    if not managed_pid:
        if is_port_open(host, port):
            message = "Ticket API is running but unmanaged (no manager PID found); refusing to kill unknown process."
        else:
            message = "Ticket API is not running (no managed PID)."
        if not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_OK

    try:
        proc = psutil.Process(managed_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        run_state.pop("ticket_api", None)
        save_run_state(run_state)
        message = f"Managed Ticket API PID {managed_pid} is already stopped; state cleaned."
        if not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_OK

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except psutil.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    run_state.pop("ticket_api", None)
    save_run_state(run_state)
    message = f"Stopped managed Ticket API (pid={managed_pid})."
    if not state.quiet:
        (console.print(message) if console is not None else print(message))
    return EXIT_OK


def status_ticket_api(state: AppState, console: Console | None) -> int:
    host = "127.0.0.1"
    port = 8787
    health_url = f"http://{host}:{port}/healthz"
    run_state = load_run_state()
    api_state = run_state.get("ticket_api") if isinstance(run_state, dict) else None
    managed = isinstance(api_state, dict)
    pid = int(api_state.get("pid", 0)) if managed and str(api_state.get("pid", "0")).isdigit() else 0
    log_path = str(api_state.get("log", "-")) if managed else "-"
    listening = is_port_open(host, port)
    health_ok = http_health_ok(health_url)

    lines = [
        f"Ticket API managed: {'yes' if managed else 'no'}",
        f"pid: {pid if pid else '-'}",
        f"port {port} listening: {'yes' if listening else 'no'}",
        f"healthz: {'ok' if health_ok else 'fail'}",
        f"log: {log_path}",
    ]

    if managed and pid and not _is_pid_alive(pid):
        lines.append("note: managed PID is not alive")
    elif listening and not managed:
        lines.append("note: running but unmanaged")

    if console is not None and not state.quiet:
        for line in lines:
            console.print(line)
    elif not state.quiet:
        for line in lines:
            print(line)
    return EXIT_OK


def run_subprocess(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def write_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def run_auth_check(state: AppState, json_out: bool = False) -> int:
    root = find_repo_root()
    console = get_console(state)
    python_exe = get_runtime_python(state, root)
    script_path = root / "webscraper" / "scripts" / "auth_probe.py"
    if not script_path.exists():
        message = f"Auth probe script not found: {script_path}"
        if json_out:
            print(json.dumps({"ok": False, "error": message}, indent=2))
        elif not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_AUTH_FAILED

    cmd = [str(python_exe), str(script_path), "--json"]
    rc, out, err = run_subprocess(cmd, cwd=root, timeout=90)
    payload: dict[str, Any]
    try:
        payload = json.loads(out or "{}")
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "Invalid JSON output from auth probe",
            "stdout": out,
            "stderr": err,
            "returncode": rc,
        }

    if json_out:
        print(json.dumps(payload, indent=2))
    elif not state.quiet:
        requests_result = payload.get("requests") if isinstance(payload, dict) else None
        selenium_result = payload.get("selenium") if isinstance(payload, dict) else None
        ok = bool(payload.get("ok")) if isinstance(payload, dict) else False
        lines = [
            f"Auth check overall: {'PASS' if ok else 'FAIL'}",
            f"Requests probe: {requests_result.get('ok') if isinstance(requests_result, dict) else 'n/a'}",
            f"Selenium probe: {selenium_result.get('ok') if isinstance(selenium_result, dict) else 'n/a'}",
            f"Recommended method: {payload.get('recommended_method', 'n/a') if isinstance(payload, dict) else 'n/a'}",
        ]
        for line in lines:
            (console.print(line) if console is not None else print(line))

    return EXIT_OK if bool(payload.get("ok")) else EXIT_AUTH_FAILED


def run_seed_auth(state: AppState, json_out: bool = False) -> int:
    root = find_repo_root()
    console = get_console(state)
    python_exe = get_runtime_python(state, root)
    script_path = root / "webscraper" / "scripts" / "seed_and_fetch.py"
    if not script_path.exists():
        message = f"Seed auth script not found: {script_path}"
        if json_out:
            print(json.dumps({"ok": False, "error": message}, indent=2))
        elif not state.quiet:
            (console.print(message) if console is not None else print(message))
        return EXIT_AUTH_FAILED

    browser = (os.environ.get("WEBSCRAPER_BROWSER") or "edge").strip().lower()
    if browser not in {"edge", "chrome"}:
        browser = "edge"
    cmd = [str(python_exe), str(script_path), "--browser", browser]
    rc, out, err = run_subprocess(cmd, cwd=root, timeout=900)

    status_code = None
    authenticated = None
    output_path = None
    for line in (out or "").splitlines():
        if line.startswith("status_code:"):
            status_code = line.split(":", 1)[1].strip()
        elif line.startswith("authenticated:"):
            authenticated = line.split(":", 1)[1].strip().lower() == "true"
        elif line.startswith("output:"):
            output_path = line.split(":", 1)[1].strip()

    ok = bool(rc == 0 and authenticated)
    payload = {
        "ok": ok,
        "status_code": status_code,
        "authenticated": bool(authenticated),
        "output": output_path,
        "returncode": rc,
        "stderr": err.strip(),
    }

    if json_out:
        print(json.dumps(payload, indent=2))
    elif not state.quiet:
        lines = [
            f"Seed auth overall: {'PASS' if ok else 'FAIL'}",
            f"status_code: {status_code if status_code is not None else 'n/a'}",
            f"authenticated: {'true' if authenticated else 'false'}",
            f"output: {output_path or 'n/a'}",
        ]
        for line in lines:
            (console.print(line) if console is not None else print(line))
        if err.strip() and state.verbose:
            (console.print(err.strip()) if console is not None else print(err.strip()))

    return EXIT_OK if ok else EXIT_AUTH_FAILED




def run_auth_doctor(state: AppState, json_out: bool = False) -> int:
    root = find_repo_root()
    console = get_console(state)
    python_exe = get_runtime_python(state, root)
    cmd = [
        str(python_exe),
        "-c",
        "import json; from webscraper.auth.cookie_seeder import auth_doctor; print(json.dumps(auth_doctor(), indent=2))",
    ]
    rc, out, err = run_subprocess(cmd, cwd=root, timeout=30)
    if rc != 0:
        payload = {"ok": False, "error": err.strip() or out.strip() or "auth doctor failed"}
    else:
        try:
            payload = json.loads(out or "{}")
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "Invalid auth doctor JSON", "stdout": out, "stderr": err}

    if json_out:
        print(json.dumps(payload, indent=2))
    elif not state.quiet:
        checks = payload.get("checks", []) if isinstance(payload, dict) else []
        (console.print if console else print)(f"Auth doctor overall: {'PASS' if payload.get('ok') else 'FAIL'}")
        for check in checks:
            if not isinstance(check, dict):
                continue
            status = "PASS" if check.get("ok") else "FAIL"
            line = f"- {check.get('check')}: {status} ({check.get('value') or '-'})"
            (console.print if console else print)(line)
        fixes = payload.get("fixes", []) if isinstance(payload, dict) else []
        for fix in fixes:
            (console.print if console else print)(f"  fix: {fix}")

    return EXIT_OK if bool(payload.get("ok")) else EXIT_AUTH_FAILED

def get_console(state: AppState) -> Console | None:
    if not RICH_AVAILABLE:
        return None
    no_color = bool(os.environ.get("NO_COLOR"))
    return Console(no_color=no_color)


def should_print_banner(state: AppState, json_out: bool, is_help: bool) -> bool:
    if is_help:
        return False
    if state.in_menu:
        return False
    if state.quiet:
        return False
    if json_out:
        return False
    return True


def print_banner(console: Console | None) -> None:
    if console is None:
        print(f"{TITLE_TEXT}\n{SUBTITLE_TEXT}")
        return

    title = Text(TITLE_TEXT, style="bold cyan", justify="center")
    subtitle = Text(SUBTITLE_TEXT, style="bright_black", justify="center")
    banner_body = Text.assemble(title, "\n", subtitle)
    console.print(
        Panel(
            banner_body,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 3),
            expand=True,
        )
    )


def print_findings_table(console: Console | None, findings: list[Finding]) -> None:
    if console is None:
        for finding in findings:
            if finding.warning:
                symbol = "WARN"
            else:
                symbol = "OK" if finding.ok else "FAIL"
            print(f"{finding.check}: {symbol} - {finding.details}")
        return

    table = Table(title="Doctor Checks", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Details", style="bright_black")

    for finding in findings:
        if finding.warning:
            status = "[yellow]⚠️ WARN[/yellow]"
        else:
            status = "[green]✅ OK[/green]" if finding.ok else "[red]❌ FAIL[/red]"
        table.add_row(finding.check, status, finding.details)

    console.print(table)


def print_result_panel(console: Console | None, ok: bool, message: str) -> None:
    if console is None:
        print(message)
        return

    final_style = "green" if ok else "red"
    console.print(
        Panel(
            Text(message, justify="center", style=f"bold {final_style}"),
            border_style=final_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _doctor_findings() -> list[Finding]:
    root = _repo_root()
    current_python = Path(sys.executable)
    preferred_python = get_preferred_python(root)
    manager_python = root / ".venv-web-manager" / "Scripts" / "python.exe"
    matches_preferred = is_running_in_preferred_python(root)
    run_hint = f"Run with: {preferred_python} -m webscraper_manager ..."
    manager_requirements = root / "webscraper_manager" / "requirements.txt"
    ui_dir = root / "webscraper" / "ticket-ui"
    ui_package_json = ui_dir / "package.json"
    ui_next_dir = ui_dir / "node_modules" / "next"
    legacy_manager_dir_candidates = [
        root / "webscraper-manager",
        root / "_legacy_webscraper_manager_old",
        root / "webscraper-manager-old",
        root / "webscraper_manager_old",
    ]
    existing_legacy_manager_dirs = [path for path in legacy_manager_dir_candidates if path.exists() and path.is_dir()]
    runtime_dir = root / "webscraper" / "var" / "runtime"
    logs_dir = root / "webscraper" / "var" / "logs"
    runtime_was_missing = not runtime_dir.is_dir()
    logs_was_missing = not logs_dir.is_dir()
    _ensure_webscraper_runtime_dirs(root)
    manager_deps_missing: list[str] = []

    for module in MANAGER_RUNTIME_MODULES:
        try:
            __import__(module)
        except ImportError:
            manager_deps_missing.append(module)

    if manager_deps_missing:
        dep_ok = False
        dep_details = f"Missing imports: {', '.join(manager_deps_missing)}"
    else:
        dep_ok = True
        dep_details = "All manager runtime dependencies importable"

    preferred_pip_check_ok = True
    preferred_pip_check_details = "Skipped: preferred webscraper python not found"
    if preferred_python.is_file():
        cmd = [str(preferred_python), "-m", "pip", "check"]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
            output = (completed.stdout or completed.stderr or "").strip()
            preferred_pip_check_ok = completed.returncode == 0
            preferred_pip_check_details = output or ("pip check passed" if preferred_pip_check_ok else "pip check failed")
        except Exception as exc:
            preferred_pip_check_ok = False
            preferred_pip_check_details = f"pip check failed to run: {exc}"

    import_probe_ok = True
    import_probe_details = "Skipped: preferred webscraper python not found"
    npm_cmd_path = resolve_npm_cmd()
    npm_cmd_ok = bool(npm_cmd_path)
    npm_cmd_details = npm_cmd_path or "npm.cmd not found (set NPM_CMD or install Node.js)"
    ui_ps1_only = _has_ps1_runner_only("npm")

    node_path = resolve_node_executable()
    node_ok = bool(node_path)
    node_details = node_path or "node not found in PATH"
    node_version_ok = False
    node_version_details = "Skipped: node executable not found"
    if node_path:
        try:
            node_version = subprocess.run([node_path, "-v"], capture_output=True, text=True, timeout=10, check=False)
            node_version_ok = node_version.returncode == 0
            node_version_details = (node_version.stdout or node_version.stderr or "").strip() or "node -v produced no output"
        except Exception as exc:
            node_version_ok = False
            node_version_details = f"node -v failed: {exc}"

    if preferred_python.is_file():
        probe_cmd = [str(preferred_python), "-c", "import selenium, bs4, lxml, requests, multipart"]
        try:
            probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=20, check=False)
            import_probe_ok = probe.returncode == 0
            if import_probe_ok:
                import_probe_details = "selenium/bs4/lxml/requests/python-multipart import check passed"
            else:
                combined = (probe.stderr or probe.stdout or "import check failed").strip()
                import_probe_details = combined.splitlines()[-1] if combined else "import check failed"
        except Exception as exc:
            import_probe_ok = False
            import_probe_details = f"import check failed to run: {exc}"

    ui_next_ok = ui_next_dir.is_dir()
    ui_next_details = (
        f"Found {ui_next_dir}"
        if ui_next_ok
        else f"Missing {ui_next_dir}. Run `E:\\DevTools\\nodejs\\npm.cmd install` in {ui_dir}"
    )

    return [
        Finding("repo_root", root.exists(), f"Found repo root at {root}"),
        Finding(
            "manager_requirements",
            manager_requirements.is_file(),
            f"Expected file: {manager_requirements}",
        ),
        Finding(
            "manager_venv_python",
            manager_python.is_file(),
            f"Expected file: {manager_python}",
        ),
        Finding(
            "webscraper_dir",
            (root / "webscraper").is_dir(),
            f"Expected directory: {root / 'webscraper'}",
        ),
        Finding(
            "webscraper_requirements",
            (root / "webscraper" / "requirements.txt").is_file(),
            f"Expected file: {root / 'webscraper' / 'requirements.txt'}",
        ),
        Finding(
            "webscraper_runtime_dir",
            runtime_dir.is_dir(),
            (
                f"Created missing runtime directory: {runtime_dir}"
                if runtime_was_missing and runtime_dir.is_dir()
                else f"Runtime directory ready: {runtime_dir}"
            ),
        ),
        Finding(
            "webscraper_logs_dir",
            logs_dir.is_dir(),
            (
                f"Created missing logs directory: {logs_dir}"
                if logs_was_missing and logs_dir.is_dir()
                else f"Logs directory ready: {logs_dir}"
            ),
        ),
        Finding("ui_dir", ui_dir.is_dir(), f"Expected directory: {ui_dir}"),
        Finding("ui_package_json", ui_package_json.is_file(), f"Expected file: {ui_package_json}"),
        Finding("node_executable", node_ok, node_details),
        Finding("node_version", node_version_ok, node_version_details),
        Finding("npm_cmd", npm_cmd_ok, npm_cmd_details),
        Finding(
            "ui_runner_ps1_only",
            ok=not ui_ps1_only,
            details=(
                "Only npm.ps1 found (blocked by execution policy on many domain-joined Windows hosts)"
                if ui_ps1_only
                else "npm.cmd/.exe available or npm runner not ps1-only"
            ),
            warning=ui_ps1_only,
        ),
        Finding("ui_next_dependency", ui_next_ok, ui_next_details),
        Finding("current_python", True, str(current_python)),
        Finding("preferred_python", True, str(preferred_python)),
        Finding(
            "preferred_python_exists",
            preferred_python.is_file(),
            f"Expected file: {preferred_python}",
        ),
        Finding("manager_runtime_deps", dep_ok, dep_details),
        Finding(
            "legacy_manager_dirs",
            not existing_legacy_manager_dirs,
            (
                "No legacy/duplicate manager directories found"
                if not existing_legacy_manager_dirs
                else "Legacy/duplicate manager directory found: "
                + "; ".join(str(path) for path in existing_legacy_manager_dirs)
                + " (keep only webscraper_manager to avoid ambiguity)"
            ),
            warning=bool(existing_legacy_manager_dirs),
        ),
        Finding(
            "webscraper_pip_check",
            preferred_pip_check_ok,
            preferred_pip_check_details,
            warning=not preferred_pip_check_ok,
        ),
        Finding(
            "webscraper_import_probe",
            import_probe_ok,
            import_probe_details,
            warning=not import_probe_ok,
        ),
        Finding(
            "python_matches_preferred",
            ok=matches_preferred,
            details="Current interpreter matches preferred interpreter" if matches_preferred else run_hint,
            warning=not matches_preferred,
        ),
    ]


def run_doctor(console: Console | None, state: AppState, json_out: bool) -> tuple[int, dict[str, Any] | None]:
    findings = _doctor_findings()
    ok = all(finding.ok or finding.warning for finding in findings)
    payload = {
        "ok": ok,
        "findings": [asdict(finding) for finding in findings],
    }

    if json_out:
        print(json.dumps(payload, indent=2))
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), payload

    if state.quiet:
        print("Doctor checks passed." if ok else "Doctor checks found issues.")
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None

    print_findings_table(console, findings)

    if state.verbose:
        message = f"Verbose: evaluated {len(findings)} checks from root: {_repo_root()}"
        if console is None:
            print(message)
        else:
            console.print(f"[bright_black]{message}[/bright_black]")

    final_message = "Doctor checks passed." if ok else "Doctor checks found issues."
    print_result_panel(console, ok, final_message)
    return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None


def _make_step(name: str, ok: bool, details: str, started: float) -> TestStep:
    return TestStep(name=name, ok=ok, details=details, duration_ms=int((time.time() - started) * 1000))


def _is_port_open(host: str, port: int, timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _run_scraper_cli_probe(root: Path, timeout: int, python_exe: Path) -> tuple[bool, str, list[str]]:
    webscraper_dir = root / "webscraper"
    commands_tried: list[str] = []
    if (webscraper_dir / "__main__.py").is_file():
        cmd = [str(python_exe), "-m", "webscraper", "--help"]
        commands_tried.append(" ".join(cmd))
        rc, out, err = run_subprocess(cmd, cwd=root, timeout=timeout)
        text = (out + "\n" + err).strip()
        return rc == 0, text or "Ran webscraper module --help", commands_tried

    if (webscraper_dir / "ultimate_scraper.py").is_file():
        dry_cmd = [str(python_exe), "ultimate_scraper.py", "--dry-run"]
        help_cmd = [str(python_exe), "ultimate_scraper.py", "--help"]
        for cmd in (dry_cmd, help_cmd):
            commands_tried.append(" ".join(cmd))
            rc, out, err = run_subprocess(cmd, cwd=webscraper_dir, timeout=timeout)
            text = (out + "\n" + err).strip()
            if rc == 0:
                return True, text or f"Ran {' '.join(cmd[1:])}", commands_tried

        return False, "webscraper CLI probe failed for --dry-run/--help", commands_tried

    return True, "No webscraper CLI module detected; skipped", commands_tried


def _select_pytest_cwd(root: Path) -> Path:
    webscraper_dir = root / "webscraper"
    if webscraper_dir.is_dir():
        if (webscraper_dir / "tests").is_dir():
            return webscraper_dir
        if (webscraper_dir / "pyproject.toml").is_file() or (webscraper_dir / "pytest.ini").is_file():
            return webscraper_dir
    return root


def ensure_webscraper_editable_installed(python_exe: str, repo_root: Path) -> None:
    """Ensure ``webscraper`` is importable in the same interpreter used for pytest."""
    resolved_root = repo_root.resolve()
    resolved_python = str(Path(python_exe).resolve())
    editable_path = (resolved_root / "webscraper").resolve()
    env = os.environ.copy()
    pytest_cwd = _select_pytest_cwd(resolved_root).resolve()
    log_lines: list[str] = [
        f"python_exe: {resolved_python}",
        f"editable_install_path: {editable_path}",
        f"import_check_cwd: {pytest_cwd}",
    ]
    commands: list[str] = []

    check_cmd = [resolved_python, "-c", "import webscraper; print(webscraper.__file__)"]
    commands.append(" ".join(check_cmd))
    try:
        check_completed = subprocess.run(
            check_cmd,
            cwd=str(pytest_cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Python executable not found: {resolved_python}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while checking webscraper import") from exc

    if check_completed.returncode == 0:
        log_lines.append("webscraper import OK")
        if check_completed.stdout.strip():
            log_lines.append(f"import stdout: {check_completed.stdout.strip()}")
        if check_completed.stderr.strip():
            log_lines.append(f"import stderr: {check_completed.stderr.strip()}")
        ensure_webscraper_editable_installed._last_run = (log_lines, commands)  # type: ignore[attr-defined]
        return

    install_cmd = [resolved_python, "-m", "pip", "install", "-e", str(editable_path)]
    commands.append(" ".join(install_cmd))
    log_lines.append("webscraper missing; installing editable")
    try:
        install_completed = subprocess.run(
            install_cmd,
            cwd=str(pytest_cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Python executable not found: {resolved_python}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while running editable install for webscraper") from exc

    try:
        recheck_completed = subprocess.run(
            check_cmd,
            cwd=str(pytest_cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Python executable not found: {resolved_python}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while re-checking webscraper import") from exc

    commands.append(" ".join(check_cmd))
    if install_completed.stdout.strip():
        log_lines.append(f"install stdout: {install_completed.stdout.strip()}")
    if install_completed.stderr.strip():
        log_lines.append(f"install stderr: {install_completed.stderr.strip()}")
    if recheck_completed.stdout.strip():
        log_lines.append(f"recheck stdout: {recheck_completed.stdout.strip()}")
    if recheck_completed.stderr.strip():
        log_lines.append(f"recheck stderr: {recheck_completed.stderr.strip()}")

    if recheck_completed.returncode != 0:
        ensure_webscraper_editable_installed._last_run = (log_lines, commands)  # type: ignore[attr-defined]
        raise RuntimeError(
            "Unable to import 'webscraper' after editable install with "
            f"python={resolved_python} path={editable_path}. "
            f"install stdout:\n{install_completed.stdout}\n"
            f"install stderr:\n{install_completed.stderr}\n"
            f"import stdout:\n{recheck_completed.stdout}\n"
            f"import stderr:\n{recheck_completed.stderr}"
        )

    log_lines.append("webscraper import OK")
    ensure_webscraper_editable_installed._last_run = (log_lines, commands)  # type: ignore[attr-defined]


def _run_pytest_step(path: str | None, timeout: int, python_exe: Path) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    root = find_repo_root()
    commands: list[str] = []
    cmd = [str(python_exe), "-m", "pytest", "-q"]
    if path:
        cmd.append(path)
    commands.append(" ".join(cmd))

    cwd = _select_pytest_cwd(root)
    try:
        rc, out, err = run_subprocess(cmd, cwd=cwd, timeout=timeout)
        ok = rc == 0
        details = (out + "\n" + err).strip() or f"pytest finished rc={rc}"
        if (not ok) and "cannot import name" in details and " from " in details:
            details = (
                f"{details}\n"
                "Hint: Test expects API that doesn't exist. Either update tests or add shim."
            )
        step = _make_step("pytest", ok, details, started)
        return step, details, commands
    except FileNotFoundError:
        step = _make_step("pytest", False, "Python executable not found for pytest", started)
        return step, step.details, commands
    except subprocess.TimeoutExpired:
        step = _make_step("pytest", False, f"pytest timed out after {timeout}s", started)
        return step, step.details, commands


def _check_test_dependencies(
    python_exe: Path,
    timeout: int,
    auto_fix: bool,
    root: Path,
) -> tuple[TestStep, list[str], bool]:
    started = time.time()
    commands: list[str] = []
    check_cmd = [str(python_exe), "-c", "import httpx"]
    commands.append(" ".join(check_cmd))

    try:
        rc, _, _ = run_subprocess(check_cmd, cwd=root, timeout=timeout)
    except subprocess.TimeoutExpired:
        step = _make_step("test deps check", False, f"Dependency check timed out after {timeout}s", started)
        return step, commands, False
    except FileNotFoundError:
        step = _make_step("test deps check", False, "Python executable not found for dependency check", started)
        return step, commands, False

    if rc == 0:
        step = _make_step("test deps check", True, "Required test dependency found: httpx", started)
        return step, commands, True

    print("Missing test dependency: httpx")
    print("Run: webscraper_manager fix test-deps")

    if not auto_fix:
        step = _make_step(
            "test deps check",
            False,
            "Missing test dependency: httpx. Run: webscraper_manager fix test-deps",
            started,
        )
        return step, commands, False

    install_step, install_logs, install_commands = _install_test_dependencies(python_exe=python_exe, timeout=timeout, root=root)
    commands.extend(install_commands)
    if install_step.ok:
        step = _make_step("test deps check", True, "Missing dependencies were auto-installed", started)
        commands.extend([f"install-log: {line}" for line in install_logs])
        return step, commands, True

    step = _make_step("test deps check", False, f"Auto-fix failed: {install_step.details}", started)
    commands.extend([f"install-log: {line}" for line in install_logs])
    return step, commands, False


def _install_test_dependencies(python_exe: Path, timeout: int, root: Path) -> tuple[TestStep, list[str], list[str]]:
    started = time.time()
    cmd = [str(python_exe), "-m", "pip", "install", "httpx", "pytest"]
    commands = [" ".join(cmd)]
    log_lines: list[str] = []
    try:
        rc, out, err = run_subprocess(cmd, cwd=root, timeout=timeout)
        if out.strip():
            log_lines.append(out.strip())
        if err.strip():
            log_lines.append(err.strip())
        ok = rc == 0
        details = "Installed pytest/httpx" if ok else f"pip install failed rc={rc}"
        return _make_step("fix test dependencies", ok, details, started), log_lines, commands
    except subprocess.TimeoutExpired:
        step = _make_step("fix test dependencies", False, f"pip install timed out after {timeout}s", started)
        return step, log_lines, commands
    except FileNotFoundError:
        step = _make_step("fix test dependencies", False, "Python executable not found for pip install", started)
        return step, log_lines, commands


def _run_fix_test_deps(state: AppState, timeout: int = 300) -> tuple[int, list[TestStep], Path]:
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"fix_test_deps_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)

    step, logs, commands = _install_test_dependencies(python_exe=python_exe, timeout=timeout, root=root)
    log_lines = ["command: fix test-deps", f"python: {python_exe}"]
    log_lines.extend(f"subprocess: {cmd}" for cmd in commands)
    log_lines.extend(logs)
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(step.details)
        print(f"Log file: {log_path}")

    return (EXIT_OK if step.ok else EXIT_TEST_FAILED), [step], log_path


def _run_fix_deps(state: AppState, timeout: int = 300, run_pip_check: bool = True) -> tuple[int, list[TestStep], Path]:
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"fix_deps_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)
    requirements_path = root / "webscraper_manager" / "requirements.txt"
    steps: list[TestStep] = []
    log_lines = ["command: fix deps", f"python: {python_exe}", f"requirements: {requirements_path}"]

    if not requirements_path.is_file():
        step = TestStep("fix deps", False, f"Missing requirements file: {requirements_path}", 0)
        steps.append(step)
        write_log(log_path, "\n".join(log_lines + [step.details]) + "\n")
        if not state.quiet:
            print(step.details)
            print(f"Log file: {log_path}")
        return EXIT_TEST_FAILED, steps, log_path

    started = time.time()
    install_cmd = [str(python_exe), "-m", "pip", "install", "-r", str(requirements_path)]
    log_lines.append(f"subprocess: {' '.join(install_cmd)}")
    rc, out, err = run_subprocess(install_cmd, cwd=root, timeout=timeout)
    if out.strip():
        log_lines.append(out.strip())
    if err.strip():
        log_lines.append(err.strip())
    install_ok = rc == 0
    steps.append(_make_step("fix deps", install_ok, "Installed manager requirements" if install_ok else f"pip install failed rc={rc}", started))

    if install_ok and run_pip_check:
        check_started = time.time()
        check_cmd = [str(python_exe), "-m", "pip", "check"]
        log_lines.append(f"subprocess: {' '.join(check_cmd)}")
        check_rc, check_out, check_err = run_subprocess(check_cmd, cwd=root, timeout=timeout)
        if check_out.strip():
            log_lines.append(check_out.strip())
        if check_err.strip():
            log_lines.append(check_err.strip())
        steps.append(_make_step("pip check", check_rc == 0, "pip check passed" if check_rc == 0 else f"pip check failed rc={check_rc}", check_started))

    write_log(log_path, "\n".join(log_lines) + "\n")
    overall_ok = all(step.ok for step in steps)
    if not state.quiet:
        print("fix deps completed." if overall_ok else "fix deps found issues.")
        for step in steps:
            status = "OK" if step.ok else "FAIL"
            print(f"- {step.name}: {status} ({step.details})")
        print(f"Log file: {log_path}")

    return (EXIT_OK if overall_ok else EXIT_TEST_FAILED), steps, log_path


def _run_import_probe_step(timeout: int, python_exe: Path, root: Path, verbose: bool) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    modules = ["selenium", "bs4", "lxml", "requests", "websocket"]
    commands: list[str] = []
    bulk_cmd = [
        str(python_exe),
        "-c",
        "import selenium, bs4, lxml, requests, websocket",
    ]
    commands.append(" ".join(bulk_cmd))

    log_lines: list[str] = []

    def _error_summary(stdout: str, stderr: str, rc: int) -> str:
        candidates = [line.strip() for line in (stderr.splitlines() + stdout.splitlines()) if line.strip()]
        if candidates:
            return candidates[-1]
        return f"Command failed with exit code {rc}"

    try:
        rc, out, err = run_subprocess(bulk_cmd, cwd=root, timeout=timeout)
    except subprocess.TimeoutExpired:
        step = _make_step("python dependency imports", False, f"Dependency probe timed out after {timeout}s", started)
        return step, step.details, commands

    log_lines.append(f"bulk-import rc={rc}")
    if out.strip():
        log_lines.append("bulk-import stdout:")
        log_lines.append(out.strip())
    if err.strip():
        log_lines.append("bulk-import stderr:")
        log_lines.append(err.strip())

    if rc == 0:
        details = "All required imports succeeded"
        return _make_step("python dependency imports", True, details, started), "\n".join(log_lines), commands

    failures: list[str] = []
    traceback_chunks: list[str] = []
    for module in modules:
        module_cmd = [str(python_exe), "-c", f"import {module}"]
        commands.append(" ".join(module_cmd))
        try:
            module_rc, module_out, module_err = run_subprocess(module_cmd, cwd=root, timeout=timeout)
        except subprocess.TimeoutExpired:
            failures.append(f"{module}: TimeoutExpired: import timed out after {timeout}s")
            log_lines.append(f"probe {module} rc=timeout")
            continue

        log_lines.append(f"probe {module} rc={module_rc}")
        if module_out.strip():
            log_lines.append(f"probe {module} stdout:")
            log_lines.append(module_out.strip())
        if module_err.strip():
            log_lines.append(f"probe {module} stderr:")
            log_lines.append(module_err.strip())

        if module_rc != 0:
            failures.append(f"{module}: {_error_summary(module_out, module_err, module_rc)}")
            if module_err.strip():
                traceback_chunks.append(f"[{module}]\n{module_err.strip()}")

    if not failures:
        fallback_error = _error_summary(out, err, rc)
        failures.append(f"bulk import command failed: {fallback_error}")

    details = f"Missing/failed imports: {'; '.join(failures)}"
    if verbose and traceback_chunks:
        details = f"{details}\n" + "\n\n".join(traceback_chunks)

    log_lines.append("failure-summary:")
    log_lines.append(details)
    return _make_step("python dependency imports", False, details, started), "\n".join(log_lines), commands


def _run_smoke_steps(timeout: int, verbose: bool, python_exe: Path) -> tuple[list[TestStep], list[str], list[str]]:
    root = find_repo_root()
    steps: list[TestStep] = []
    logs: list[str] = [f"[python] using {python_exe}"]
    commands: list[str] = []

    started = time.time()
    findings = _doctor_findings()
    ok = all(f.ok or f.warning for f in findings)
    details = "; ".join(f"{f.check}={'warn' if f.warning else ('ok' if f.ok else 'fail')}" for f in findings)
    steps.append(_make_step("doctor", ok, details, started))
    logs.append(f"[doctor] {details}")

    dep_step, dep_details, dep_commands = _run_import_probe_step(timeout=timeout, python_exe=python_exe, root=root, verbose=verbose)
    steps.append(dep_step)
    commands.extend(dep_commands)
    logs.append(f"[deps] {dep_details}")

    started = time.time()
    cli_ok, cli_details, cli_commands = _run_scraper_cli_probe(root, timeout=timeout, python_exe=python_exe)
    commands.extend(cli_commands)
    steps.append(_make_step("webscraper CLI probe", cli_ok, cli_details, started))
    logs.append(f"[cli-probe] {cli_details}")

    started = time.time()
    services_cfg = _load_services_config(root)
    api_enabled = _is_service_enabled("api", services_cfg.get("api", {}))
    if not api_enabled:
        api_ok = True
        api_details = "SKIP: API disabled in services config"
    elif not _is_port_open("127.0.0.1", 8787):
        api_ok = False
        api_details = "FAIL: API enabled but port 8787 is closed"
    else:
        cmd = [
            str(python_exe),
            "-c",
            (
                "import urllib.request; "
                "u=urllib.request.urlopen('http://127.0.0.1:8787/openapi.json', timeout=5); "
                "print(u.status)"
            ),
        ]
        commands.append(" ".join(cmd))
        try:
            rc, out, err = run_subprocess(cmd, cwd=root, timeout=min(timeout, 10))
            api_ok = rc == 0
            api_details = (out + "\n" + err).strip() or "API openapi probe completed"
            if not api_ok:
                api_details = f"FAIL: API enabled but /openapi.json probe failed ({api_details})"
        except subprocess.TimeoutExpired:
            api_ok = False
            api_details = "FAIL: API enabled but /openapi.json probe timed out"
    steps.append(_make_step("api reachability", api_ok, api_details, started))
    logs.append(f"[api] {api_details}")

    if verbose:
        logs.append("[verbose] smoke steps complete")

    return steps, logs, commands


def _run_scraper_sanity_step(timeout: int, python_exe: Path) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    root = find_repo_root()
    commands: list[str] = []

    candidates = [
        [str(python_exe), "-m", "webscraper", "--dry-run"],
        [str(python_exe), "-m", "webscraper.cli.main", "--dry-run"],
    ]

    try:
        outputs: list[str] = []
        for cmd in candidates:
            commands.append(" ".join(cmd))
            rc, out, err = run_subprocess(cmd, cwd=root, timeout=timeout)
            details = (out + "\n" + err).strip() or f"scraper sanity finished rc={rc}"
            outputs.append(f"$ {' '.join(cmd)}\n{details}")
            if rc == 0:
                return _make_step("scraper sanity run", True, details, started), "\n\n".join(outputs), commands

        fail_details = "\n\n".join(outputs) if outputs else "No sanity command candidates were available"
        return _make_step("scraper sanity run", False, fail_details, started), fail_details, commands
    except subprocess.TimeoutExpired:
        step = _make_step("scraper sanity run", False, f"scraper sanity timed out after {timeout}s", started)
        return step, step.details, commands


def _http_get_status(url: str, timeout_s: float) -> int | None:
    try:
        import httpx  # type: ignore[import-not-found]
    except Exception:
        return None

    try:
        with httpx.Client(timeout=timeout_s) as client:
            return int(client.get(url).status_code)
    except Exception:
        return None


def _wait_for_api_readiness(host: str, port: int, timeout_s: int) -> tuple[bool, str]:
    deadline = time.time() + timeout_s
    health_url = f"http://{host}:{port}/healthz"
    while time.time() < deadline:
        if _is_port_open(host, port, timeout_s=0.5):
            status = _http_get_status(url=health_url, timeout_s=2.0)
            if status == 200:
                return True, f"health route OK: {health_url}"
        time.sleep(0.25)
    return False, f"API did not become ready within {timeout_s}s (GET {health_url} != 200)"


def _start_ticket_api_if_needed(python_exe: Path, root: Path) -> tuple[str, str, subprocess.Popen[str] | None, list[str]]:
    host = "127.0.0.1"
    port = 8787
    commands: list[str] = []

    if _is_port_open(host, port):
        return "already_running", "Port 8787 already open; treating API as externally running", None, commands

    target = "webscraper.ticket_api.app:app"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [
        str(python_exe),
        "-m",
        "uvicorn",
        target,
        "--host",
        host,
        "--port",
        str(port),
    ]
    commands.append("command: " + " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root.resolve()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return "failed", "Python executable not found while starting uvicorn", None, commands

    deadline = time.time() + 5
    while time.time() < deadline:
        if _is_port_open(host, port, timeout_s=0.5):
            return "started", f"Started ticket API via {target}", proc, commands
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if proc.poll() is None and _is_port_open(host, port, timeout_s=0.5):
        return "started", f"Started ticket API via {target}", proc, commands

    try:
        out, err = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=2)
    stdout_text = (out or "").strip()
    stderr_text = (err or "").strip()
    if stdout_text:
        commands.append(f"stdout: {stdout_text}")
    if stderr_text:
        commands.append(f"stderr: {stderr_text}")
    if not stdout_text and not stderr_text:
        commands.append(f"stderr: uvicorn exited while loading {target}")
    return "failed", f"Unable to start ticket API via {target}", None, commands


def _stop_started_process(proc: subprocess.Popen[str] | None) -> tuple[bool, str]:
    if proc is None:
        return True, "No managed API process to stop"

    if proc.poll() is not None:
        return True, "Managed API process already exited"

    proc.terminate()
    try:
        proc.wait(timeout=5)
        return True, "Managed API process terminated cleanly"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        return True, "Managed API process required kill() after terminate timeout"


def _format_test_summary(
    steps: list[TestStep],
    total_ms: int,
    log_path: Path,
    pure_json_mode: bool,
    status_summary: dict[str, str] | None = None,
) -> str:
    payload = {
        "ok": all(step.ok for step in steps),
        "steps": [asdict(step) for step in steps],
        "duration_ms": total_ms,
        "log_file": str(log_path),
    }
    if status_summary is not None:
        payload["status_summary"] = status_summary
    if pure_json_mode:
        return json.dumps(payload, indent=2)

    lines = ["", "Test summary:"]
    if status_summary is not None:
        lines.append("- status:")
        for key in ("api_start", "api_ready", "pytest", "sanity"):
            if key in status_summary:
                lines.append(f"  - {key}: {status_summary[key]}")
    for step in steps:
        symbol = "✅ PASS" if step.ok else "❌ FAIL"
        lines.append(f"- {symbol} {step.name} ({step.duration_ms}ms)")
        lines.append(f"  {step.details}")
    lines.append(f"Total duration: {total_ms}ms")
    lines.append(f"Log file: {log_path}")
    return "\n".join(lines)


def _run_test_smoke(state: AppState, timeout: int) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_smoke_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)

    log_lines: list[str] = [f"command: test smoke --timeout {timeout}", f"python: {python_exe}"]

    try:
        steps, logs, commands = _run_smoke_steps(timeout=timeout, verbose=state.verbose, python_exe=python_exe)
        log_lines.extend(f"subprocess: {cmd}" for cmd in commands)
        log_lines.extend(logs)
    except Exception as exc:
        details = f"Unhandled error in smoke test: {exc}"
        if state.verbose:
            details = f"{details}\n{traceback.format_exc()}"
        steps = [TestStep(name="smoke test execution", ok=False, details=details, duration_ms=0)]
        log_lines.append(details)

    total_ms = int((time.time() - started) * 1000)
    log_lines.append("\n" + _format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=False))
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(_format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=state.pure_json_mode))

    ok = all(step.ok for step in steps)
    return (EXIT_OK if ok else EXIT_TEST_FAILED), steps, log_path


def _run_test_pytest(
    state: AppState,
    timeout: int,
    path: str | None = None,
    fix: bool = False,
    original_args: list[str] | None = None,
) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_pytest_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)
    current_python = Path(sys.executable).resolve()
    preferred_python = get_preferred_python(root).resolve()

    log_lines: list[str] = [
        f"command: test pytest --timeout {timeout} path={path or ''}".strip(),
        f"python: {python_exe}",
        f"current_python: {current_python}",
        f"preferred_python: {preferred_python}",
    ]

    if current_python != preferred_python:
        if state.use_preferred_python:
            args_for_reexec = original_args if original_args is not None else sys.argv[1:]
            reexec_cmd = [str(preferred_python), "-m", "webscraper_manager", *args_for_reexec]
            log_lines.append(
                f"interpreter_decision: re-exec under preferred python ({preferred_python})"
            )
            log_lines.append(f"subprocess: {' '.join(reexec_cmd)}")
            write_log(log_path, "\n".join(log_lines) + "\n")
            completed = subprocess.run(reexec_cmd, check=False)
            return completed.returncode, [], log_path

        warning = (
            "WARNING: use_preferred_python is OFF and current interpreter does not match preferred "
            f"(current: {current_python}, preferred: {preferred_python})"
        )
        print(warning)
        log_lines.append("interpreter_decision: mismatch allowed because use_preferred_python is OFF")
        log_lines.append(warning)
    else:
        log_lines.append("interpreter_decision: current interpreter already matches preferred")

    dep_step, dep_commands, dep_ok = _check_test_dependencies(
        python_exe=python_exe,
        timeout=min(timeout, 90),
        auto_fix=fix,
        root=root,
    )
    steps: list[TestStep] = [dep_step]
    log_lines.extend(f"subprocess: {cmd}" for cmd in dep_commands)

    if dep_ok:
        install_started = time.time()
        try:
            ensure_webscraper_editable_installed(python_exe=str(python_exe), repo_root=root)
            install_logs, install_commands = getattr(ensure_webscraper_editable_installed, "_last_run", ([], []))
            steps.append(
                _make_step(
                    "webscraper import readiness",
                    True,
                    "webscraper import OK",
                    install_started,
                )
            )
            log_lines.extend(f"subprocess: {cmd}" for cmd in install_commands)
            log_lines.extend(install_logs)
            step, details, commands = _run_pytest_step(path=path, timeout=timeout, python_exe=python_exe)
            steps.append(step)
            log_lines.extend(f"subprocess: {cmd}" for cmd in commands)
            log_lines.append(details)
        except RuntimeError as exc:
            steps.append(_make_step("webscraper import readiness", False, str(exc), install_started))
            log_lines.append(str(exc))

    total_ms = int((time.time() - started) * 1000)
    log_lines.append("\n" + _format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=False))
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(_format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=state.pure_json_mode))

    return (EXIT_OK if all(step.ok for step in steps) else EXIT_TEST_FAILED), steps, log_path


def _run_test_all(
    state: AppState,
    timeout: int,
    keep_going: bool,
    pytest_path: str | None = None,
    fix: bool = False,
    original_args: list[str] | None = None,
) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_all_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)
    current_python = Path(sys.executable).resolve()
    preferred_python = get_preferred_python(root).resolve()

    steps: list[TestStep] = []
    log_lines: list[str] = [
        f"command: test all --timeout {timeout} --keep-going={keep_going}",
        f"python: {python_exe}",
        f"current_python: {current_python}",
        f"preferred_python: {preferred_python}",
    ]
    status_summary: dict[str, str] = {
        "api_start": "failed",
        "api_ready": "failed",
        "pytest": "fail",
        "sanity": "fail",
    }
    api_proc: subprocess.Popen[str] | None = None

    if current_python != preferred_python:
        if state.use_preferred_python:
            args_for_reexec = original_args if original_args is not None else sys.argv[1:]
            reexec_cmd = [str(preferred_python), "-m", "webscraper_manager", *args_for_reexec]
            log_lines.append(
                f"interpreter_decision: re-exec under preferred python ({preferred_python})"
            )
            log_lines.append(f"subprocess: {' '.join(reexec_cmd)}")
            write_log(log_path, "\n".join(log_lines) + "\n")
            completed = subprocess.run(reexec_cmd, check=False)
            return completed.returncode, [], log_path

        warning = (
            "WARNING: use_preferred_python is OFF and current interpreter does not match preferred "
            f"(current: {current_python}, preferred: {preferred_python})"
        )
        print(warning)
        log_lines.append("interpreter_decision: mismatch allowed because use_preferred_python is OFF")
        log_lines.append(warning)
    else:
        log_lines.append("interpreter_decision: current interpreter already matches preferred")

    failed = False
    try:
        smoke_steps, smoke_logs, smoke_commands = _run_smoke_steps(timeout=min(timeout, 30), verbose=state.verbose, python_exe=python_exe)
        steps.extend(smoke_steps)
        log_lines.extend(f"subprocess: {cmd}" for cmd in smoke_commands)
        log_lines.extend(smoke_logs)
        failed = any(not step.ok for step in smoke_steps)

        api_start_status, api_start_details, api_proc, api_start_commands = _start_ticket_api_if_needed(
            python_exe=python_exe,
            root=root,
        )
        status_summary["api_start"] = api_start_status
        log_lines.extend(f"subprocess: {cmd}" for cmd in api_start_commands)
        log_lines.append(f"api_start: {api_start_details}")
        steps.append(TestStep(name="ticket api startup", ok=api_start_status != "failed", details=api_start_details, duration_ms=0))
        failed = failed or (api_start_status == "failed")

        api_ready_ok, api_ready_details = _wait_for_api_readiness(host="127.0.0.1", port=8787, timeout_s=10)
        status_summary["api_ready"] = "ok" if api_ready_ok else "failed"
        steps.append(TestStep(name="ticket api readiness", ok=api_ready_ok, details=api_ready_details, duration_ms=0))
        log_lines.append(f"api_ready: {api_ready_details}")
        failed = failed or (not api_ready_ok)

        has_tests = (root / "tests").is_dir() or (root / "webscraper" / "tests").is_dir()
        should_try_pytest = has_tests

        if should_try_pytest and (keep_going or not failed):
            dep_step, dep_commands, dep_ok = _check_test_dependencies(
                python_exe=python_exe,
                timeout=min(timeout, 90),
                auto_fix=fix,
                root=root,
            )
            steps.append(dep_step)
            log_lines.extend(f"subprocess: {cmd}" for cmd in dep_commands)
            failed = failed or (not dep_step.ok)

            if dep_ok and (keep_going or not failed):
                install_started = time.time()
                try:
                    ensure_webscraper_editable_installed(python_exe=str(python_exe), repo_root=root)
                    install_logs, install_commands = getattr(ensure_webscraper_editable_installed, "_last_run", ([], []))
                    install_step = _make_step(
                        "webscraper import readiness",
                        True,
                        "webscraper import OK",
                        install_started,
                    )
                    steps.append(install_step)
                    log_lines.extend(f"subprocess: {cmd}" for cmd in install_commands)
                    log_lines.extend(install_logs)
                    pytest_step, pytest_details, pytest_commands = _run_pytest_step(path=pytest_path, timeout=timeout, python_exe=python_exe)
                    steps.append(pytest_step)
                    status_summary["pytest"] = "pass" if pytest_step.ok else "fail"
                    log_lines.extend(f"subprocess: {cmd}" for cmd in pytest_commands)
                    log_lines.append(pytest_details)
                    failed = failed or (not pytest_step.ok)
                except RuntimeError as exc:
                    install_step = _make_step("webscraper import readiness", False, str(exc), install_started)
                    steps.append(install_step)
                    log_lines.append(str(exc))
                    status_summary["pytest"] = "fail"
                    failed = True
            else:
                status_summary["pytest"] = "fail"
        elif not should_try_pytest:
            steps.append(TestStep(name="pytest", ok=True, details="No tests folder detected; skipped", duration_ms=0))
            status_summary["pytest"] = "pass"
        else:
            status_summary["pytest"] = "fail"

        if keep_going or not failed:
            sanity_step, sanity_details, sanity_commands = _run_scraper_sanity_step(timeout=min(timeout, 45), python_exe=python_exe)
            steps.append(sanity_step)
            status_summary["sanity"] = "pass" if sanity_step.ok else "fail"
            log_lines.extend(f"subprocess: {cmd}" for cmd in sanity_commands)
            log_lines.append(sanity_details)
            failed = failed or (not sanity_step.ok)
        else:
            status_summary["sanity"] = "fail"
    finally:
        shutdown_ok, shutdown_details = _stop_started_process(api_proc)
        steps.append(TestStep(name="ticket api shutdown", ok=shutdown_ok, details=shutdown_details, duration_ms=0))
        log_lines.append(f"api_shutdown: {shutdown_details}")

    total_ms = int((time.time() - started) * 1000)
    log_lines.append(
        "\n"
        + _format_test_summary(
            steps,
            total_ms=total_ms,
            log_path=log_path,
            pure_json_mode=False,
            status_summary=status_summary,
        )
    )
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(
            _format_test_summary(
                steps,
                total_ms=total_ms,
                log_path=log_path,
                pure_json_mode=state.pure_json_mode,
                status_summary=status_summary,
            )
        )

    return (EXIT_OK if not failed else EXIT_TEST_FAILED), steps, log_path


def run_version(console: Console | None, state: AppState) -> None:
    if state.quiet:
        print(__version__)
        return
    if console is None:
        print(__version__)
        return
    console.print(
        Panel(
            Text(f"webscraper_manager {__version__}", justify="center", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _set_flag_from_source(ctx: Any, name: str, value: bool) -> bool | None:
    try:
        source = ctx.get_parameter_source(name)
        if source is not None and source.name != "DEFAULT":
            return value
    except Exception:
        if value:
            return value
    return None


def _clear_screen(state: AppState) -> None:
    if not state.clear_screen:
        return
    if os.name == "nt":
        os.system("cls")
        return
    os.system("clear")


def _read_line(prompt: str) -> str:
    return input(prompt).strip().lower()


def _confirm_quit() -> bool:
    try:
        answer = _read_line("Quit? [y/N] ")
    except KeyboardInterrupt:
        print()
        return False
    return answer in {"y", "yes"}


def render_menu(console: Console | None, state: AppState) -> None:
    _clear_screen(state)
    menu_console = console if sys.stdout.isatty() else None
    print_banner(menu_console)
    clear_status = "ON" if state.clear_screen else "OFF"
    pure_json_status = "ON" if state.pure_json_mode else "OFF"
    preferred_status = "ON" if state.use_preferred_python else "OFF"
    root = find_repo_root()
    runtime_python = get_runtime_python(state, root)
    preferred_match = "YES" if runtime_python.resolve() == get_preferred_python(root).resolve() else "NO"

    if menu_console is None:
        print(f"\nToggles: pure_json_mode: {pure_json_status} | clear: {clear_status} | use_preferred_python: {preferred_status}")
        print("\nMenu")
        print("[s] Start services")
        print("[x] Stop services")
        print("[u] Status services")
        print("[1] Doctor (normal)")
        print("[2] Doctor (quiet)")
        print("[3] Doctor (global quiet before command)")
        print("[4] Doctor (json)")
        print("[5] Version")
        print("[6] Test Run (smoke)")
        print("[7] Full Test Run (all)")
        print("[8] Pytest")
        print("[9] Fix Test Dependencies (pytest/httpx)")
        print("[a] Ticket API: Start")
        print("[b] Ticket API: Stop")
        print("[c] Ticket API: Status")
        print("[r] Refresh")
        print(f"[t] Toggle pure JSON mode (currently {pure_json_status})")
        print(f"[p] Toggle use preferred python (currently {preferred_status})")
        print("[q] Quit")
        print(f"\npython: {runtime_python.name} (preferred: {preferred_match})")
        return

    table = Table(title="Menu", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Option", justify="center", no_wrap=True)
    table.add_column("Command", style="white", no_wrap=True)
    table.add_column("Description", style="bright_black")
    table.caption = f"pure_json_mode: {pure_json_status} | clear: {clear_status} | use_preferred_python: {preferred_status}"
    table.add_row("s", "Start services", "Same as: start")
    table.add_row("x", "Stop services", "Same as: stop")
    table.add_row("u", "Status services", "Same as: status")
    table.add_row("1", "Doctor (normal)", "Same as: doctor")
    table.add_row("2", "Doctor (quiet)", "Same as: doctor --quiet")
    table.add_row("3", "Doctor (global quiet before command)", "Same as: --quiet doctor")
    table.add_row("4", "Doctor (json)", "Same as: doctor --json")
    table.add_row("5", "Version", "Same as: --version")
    table.add_row("6", "Test Run (smoke)", "Same as: test smoke")
    table.add_row("7", "Full Test Run (all)", "Same as: test all")
    table.add_row("8", "Pytest", "Same as: test pytest")
    table.add_row("9", "Fix Test Dependencies (pytest/httpx)", "Same as: fix test-deps")
    table.add_row("a", "Ticket API: Start", "Start API in background (managed by menu state)")
    table.add_row("b", "Ticket API: Stop", "Stop only manager-started Ticket API PID")
    table.add_row("c", "Ticket API: Status", "Show managed/unmanaged, pid, port, healthz, and log")
    table.add_row("r", "Refresh", "Redraw the menu")
    table.add_row("t", "Toggle pure JSON mode", f"Currently: {pure_json_status}")
    table.add_row("p", "Toggle use preferred python", f"Currently: {preferred_status}")
    table.add_row("q", "Quit", "Exit menu (with confirmation)")
    menu_console.print(table)
    menu_console.print(f"[bright_black]python: {runtime_python.name} (preferred: {preferred_match})[/bright_black]")


def _run_menu_action(console: Console | None, state: AppState, choice: str) -> int:
    if choice == "s":
        return _start_services(state, console)
    if choice == "x":
        return _stop_services(state, console)
    if choice == "u":
        return _print_service_status(state, console)
    if choice == "1":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "2":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "3":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "4":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        if not state.pure_json_mode:
            print("Running: doctor --json")
        code, _ = run_doctor(console, action_state, json_out=True)
        return code
    if choice == "5":
        action_state = AppState(
            quiet=state.quiet,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        run_version(console, action_state)
        return EXIT_OK
    if choice == "6":
        if not state.pure_json_mode:
            print("Running: test smoke")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_smoke(action_state, timeout=30)
        return code
    if choice == "7":
        if not state.pure_json_mode:
            print("Running: test all")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_all(
            action_state,
            timeout=300,
            keep_going=False,
            original_args=["test", "all", "--timeout", "300"],
        )
        return code
    if choice == "8":
        if not state.pure_json_mode:
            print("Running: test pytest")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_pytest(
            action_state,
            timeout=300,
            path=None,
            original_args=["test", "pytest", "--timeout", "300"],
        )
        return code
    if choice == "9":
        if not state.pure_json_mode:
            print("Running: fix test-deps")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_fix_test_deps(action_state, timeout=300)
        return code
    if choice == "a":
        return _start_services(state, console, service="api")
    if choice == "b":
        return _stop_services(state, console, service="api")
    if choice == "c":
        return _print_service_status(state, console, service="api")
    return EXIT_USAGE


def pause_for_user() -> None:
    print()
    print("Press Enter to return to menu…")
    try:
        if not sys.stdin.isatty():
            print("(No interactive stdin; returning to menu in 2s...)")
            time.sleep(2)
            return
        input()
    except EOFError:
        print("(No interactive stdin; returning to menu in 2s...)")
        time.sleep(2)
    except KeyboardInterrupt:
        print()
        return


def run_menu(state: AppState) -> int:
    state.in_menu = True
    console = get_console(state)

    while True:
        render_menu(console, state)
        try:
            choice = _read_line("\nSelect an option [s, x, u, 1-9, a, b, c, r, t, p, q]: ")
        except KeyboardInterrupt:
            print()
            continue

        if choice == "r":
            continue

        if choice == "t":
            state.pure_json_mode = not state.pure_json_mode
            mode = "ON" if state.pure_json_mode else "OFF"
            print(f"pure_json_mode: {mode}")
            continue

        if choice == "p":
            state.use_preferred_python = not state.use_preferred_python
            mode = "ON" if state.use_preferred_python else "OFF"
            print(f"use_preferred_python: {mode}")
            continue

        if choice == "q":
            if _confirm_quit():
                return EXIT_OK
            continue

        if choice not in {"s", "x", "u", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c"}:
            print("Invalid selection. Enter s, x, u, 1, 2, 3, 4, 5, 6, 7, 8, 9, a, b, c, r, t, p, or q.")
            continue

        try:
            _run_menu_action(console, state, choice)
        except KeyboardInterrupt:
            if not state.pure_json_mode:
                print("Canceled.")
            continue

        pause_for_user()


def _build_state_from_ctx(ctx: Any, quiet: bool, verbose: bool, use_preferred_python: bool = True) -> AppState:
    state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()

    quiet_override = _set_flag_from_source(ctx, "quiet", quiet)
    verbose_override = _set_flag_from_source(ctx, "verbose", verbose)
    preferred_override = _set_flag_from_source(ctx, "use_preferred_python", use_preferred_python)

    if quiet_override is not None:
        state.quiet = quiet_override
    if verbose_override is not None:
        state.verbose = verbose_override
    if preferred_override is not None:
        state.use_preferred_python = preferred_override
    return state


if TYPER_AVAILABLE:
    app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)
    test_app = typer.Typer(help="Run webscraper test suites", no_args_is_help=True)
    fix_app = typer.Typer(help="Fix common environment issues", no_args_is_help=True)
    start_app = typer.Typer(help="Start managed services", invoke_without_command=True, no_args_is_help=False)
    stop_app = typer.Typer(help="Stop managed services", invoke_without_command=True, no_args_is_help=False)
    status_app = typer.Typer(help="Show managed service status", invoke_without_command=True, no_args_is_help=False)

    def _version_callback(value: bool) -> None:
        if not value:
            return
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        raise typer.Exit(EXIT_OK)

    @app.callback(invoke_without_command=False)
    def _root(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output (no banner)."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
        use_preferred_python: bool = typer.Option(
            True,
            "--use-preferred-python/--no-use-preferred-python",
            help="Use preferred webscraper venv interpreter for subprocess actions.",
        ),
    ) -> None:
        del version
        if ctx.resilient_parsing:
            return
        ctx.obj = AppState(quiet=quiet, verbose=verbose, use_preferred_python=use_preferred_python)

    @app.command()
    def doctor(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        json_override = _set_flag_from_source(ctx, "json_output", json_output)
        use_json = bool(json_override) if json_override is not None else json_output

        if should_print_banner(state, json_out=use_json, is_help=False):
            print_banner(get_console(state))

        code, _ = run_doctor(get_console(state), state, json_out=use_json)
        if code:
            raise typer.Exit(code)

    @app.command("auth-check")
    def auth_check(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(run_auth_check(state, json_out=bool(json_output)))


    @app.command("auth-doctor")
    def auth_doctor_cmd(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(run_auth_doctor(state, json_out=bool(json_output)))

    @app.command("seed-auth")
    def seed_auth(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(run_seed_auth(state, json_out=bool(json_output)))

    @start_app.callback()
    def start_default(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_start_services(state, get_console(state), service="all"))

    @start_app.command("all")
    def start_all(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_start_services(state, get_console(state), service="all"))

    @start_app.command("api")
    def start_api(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_start_services(state, get_console(state), service="api"))

    @start_app.command("ui")
    def start_ui(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_start_services(state, get_console(state), service="ui"))

    @start_app.command("webscraper")
    def start_webscraper(
        ctx: typer.Context,
        detach: bool = typer.Option(False, "--detach", help="Start webscraper stack and return immediately."),
        kill_ports: bool = typer.Option(True, "--kill-ports/--no-kill-ports", help="Kill processes occupying stack ports before start."),
        kill_scope: str = typer.Option("repo", "--kill-scope", help="Port kill scope: repo, safe, or force."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(
            _start_webscraper_stack(state, get_console(state), detach=detach, kill_ports=kill_ports, kill_scope=kill_scope)
        )

    @stop_app.callback()
    def stop_default(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_stop_services(state, get_console(state), service="all"))

    @stop_app.command("all")
    def stop_all(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_stop_services(state, get_console(state), service="all"))

    @stop_app.command("api")
    def stop_api(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_stop_services(state, get_console(state), service="api"))

    @stop_app.command("ui")
    def stop_ui(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_stop_services(state, get_console(state), service="ui"))

    @stop_app.command("webscraper")
    def stop_webscraper(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_stop_webscraper_stack(state, get_console(state)))

    @status_app.callback()
    def status_default(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_print_service_status(state, get_console(state), service="all"))

    @status_app.command("all")
    def status_all(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_print_service_status(state, get_console(state), service="all"))

    @status_app.command("api")
    def status_api(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_print_service_status(state, get_console(state), service="api"))

    @status_app.command("ui")
    def status_ui(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_print_service_status(state, get_console(state), service="ui"))

    @status_app.command("webscraper")
    def status_webscraper(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        raise typer.Exit(_status_webscraper_stack(state, get_console(state)))

    app.add_typer(start_app, name="start")
    app.add_typer(stop_app, name="stop")
    app.add_typer(status_app, name="status")

    @app.command()
    def restart(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        _stop_services(state, get_console(state))
        raise typer.Exit(_start_services(state, get_console(state)))

    @test_app.command("smoke")
    def test_smoke(
        ctx: typer.Context,
        timeout: int = typer.Option(30, "--timeout", min=1, help="Timeout in seconds for smoke checks."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_smoke(state, timeout=timeout)
        raise typer.Exit(code)

    @test_app.command("pytest")
    def test_pytest(
        ctx: typer.Context,
        path: str | None = typer.Option(None, "--path", help="Optional pytest path selection."),
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for pytest run."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        fix: bool = typer.Option(False, "--fix", help="Auto-install missing pytest dependencies before running."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_pytest(state, timeout=timeout, path=path, fix=fix, original_args=sys.argv[1:])
        raise typer.Exit(code)

    @test_app.command("all")
    def test_all(
        ctx: typer.Context,
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for full test run."),
        keep_going: bool = typer.Option(False, "--keep-going", help="Continue running steps after failures."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        fix: bool = typer.Option(False, "--fix", help="Auto-install missing pytest dependencies before running."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_all(
            state,
            timeout=timeout,
            keep_going=keep_going,
            pytest_path=None,
            fix=fix,
            original_args=sys.argv[1:],
        )
        raise typer.Exit(code)

    app.add_typer(test_app, name="test")

    @fix_app.command("test-deps")
    def fix_test_deps(
        ctx: typer.Context,
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for pip install."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_fix_test_deps(state, timeout=timeout)
        raise typer.Exit(code)

    @fix_app.command("deps")
    def fix_deps(
        ctx: typer.Context,
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for pip commands."),
        no_check: bool = typer.Option(False, "--no-check", help="Skip pip check after install."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_fix_deps(state, timeout=timeout, run_pip_check=not no_check)
        raise typer.Exit(code)

    app.add_typer(fix_app, name="fix")

    @app.command()
    def menu(
        ctx: typer.Context,
        clear_screen: bool = typer.Option(
            False,
            "--clear",
            "--clear-screen",
            help="Clear the screen at the start of each menu render.",
        ),
        no_clear: bool = typer.Option(False, "--no-clear", help="Do not clear the screen between menu draws."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output for menu actions."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        state.clear_screen = bool(clear_screen and not no_clear)
        code = run_menu(state)
        if code:
            raise typer.Exit(code)


def _argparse_fallback(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])

    root = argparse.ArgumentParser(prog="webscraper_manager", description="Manage webscraper workflows")
    root.add_argument("--version", action="store_true", help="Show version and exit")
    root.add_argument("--use-preferred-python", action=argparse.BooleanOptionalAction, default=True, help="Use preferred webscraper venv interpreter for subprocess actions")

    subparsers = root.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Run doctor checks")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")

    auth_check_parser = subparsers.add_parser("auth-check", help="Run auth probes for requests and selenium")
    auth_check_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    auth_check_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    auth_check_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    seed_auth_parser = subparsers.add_parser("seed-auth", help="Seed requests auth with Selenium and fetch customers page")
    auth_doctor_parser = subparsers.add_parser("auth-doctor", help="Check Chrome auth seeding prerequisites")
    auth_doctor_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    auth_doctor_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    auth_doctor_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    seed_auth_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    seed_auth_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    seed_auth_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    doctor_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    doctor_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    menu_parser = subparsers.add_parser("menu", help="Open interactive menu")
    menu_parser.add_argument("--clear", "--clear-screen", action="store_true", dest="clear_screen", help="Clear the screen when drawing the menu")
    menu_parser.add_argument("--no-clear", action="store_true", help="Do not clear the screen")
    menu_parser.add_argument("--quiet", action="store_true", help="Minimal output for menu actions")
    menu_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    for svc_cmd in ("start", "stop", "status", "restart"):
        svc_parser = subparsers.add_parser(svc_cmd, help=f"{svc_cmd.capitalize()} managed services")
        if svc_cmd in {"start", "stop", "status"}:
            svc_parser.add_argument("service", nargs="?", choices=["all", "api", "ui", "worker", "webscraper"], help="Optional service target")
        if svc_cmd == "start":
            svc_parser.add_argument("--detach", action="store_true", help="Start webscraper stack and return immediately")
            svc_parser.add_argument("--kill-ports", action=argparse.BooleanOptionalAction, default=True, help="Kill processes occupying stack ports before start")
            svc_parser.add_argument("--kill-scope", choices=["repo", "safe", "force"], default="repo", help="Port kill scope when starting webscraper")
        svc_parser.add_argument("--quiet", action="store_true", help="Minimal output")
        svc_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    test_parser = subparsers.add_parser("test", help="Run test workflows")
    test_subparsers = test_parser.add_subparsers(dest="test_command")

    smoke_parser = test_subparsers.add_parser("smoke", help="Run smoke tests")
    smoke_parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    smoke_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    smoke_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    all_parser = test_subparsers.add_parser("all", help="Run full test suite")
    all_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    all_parser.add_argument("--keep-going", action="store_true", help="Continue despite failures")
    all_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    all_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    all_parser.add_argument("--fix", action="store_true", help="Auto-install missing pytest dependencies before running")

    pytest_parser = test_subparsers.add_parser("pytest", help="Run pytest")
    pytest_parser.add_argument("--path", type=str, default=None, help="Optional pytest path")
    pytest_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    pytest_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    pytest_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    pytest_parser.add_argument("--fix", action="store_true", help="Auto-install missing pytest dependencies before running")

    fix_parser = subparsers.add_parser("fix", help="Fix common environment issues")
    fix_subparsers = fix_parser.add_subparsers(dest="fix_command")
    fix_test_deps_parser = fix_subparsers.add_parser("test-deps", help="Install pytest/httpx dependencies")
    fix_test_deps_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    fix_test_deps_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    fix_test_deps_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    fix_deps_parser = fix_subparsers.add_parser("deps", help="Install manager dependencies from requirements.txt")
    fix_deps_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    fix_deps_parser.add_argument("--no-check", action="store_true", help="Skip pip check")
    fix_deps_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    fix_deps_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    root.add_argument("--quiet", action="store_true", help="Minimal output")
    root.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = root.parse_args(argv)

    if args.version:
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        return EXIT_OK

    if args.command == "menu":
        state = AppState(
            quiet=bool(args.quiet),
            verbose=bool(args.verbose),
            clear_screen=bool(args.clear_screen and not args.no_clear),
            use_preferred_python=bool(args.use_preferred_python),
        )
        return run_menu(state)

    if args.command == "doctor":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        if should_print_banner(state, json_out=bool(args.json_output), is_help=False):
            print_banner(get_console(state))
        code, _ = run_doctor(get_console(state), state, json_out=bool(args.json_output))
        return code

    if args.command == "auth-check":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        return run_auth_check(state, json_out=bool(args.json_output))

    if args.command == "auth-doctor":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        return run_auth_doctor(state, json_out=bool(args.json_output))

    if args.command == "seed-auth":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        return run_seed_auth(state, json_out=bool(args.json_output))

    if args.command in {"start", "stop", "status", "restart"}:
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        console = get_console(state)
        if args.command == "start":
            if getattr(args, "service", None) == "webscraper":
                return _start_webscraper_stack(
                    state,
                    console,
                    detach=bool(getattr(args, "detach", False)),
                    kill_ports=bool(getattr(args, "kill_ports", True)),
                    kill_scope=str(getattr(args, "kill_scope", "repo")),
                )
            return _start_services(state, console, service=getattr(args, "service", None))
        if args.command == "stop":
            if getattr(args, "service", None) == "webscraper":
                return _stop_webscraper_stack(state, console)
            return _stop_services(state, console, service=getattr(args, "service", None))
        if args.command == "status":
            if getattr(args, "service", None) == "webscraper":
                return _status_webscraper_stack(state, console)
            return _print_service_status(state, console, service=getattr(args, "service", None))
        _stop_services(state, console)
        return _start_services(state, console)

    if args.command == "test":
        if args.test_command == "smoke":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_smoke(state, timeout=int(args.timeout))
            return code
        if args.test_command == "all":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_all(
                state,
                timeout=int(args.timeout),
                keep_going=bool(args.keep_going),
                pytest_path=None,
                fix=bool(args.fix),
                original_args=argv,
            )
            return code
        if args.test_command == "pytest":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_pytest(
                state,
                timeout=int(args.timeout),
                path=args.path,
                fix=bool(args.fix),
                original_args=argv,
            )
            return code
        test_parser.print_help()
        return EXIT_USAGE


    if args.command == "fix":
        if args.fix_command == "test-deps":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_fix_test_deps(state, timeout=int(args.timeout))
            return code
        if args.fix_command == "deps":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_fix_deps(state, timeout=int(args.timeout), run_pip_check=not bool(args.no_check))
            return code
        fix_parser.print_help()
        return EXIT_USAGE

    root.print_help()
    return EXIT_USAGE if argv else EXIT_OK


def main() -> None:
    argv = sys.argv[1:]
    if TYPER_AVAILABLE:
        app()
        return

    try:
        raise SystemExit(_argparse_fallback(argv))
    except KeyboardInterrupt:
        raise


if __name__ == "__main__":
    main()

# Test commands
# python -m webscraper_manager menu --no-clear
# python -m webscraper_manager doctor --quiet
# python -m webscraper_manager test smoke
# python -m webscraper_manager test all
# python -m webscraper_manager test pytest
# python -m webscraper_manager --version
# Quick verification
# python -m webscraper_manager start api
# python -m webscraper_manager start ui
# UI: http://localhost:3000
# API OpenAPI: http://127.0.0.1:8787/openapi.json
