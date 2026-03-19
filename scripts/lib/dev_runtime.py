from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import shlex
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


VERBOSE = False


def set_verbose(enabled: bool) -> None:
    global VERBOSE
    VERBOSE = bool(enabled)


def vlog(section: str, message: str) -> None:
    if VERBOSE:
        log(section, message)


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
    log(section, f"Running: {shlex.join(cmd)}")
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


def _normalize_http_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for path in paths:
        value = str(path or "").strip()
        if not value:
            continue
        if not value.startswith("/"):
            value = f"/{value}"
        if value not in normalized:
            normalized.append(value)
    return normalized


def _probe_http_paths(
    *,
    host: str,
    port: int,
    paths: list[str],
    section: str,
) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                status = int(response.getcode() or 0)
            log(section, f"http_probe path={path} status={status}")
            if status < 500:
                return f"ready via HTTP {status} {path}", errors
            errors.append(f"{path}: status={status}")
        except urllib.error.HTTPError as exc:
            status = int(exc.code or 0)
            log(section, f"http_probe path={path} status={status}")
            if status < 500:
                return f"ready via HTTP {status} {path}", errors
            errors.append(f"{path}: status={status}")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log(section, f"http_probe path={path} error={detail}")
            errors.append(f"{path}: {detail}")
    return None, errors


def _read_log_chunk(path: Path, offset: int) -> tuple[str, int]:
    if not path.exists():
        return "", offset
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        data = handle.read()
        return data, handle.tell()


def _contains_success_marker(text: str, markers: list[str]) -> str | None:
    lowered = text.lower()
    for marker in markers:
        if marker.lower() in lowered:
            return marker
    return None


def wait_for_dev_server_ready(
    *,
    pid: int,
    host: str,
    port: int,
    timeout_s: int,
    http_paths: list[str],
    log_path: Path | None,
    section: str = "ready",
    process_stable_s: float = 3.0,
    http_probe_interval_s: float = 1.0,
    open_port_fallback_s: float = 12.0,
    allow_open_port_fallback: bool = True,
    success_markers: list[str] | None = None,
) -> str:
    """Wait for dev server readiness using process, port, stdout markers, and HTTP probes."""
    paths = _normalize_http_paths(http_paths)
    if not paths:
        paths = ["/"]

    markers = success_markers or []
    deadline = time.monotonic() + timeout_s
    stable_at = time.monotonic() + process_stable_s
    next_http_probe_at = 0.0
    port_open_since: float | None = None
    process_stable_logged = False
    port_open_logged = False
    log_offset = 0
    recent_errors: list[str] = []

    log(section, f"readiness_start pid={pid} timeout_s={timeout_s} paths={paths}")
    while time.monotonic() < deadline:
        if not is_pid_alive(pid):
            raise LauncherError(f"Frontend process died before readiness completed (pid={pid}).")

        if not process_stable_logged and time.monotonic() >= stable_at:
            process_stable_logged = True
            log(section, f"pid_stable pid={pid}")

        if markers and log_path:
            chunk, log_offset = _read_log_chunk(log_path, log_offset)
            marker = _contains_success_marker(chunk, markers)
            if marker:
                reason = f"ready via stdout marker '{marker}'"
                log(section, f"readiness_success reason={reason}")
                return reason

        port_open = is_port_open(host, port, timeout=0.5)
        if port_open:
            if port_open_since is None:
                port_open_since = time.monotonic()
            if not port_open_logged:
                port_open_logged = True
                log(section, f"port_open host={host} port={port}")
        else:
            if port_open_logged:
                log(section, f"port_closed host={host} port={port}")
            port_open_logged = False
            port_open_since = None

        if port_open and time.monotonic() >= next_http_probe_at:
            next_http_probe_at = time.monotonic() + http_probe_interval_s
            reason, errors = _probe_http_paths(host=host, port=port, paths=paths, section=section)
            if reason:
                log(section, f"readiness_success reason={reason}")
                return reason
            recent_errors.extend(errors)
            recent_errors = recent_errors[-5:]

        if (
            allow_open_port_fallback
            and process_stable_logged
            and port_open_since is not None
            and (time.monotonic() - port_open_since) >= open_port_fallback_s
        ):
            reason = (
                "ready via open port fallback "
                f"(host={host} port={port} stable_for={int(open_port_fallback_s)}s)"
            )
            log(section, f"readiness_success reason={reason}")
            return reason

        time.sleep(0.5)

    details = "; ".join(recent_errors[-5:]) if recent_errors else "none"
    raise LauncherError(
        "Frontend readiness failed "
        f"(pid={pid}, host={host}, port={port}, timeout={timeout_s}s). "
        f"Last probe errors: {details}"
    )


def _creationflags() -> int:
    if not is_windows():
        return 0
    new_group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return new_group | no_window


@dataclass(frozen=True)
class BrowserLaunchDetails:
    mode: str
    browser_path: str | None
    user_data_dir: str | None
    profile_directory: str | None
    url: str | None
    command: list[str]
    launched: bool
    reason: str


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
    log("launch", f"Command: {shlex.join(cmd)}")
    log("launch", f"Log file: {log_path}")

    return {
        "service": service_name,
        "pid": proc.pid,
        "cmd": cmd,
        "command": shlex.join(cmd),
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


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if is_windows():
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False
        output = (proc.stdout or "").strip().lower()
        return bool(output and "no tasks are running" not in output and f"\"{pid}\"" in output)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_process_stable(pid: int, *, timeout_s: int, section: str = "wait", min_alive_s: float = 3.0) -> None:
    deadline = time.time() + timeout_s
    stable_until = time.time() + min_alive_s
    while time.time() < deadline:
        if not is_pid_alive(pid):
            raise LauncherError(f"Process exited before reaching stable state (pid={pid}).")
        if time.time() >= stable_until:
            log(section, f"Process is stable (pid={pid})")
            return
        time.sleep(0.5)
    raise LauncherError(f"Timed out waiting for process stability (pid={pid}, timeout={timeout_s}s).")


def prune_stale_service_state(root: Path, *, section: str = "state") -> None:
    state_path = root / RUNTIME_STATE_FILE
    state = _load_state(state_path)
    services = state.get("services", {})
    if not isinstance(services, dict):
        return
    stale = [name for name, info in services.items() if not is_pid_alive(int(info.get("pid", 0) or 0))]
    for name in stale:
        services.pop(name, None)
        log(section, f"Removed stale runtime service entry: {name}")
    if stale:
        state["services"] = services
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def save_service_state(root: Path, entry: dict[str, Any]) -> None:
    state_path = root / RUNTIME_STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    prune_stale_service_state(root)
    state = _load_state(state_path)
    services = state.setdefault("services", {})
    services[entry["service"]] = entry
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    log("state", f"Updated runtime state: {state_path}")


def update_service_state(root: Path, service_name: str, **fields: Any) -> None:
    if not fields:
        return
    state_path = root / RUNTIME_STATE_FILE
    state = _load_state(state_path)
    services = state.get("services", {})
    if not isinstance(services, dict):
        return
    service = services.get(service_name)
    if not isinstance(service, dict):
        return
    service.update(fields)
    services[service_name] = service
    state["services"] = services
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    log("state", f"Updated service state fields for {service_name}: {', '.join(sorted(fields.keys()))}")


def load_services(root: Path) -> dict[str, dict[str, Any]]:
    prune_stale_service_state(root)
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


def clear_runtime_state(root: Path) -> None:
    state_path = root / RUNTIME_STATE_FILE
    if state_path.exists():
        state_path.unlink()
        log("state", f"Removed runtime state file: {state_path}")


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
    log("browser", f"Opened URL: {url}")


def launch_browser_mode(
    *,
    mode: str,
    url: str,
    profile_directory: str = "Default",
    persistent_user_data_dir: Path | None = None,
    browser_path: str | None = None,
) -> BrowserLaunchDetails:
    normalized = (mode or "none").strip().lower()
    if normalized in {"none", "off", "disabled"}:
        return BrowserLaunchDetails(
            mode="none",
            browser_path=None,
            user_data_dir=None,
            profile_directory=None,
            url=url,
            command=[],
            launched=False,
            reason="Browser launch disabled by --browser none.",
        )

    if is_windows():
        resolved_browser = browser_path or shutil.which("msedge") or shutil.which("msedge.exe")
        if not resolved_browser:
            return BrowserLaunchDetails(
                mode=normalized,
                browser_path=None,
                user_data_dir=None,
                profile_directory=profile_directory,
                url=url,
                command=[],
                launched=False,
                reason="Microsoft Edge executable was not found in PATH.",
            )
        cmd = [resolved_browser, "--no-first-run", "--no-default-browser-check"]
        user_data_dir: str | None = None
        if normalized == "persistent-profile":
            if persistent_user_data_dir is None:
                return BrowserLaunchDetails(
                    mode=normalized,
                    browser_path=resolved_browser,
                    user_data_dir=None,
                    profile_directory=profile_directory,
                    url=url,
                    command=[],
                    launched=False,
                    reason="Persistent profile mode requires a user-data-dir.",
                )
            persistent_user_data_dir.mkdir(parents=True, exist_ok=True)
            user_data_dir = str(persistent_user_data_dir)
            cmd.append(f"--user-data-dir={user_data_dir}")
            cmd.append(f"--profile-directory={profile_directory}")
        elif normalized == "existing-profile":
            cmd.append(f"--profile-directory={profile_directory}")
        else:
            return BrowserLaunchDetails(
                mode=normalized,
                browser_path=resolved_browser,
                user_data_dir=None,
                profile_directory=profile_directory,
                url=url,
                command=[],
                launched=False,
                reason=f"Unsupported browser mode: {mode}",
            )
        cmd.append(url)
        creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        return BrowserLaunchDetails(
            mode=normalized,
            browser_path=resolved_browser,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            url=url,
            command=cmd,
            launched=True,
            reason="Browser launched.",
        )

    # Non-Windows fallback.
    maybe_open_browser(url, open_browser=True)
    return BrowserLaunchDetails(
        mode=normalized,
        browser_path=None,
        user_data_dir=None,
        profile_directory=profile_directory,
        url=url,
        command=[],
        launched=True,
        reason="Opened browser via platform default launcher.",
    )


def inspect_web_stack(root: Path) -> dict[str, Any]:
    ticket_ui_exists = (root / "webscraper" / "ticket-ui" / "package.json").exists()
    ticket_api_exists = (root / "webscraper" / "src" / "webscraper" / "ticket_api" / "app.py").exists()
    return {
        "services": {
            "manager_backend": {"exists": (root / "webscraper_manager" / "api" / "server.py").exists(), "url": "http://127.0.0.1:8787/api/health"},
            "manager_frontend": {"exists": (root / "manager-ui" / "package.json").exists(), "url": "http://127.0.0.1:3004/dashboard"},
            "webscraper_worker": {"exists": (root / "webscraper" / "__main__.py").exists(), "url": None},
            "webscraper_api": {"exists": ticket_api_exists, "url": "http://127.0.0.1:8788/api/health"},
            "webscraper_ui": {"exists": ticket_ui_exists, "url": "http://127.0.0.1:3005"},
        }
    }


def print_inspection(root: Path, browser_mode: str) -> None:
    payload = inspect_web_stack(root)
    log("inspect", f"browser_mode={browser_mode}")
    for name, info in payload.get("services", {}).items():
        exists = bool(info.get("exists"))
        url = info.get("url") or "-"
        log("inspect", f"{name}: exists={exists} url={url}")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-bootstrap", action="store_true", help="Do not auto-bootstrap missing dependencies")
    parser.add_argument("--doctor", action="store_true", help="Run scripts/doctor_devs.py before starting")
    parser.add_argument("--no-port-cleanup", action="store_true", help="Fail if required ports are occupied")
    parser.add_argument("--dry-run", action="store_true", help="Print launch decisions without starting services")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose launcher logging")
    parser.add_argument("--inspect", action="store_true", help="Print discoverable services and exit")
