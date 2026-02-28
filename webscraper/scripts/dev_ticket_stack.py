#!/usr/bin/env python3
"""Start ticket API + Next.js UI dev servers with shared console output."""

from __future__ import annotations

import os
import socket
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import importlib.util
from pathlib import Path
from typing import TextIO

API_HOST = "127.0.0.1"
API_PORT = "8787"
UI_PORT = "3004"
PROXY_TARGET = f"http://{API_HOST}:{API_PORT}"
STARTUP_TIMEOUT_SECONDS = 60


class ProcessGroup:
    def __init__(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []
        self._lock = threading.Lock()

    def add(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.append(process)

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._processes)

        for process in processes:
            if process.poll() is not None:
                continue
            process.terminate()

        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def stream_output(pipe: TextIO, prefix: str) -> None:
    for line in iter(pipe.readline, ""):
        print(f"[{prefix}] {line.rstrip()}")
    pipe.close()




def _is_port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

def _wait_for_tcp_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _wait_for_api_health(target: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"{target}/api/health"

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        except TimeoutError:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    ui_dir = repo_root / "webscraper" / "ticket-ui"

    if not ui_dir.exists():
        print(f"ticket-ui folder not found: {ui_dir}", file=sys.stderr)
        return 1

    npm_exe = "npm.cmd" if os.name == "nt" else "npm"

    if importlib.util.find_spec("multipart") is None:
        print(
            "[ERROR] Missing dependency python-multipart. Install it into .venv-webscraper with: "
            f"{sys.executable} -m pip install -r webscraper/requirements.txt -r webscraper/requirements_api.txt",
            file=sys.stderr,
        )
        return 1

    api_cmd = [
        sys.executable,
        "-m",
        "webscraper.ticket_api.app",
        "--host",
        API_HOST,
        "--port",
        API_PORT,
        "--reload",
    ]
    ui_cmd = [npm_exe, "run", "dev:ui"]

    ui_env = os.environ.copy()
    ui_env["PORT"] = UI_PORT
    ui_env["TICKET_API_PROXY_TARGET"] = PROXY_TARGET
    ui_env["NEXT_PUBLIC_TICKET_API_PROXY_TARGET"] = PROXY_TARGET

    process_group = ProcessGroup()
    stop_event = threading.Event()

    def handle_interrupt(_sig: int, _frame: object) -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        print("\nShutting down ticket stack...")
        process_group.terminate_all()

    signal.signal(signal.SIGINT, handle_interrupt)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_interrupt)

    print(f"Starting API on {PROXY_TARGET}")

    api_proc = subprocess.Popen(
        api_cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    process_group.add(api_proc)

    api_thread = threading.Thread(target=stream_output, args=(api_proc.stdout, "API"), daemon=True)
    api_thread.start()

    print("Waiting for API readiness…")
    if not _wait_for_tcp_port(API_HOST, int(API_PORT), STARTUP_TIMEOUT_SECONDS):
        print(
            f"[ERROR] API port {API_HOST}:{API_PORT} did not open within {STARTUP_TIMEOUT_SECONDS}s.\n"
            "Next steps:\n"
            "  1) Check whether another process is already using port 8787.\n"
            "  2) Start API directly: python -m webscraper.ticket_api.app --host 127.0.0.1 --port 8787 --reload\n"
            "  3) Review the [API] logs above for traceback details.",
            file=sys.stderr,
        )
        process_group.terminate_all()
        api_thread.join(timeout=1)
        return 1

    if not _wait_for_api_health(PROXY_TARGET, STARTUP_TIMEOUT_SECONDS):
        print(
            f"[ERROR] API did not report readiness at {PROXY_TARGET}/api/health within {STARTUP_TIMEOUT_SECONDS}s.\n"
            "Next steps:\n"
            "  1) Open http://127.0.0.1:8787/api/health in a browser/curl.\n"
            "  2) Start API directly with uvicorn/module command to verify startup.\n"
            "  3) Check the [API] logs above for dependency/import errors.",
            file=sys.stderr,
        )
        process_group.terminate_all()
        api_thread.join(timeout=1)
        return 1

    ui_proc: subprocess.Popen[str] | None = None
    threads = [api_thread]

    if _is_port_in_use(API_HOST, int(UI_PORT)):
        print(f"[WARN] UI port {UI_PORT} is already in use; skipping UI startup and keeping API alive.")
    else:
        print(f"API ready, starting UI on http://127.0.0.1:{UI_PORT} (proxy -> {PROXY_TARGET})")
        ui_proc = subprocess.Popen(
            ui_cmd,
            cwd=ui_dir,
            env=ui_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        process_group.add(ui_proc)

        ui_thread = threading.Thread(target=stream_output, args=(ui_proc.stdout, "UI"), daemon=True)
        ui_thread.start()
        threads.append(ui_thread)

    exit_code = 0
    try:
        while not stop_event.is_set():
            api_rc = api_proc.poll()
            ui_rc = ui_proc.poll() if ui_proc is not None else None

            if api_rc is not None or ui_rc is not None:
                stop_event.set()
                if api_rc not in (None, 0):
                    print(f"API exited with code {api_rc}", file=sys.stderr)
                    exit_code = api_rc
                if ui_rc not in (None, 0):
                    print(f"UI exited with code {ui_rc}", file=sys.stderr)
                    exit_code = ui_rc
                process_group.terminate_all()
                break

            stop_event.wait(0.2)
    finally:
        process_group.terminate_all()
        for thread in threads:
            thread.join(timeout=1)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
