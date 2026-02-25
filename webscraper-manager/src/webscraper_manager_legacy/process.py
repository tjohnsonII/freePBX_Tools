from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

from .config import ManagerConfig, ensure_runtime_dirs

EXIT_START_FAILED = 20


@dataclass
class ManagedProcess:
    name: str
    pid: int
    command: list[str]


def _creationflags(detach: bool) -> int:
    if os.name != "nt" or not detach:
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]


def _pid_file(config: ManagerConfig, name: str) -> Path:
    return ensure_runtime_dirs(config)["pids"] / f"{name}.json"


def _save_pid(config: ManagerConfig, proc: ManagedProcess) -> None:
    _pid_file(config, proc.name).write_text(
        json.dumps({"pid": proc.pid, "command": proc.command}, indent=2),
        encoding="utf-8",
    )


def _load_pid(config: ManagerConfig, name: str) -> ManagedProcess | None:
    path = _pid_file(config, name)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ManagedProcess(name=name, pid=int(data["pid"]), command=list(data.get("command", [])))


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_ui(config: ManagerConfig, detach: bool = False) -> ManagedProcess:
    ui_dir = config.webscraper_dir / "ticket-ui"
    if (ui_dir / "pnpm-lock.yaml").exists():
        command = ["pnpm", "run", "dev"]
    elif (ui_dir / "yarn.lock").exists():
        command = ["yarn", "dev"]
    else:
        command = ["npm", "run", "dev"]

    proc = subprocess.Popen(command, cwd=ui_dir, creationflags=_creationflags(detach))
    managed = ManagedProcess(name="ui", pid=proc.pid, command=command)
    _save_pid(config, managed)
    return managed


def start_scraper(config: ManagerConfig, detach: bool = False, watch: bool = False) -> ManagedProcess:
    python_bin = config.scraper_python or sys.executable
    command = [python_bin, "-m", "webscraper"]
    if watch:
        command += ["--loop"]

    proc = subprocess.Popen(command, cwd=config.repo_root, creationflags=_creationflags(detach))
    managed = ManagedProcess(name="scraper", pid=proc.pid, command=command)
    _save_pid(config, managed)
    return managed


def stop_managed_process(config: ManagerConfig, name: str) -> bool:
    info = _load_pid(config, name)
    if not info:
        return False

    try:
        proc = psutil.Process(info.pid)
        proc.terminate()
        proc.wait(timeout=8)
    except psutil.TimeoutExpired:
        proc.kill()
    except psutil.NoSuchProcess:
        pass

    pid_file = _pid_file(config, name)
    if pid_file.exists():
        pid_file.unlink()
    return True


def relevant_processes() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "next dev" in cmdline or "webscraper" in cmdline:
                rows.append({"pid": proc.pid, "name": proc.info.get("name", ""), "cmdline": cmdline[:240]})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return rows


def stop_everything(config: ManagerConfig) -> list[str]:
    stopped: list[str] = []
    for name in ["scraper", "ui"]:
        if stop_managed_process(config, name):
            stopped.append(name)
    return stopped
