from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path("var") / "web-app-launcher"
RUNTIME_STATE_FILE = RUNTIME_DIR / "run_state.json"


class LauncherError(RuntimeError):
    """Raised for expected launcher failures with actionable messages."""


def is_windows() -> bool:
    return os.name == "nt"


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "scripts").exists():
            return candidate
    raise LauncherError("Could not locate repo root from current path.")


def log(section: str, message: str) -> None:
    print(f"[{section}] {message}")


def host_python() -> str:
    if is_windows():
        py = shutil.which("py")
        if py:
            return "py"
    python = shutil.which("python")
    if python:
        return python
    raise LauncherError("No host Python interpreter found in PATH.")


def run_checked(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None, section: str = "run") -> None:
    log(section, f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    if proc.returncode != 0:
        raise LauncherError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def ensure_paths_exist(root: Path, required_paths: list[str], *, section: str) -> None:
    missing = [path for path in required_paths if not (root / path).exists()]
    if missing:
        raise LauncherError(f"Missing required path(s): {', '.join(missing)}")
    for path in required_paths:
        log(section, f"OK: {path}")


def venv_python(root: Path, venv_name: str) -> Path:
    if is_windows():
        return root / venv_name / "Scripts" / "python.exe"
    return root / venv_name / "bin" / "python"


def bootstrap_venv(root: Path, venv_name: str) -> None:
    py = host_python()
    cmd = [py]
    if is_windows() and Path(py).name.lower() == "py.exe":
        cmd.append("-3")
    cmd.extend(
        [
            str(root / "scripts" / "bootstrap_venv.py"),
            "--venv",
            venv_name,
            "--auto-from-registry",
        ]
    )
    run_checked(cmd, cwd=root, section="bootstrap")


def ensure_python_env(root: Path, venv_name: str, *, bootstrap: bool) -> Path:
    py = venv_python(root, venv_name)
    if py.exists():
        log("python", f"Using interpreter: {py}")
        return py
    if not bootstrap:
        raise LauncherError(f"Missing interpreter: {py}")
    log("python", f"Interpreter missing, bootstrapping {venv_name}...")
    bootstrap_venv(root, venv_name)
    if not py.exists():
        raise LauncherError(f"Bootstrap completed but interpreter is still missing: {py}")
    log("python", f"Using interpreter: {py}")
    return py


def npm_executable() -> str:
    preferred = "npm.cmd" if is_windows() else "npm"
    npm = shutil.which(preferred) or shutil.which("npm")
    if not npm:
        raise LauncherError("npm was not found in PATH.")
    return npm


def ensure_manager_ui_dependencies(root: Path) -> None:
    py = host_python()
    cmd = [py]
    if is_windows() and Path(py).name.lower() == "py.exe":
        cmd.append("-3")
    cmd.append(str(root / "scripts" / "ensure_manager_ui_deps.py"))
    run_checked(cmd, cwd=root, section="deps")


def run_doctor(root: Path) -> None:
    py = host_python()
    cmd = [py]
    if is_windows() and Path(py).name.lower() == "py.exe":
        cmd.append("-3")
    cmd.append(str(root / "scripts" / "doctor_devs.py"))
    run_checked(cmd, cwd=root, section="doctor")


def _netstat_pids_for_port(port: int) -> set[int]:
    if not is_windows():
        return set()
    cmd = ["netstat", "-ano", "-p", "tcp"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return set()

    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        if local_address.endswith(f":{port}"):
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                pass
    return pids


def _posix_pids_for_port(port: int) -> set[int]:
    if is_windows():
        return set()
    lsof = shutil.which("lsof")
    if not lsof:
        return set()
    proc = subprocess.run([lsof, "-ti", f"tcp:{port}"], capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        return set()
    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.add(int(line))
        except ValueError:
            pass
    return pids


def pids_for_port(port: int) -> set[int]:
    pids = _netstat_pids_for_port(port)
    if pids:
        return pids
    return _posix_pids_for_port(port)


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def kill_pid_tree(pid: int, *, section: str) -> None:
    if pid <= 0:
        return
    if is_windows():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        log(section, f"Sent taskkill to pid {pid}")
        return
    try:
        os.kill(pid, 15)
        log(section, f"Sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        return
    except PermissionError:
        log(section, f"Permission denied when killing pid {pid}")


def ensure_port_available(port: int, *, cleanup: bool, section: str) -> None:
    if not is_port_open("127.0.0.1", port):
        log(section, f"Port {port} is free")
        return
    pids = pids_for_port(port)
    if not cleanup:
        pid_text = ", ".join(str(pid) for pid in sorted(pids)) or "unknown"
        raise LauncherError(f"Port {port} is already in use (pid: {pid_text}).")

    log(section, f"Port {port} is in use; attempting cleanup")
    for pid in sorted(pids):
        kill_pid_tree(pid, section=section)

    deadline = time.time() + 10
    while time.time() < deadline:
        if not is_port_open("127.0.0.1", port):
            log(section, f"Port {port} is now free")
            return
        time.sleep(0.25)
    raise LauncherError(f"Port {port} remains busy after cleanup attempts.")


def wait_for_http(url: str, *, timeout_s: int, ok_status_max: int = 399, section: str = "wait") -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                status = response.getcode()
                if 200 <= status <= ok_status_max:
                    log(section, f"Ready: {url} ({status})")
                    return
        except urllib.error.HTTPError as exc:
            if 200 <= exc.code <= ok_status_max:
                log(section, f"Ready: {url} ({exc.code})")
                return
        except Exception:
            pass
        time.sleep(1)
    raise LauncherError(f"Timed out waiting for {url} after {timeout_s}s.")


def _creationflags() -> int:
    if not is_windows():
        return 0
    return subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def start_detached(
    *,
    root: Path,
    service_name: str,
    cmd: list[str],
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    runtime_dir = root / RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = runtime_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = logs_dir / f"{service_name}.log"
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=_creationflags(),
            start_new_session=not is_windows(),
        )

    log("launch", f"Started {service_name} (pid={proc.pid})")
    log("launch", f"Command: {' '.join(cmd)}")
    log("launch", f"Log file: {log_path}")

    return {
        "service": service_name,
        "pid": proc.pid,
        "cmd": cmd,
        "cwd": str(cwd),
        "log": str(log_path),
        "started_at": int(time.time()),
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"services": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"services": {}}


def save_service_state(root: Path, entry: dict[str, Any]) -> None:
    state_path = root / RUNTIME_STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state(state_path)
    services = state.setdefault("services", {})
    services[entry["service"]] = entry
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    log("state", f"Updated runtime state: {state_path}")


def load_services(root: Path) -> dict[str, dict[str, Any]]:
    state = _load_state(root / RUNTIME_STATE_FILE)
    services = state.get("services", {})
    if isinstance(services, dict):
        return {str(name): value for name, value in services.items() if isinstance(value, dict)}
    return {}


def remove_service_state(root: Path, service_name: str) -> None:
    state_path = root / RUNTIME_STATE_FILE
    state = _load_state(state_path)
    services = state.get("services", {})
    if isinstance(services, dict) and service_name in services:
        services.pop(service_name, None)
        state["services"] = services
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def stop_service(root: Path, service_name: str, *, fallback_ports: list[int] | None = None) -> None:
    services = load_services(root)
    info = services.get(service_name)
    section = "stop"

    if info:
        pid = int(info.get("pid", 0) or 0)
        if pid:
            kill_pid_tree(pid, section=section)
        remove_service_state(root, service_name)
    else:
        log(section, f"No runtime entry for {service_name}")

    if fallback_ports:
        for port in fallback_ports:
            if is_port_open("127.0.0.1", port):
                log(section, f"Fallback cleanup for port {port}")
                for pid in sorted(pids_for_port(port)):
                    kill_pid_tree(pid, section=section)


def stop_all_known_services(root: Path, *, fallback_ports: list[int] | None = None) -> None:
    services = load_services(root)
    for name in list(services.keys()):
        stop_service(root, name)

    if fallback_ports:
        for port in fallback_ports:
            if is_port_open("127.0.0.1", port):
                for pid in sorted(pids_for_port(port)):
                    kill_pid_tree(pid, section="stop")


def maybe_open_browser(url: str, *, open_browser: bool) -> None:
    if not open_browser:
        return
    if is_windows():
        subprocess.Popen(["cmd", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        browser = shutil.which("xdg-open")
        if browser:
            subprocess.Popen([browser, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("browser", f"Opened: {url}")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-bootstrap", action="store_true", help="Do not auto-bootstrap missing dependencies")
    parser.add_argument("--doctor", action="store_true", help="Run scripts/doctor_devs.py before starting")
    parser.add_argument("--no-port-cleanup", action="store_true", help="Fail if required ports are occupied")
