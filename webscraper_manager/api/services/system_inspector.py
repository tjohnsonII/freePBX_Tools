from __future__ import annotations

import os
import platform
import socket
import sys
from pathlib import Path
from typing import Any

import psutil


class SystemInspector:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def ports(self, targets: list[int] | None = None) -> dict[str, Any]:
        targets = targets or [8787, 3004]
        listeners = []
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                continue
            listeners.append({"port": conn.laddr.port, "pid": conn.pid})
        return {
            "listeners": listeners,
            "targets": {str(port): any(l["port"] == port for l in listeners) for port in targets},
        }

    def processes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline", "status"]):
            info = proc.info
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "status": info.get("status"),
                    "cmdline": " ".join(info.get("cmdline") or []),
                }
            )
        return rows[:100]

    def env(self) -> dict[str, str]:
        masked: dict[str, str] = {}
        for key, value in os.environ.items():
            if any(token in key.lower() for token in ["token", "secret", "password", "cookie", "key"]):
                masked[key] = "***MASKED***"
            else:
                masked[key] = value[:120]
        return masked

    def paths(self) -> dict[str, Any]:
        return {
            "repo_root": str(self.repo_root),
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "hostname": socket.gethostname(),
            "os": platform.platform(),
        }
