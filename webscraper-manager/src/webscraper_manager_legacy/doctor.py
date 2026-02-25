from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import ManagerConfig, detect_scraper_python

EXIT_DOCTOR_ISSUES = 10
REQUIRED_MODULES = ["selenium", "requests", "lxml", "bs4", "websocket"]


@dataclass
class Finding:
    key: str
    status: str
    message: str
    fix: str | None = None
    details: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "message": self.message,
            "fix": self.fix,
            "details": self.details or {},
        }


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _command_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        out = subprocess.check_output([path, "--version"], text=True, stderr=subprocess.STDOUT, timeout=5)
        return out.strip()
    except Exception:
        return None


def _path_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


def run_doctor(config: ManagerConfig) -> list[Finding]:
    findings: list[Finding] = []

    py_ok = sys.version_info >= (3, 10)
    findings.append(
        Finding(
            key="python_version",
            status="ok" if py_ok else "error",
            message=f"Python {sys.version.split()[0]}",
            fix="Install Python >=3.10 and rerun" if not py_ok else None,
        )
    )

    expected = detect_scraper_python(config.repo_root)
    current = Path(sys.executable)
    in_venv = current.resolve() == expected.resolve()
    findings.append(
        Finding(
            key="venv",
            status="ok" if in_venv else "warn",
            message=f"Interpreter: {current}",
            fix=f"Use {expected} -m webscraper_manager ..." if not in_venv else None,
            details={"expected": str(expected)},
        )
    )

    for module_name in REQUIRED_MODULES:
        installed = importlib.util.find_spec(module_name) is not None
        findings.append(
            Finding(
                key=f"dep_{module_name}",
                status="ok" if installed else "error",
                message=f"Dependency {module_name} {'found' if installed else 'missing'}",
                fix="Run webscraper-manager fix" if not installed else None,
            )
        )

    for key, path in {
        "chrome_binary": config.chrome_binary,
        "edge_binary": config.edge_binary,
        "chromedriver": config.chromedriver,
        "edgedriver": config.edgedriver,
    }.items():
        exists = _path_exists(path)
        findings.append(
            Finding(
                key=key,
                status="ok" if exists else "warn",
                message=f"{key}={path or 'not set'}",
                fix=f"Set {key} in .webscraper_manager/config.json" if not exists else None,
                details={"version": _command_version(path)},
            )
        )

    webscraper_expected = [
        config.webscraper_dir / "requirements.txt",
        config.webscraper_dir / "src" / "webscraper",
        config.webscraper_dir / "ticket-ui" / "package.json",
    ]
    for path in webscraper_expected:
        findings.append(
            Finding(
                key=f"path_{path.name}",
                status="ok" if path.exists() else "error",
                message=f"{path} {'exists' if path.exists() else 'missing'}",
                fix="Restore webscraper project files" if not path.exists() else None,
            )
        )

    is_up = _is_port_open("127.0.0.1", 8787)
    findings.append(
        Finding(
            key="port_8787",
            status="ok" if is_up else "warn",
            message="Port 8787 listening" if is_up else "Port 8787 not listening",
            fix="Run webscraper-manager start ui" if not is_up else None,
        )
    )

    try:
        resp = requests.get(f"{config.base_url}/api/events/latest", params={"limit": 1}, timeout=3)
        api_ok = resp.status_code == 200
        findings.append(
            Finding(
                key="api_latest",
                status="ok" if api_ok else "warn",
                message=f"/api/events/latest -> {resp.status_code}",
                fix="Start the ticket UI/API stack" if not api_ok else None,
                details={"body": resp.text[:160]},
            )
        )
    except requests.RequestException as exc:
        findings.append(
            Finding(
                key="api_latest",
                status="warn",
                message=f"API check failed: {exc}",
                fix="Run webscraper-manager start ui",
            )
        )

    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(f.status == "error" for f in findings)


def has_issues(findings: list[Finding]) -> bool:
    return any(f.status in {"error", "warn"} for f in findings)
