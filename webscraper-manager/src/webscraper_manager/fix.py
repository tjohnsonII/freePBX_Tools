from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import ManagerConfig, ensure_runtime_dirs, save_config


@dataclass
class FixAction:
    name: str
    ok: bool
    message: str


def _run(command: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        if proc.returncode == 0:
            return True, proc.stdout.strip() or "ok"
        return False, (proc.stderr.strip() or proc.stdout.strip() or "failed")
    except Exception as exc:
        return False, str(exc)


def apply_safe_fixes(config: ManagerConfig) -> list[FixAction]:
    actions: list[FixAction] = []

    ensure_runtime_dirs(config)
    actions.append(FixAction(name="runtime_dirs", ok=True, message="Created runtime folders"))

    pip_python = config.scraper_python or sys.executable
    req_file = config.webscraper_dir / "requirements.txt"
    if req_file.exists():
        ok, msg = _run([pip_python, "-m", "pip", "install", "-r", str(req_file)])
        actions.append(FixAction(name="install_webscraper_requirements", ok=ok, message=msg))

    ok, msg = _run([pip_python, "-m", "pip", "install", "typer", "rich", "psutil", "requests", "selenium"])
    actions.append(FixAction(name="install_manager_dependencies", ok=ok, message=msg))

    if not config.chrome_binary:
        default_chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if default_chrome.exists():
            config.chrome_binary = str(default_chrome)
            actions.append(FixAction(name="detect_chrome", ok=True, message=f"Detected {default_chrome}"))

    if not config.edge_binary:
        default_edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        if not default_edge.exists():
            default_edge = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
        if default_edge.exists():
            config.edge_binary = str(default_edge)
            actions.append(FixAction(name="detect_edge", ok=True, message=f"Detected {default_edge}"))

    if not config.chromedriver:
        found = shutil.which("chromedriver")
        if found:
            config.chromedriver = found
            actions.append(FixAction(name="detect_chromedriver", ok=True, message=f"Detected {found}"))
        else:
            actions.append(
                FixAction(
                    name="detect_chromedriver",
                    ok=False,
                    message="chromedriver missing. Download from https://googlechromelabs.github.io/chrome-for-testing/",
                )
            )

    if not config.edgedriver:
        found = shutil.which("msedgedriver")
        if found:
            config.edgedriver = found
            actions.append(FixAction(name="detect_edgedriver", ok=True, message=f"Detected {found}"))
        else:
            actions.append(
                FixAction(
                    name="detect_edgedriver",
                    ok=False,
                    message="msedgedriver missing. Download from https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/",
                )
            )

    if shutil.which("dot"):
        actions.append(FixAction(name="graphviz", ok=True, message="Graphviz dot found on PATH"))
    else:
        actions.append(FixAction(name="graphviz", ok=False, message="Graphviz not found on PATH (optional)"))

    save_config(config)
    actions.append(FixAction(name="save_config", ok=True, message=f"Updated {config.config_file}"))
    return actions
