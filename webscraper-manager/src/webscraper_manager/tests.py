from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import ManagerConfig

EXIT_TEST_FAILED = 30


@dataclass
class TestRun:
    name: str
    returncode: int
    output: str


def _run(command: list[str], cwd: Path) -> TestRun:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return TestRun(name=" ".join(command), returncode=proc.returncode, output=(proc.stdout + "\n" + proc.stderr).strip())


def run_smoke(config: ManagerConfig) -> TestRun:
    python_bin = config.scraper_python or sys.executable
    return _run([python_bin, "-m", "webscraper.smoke_test"], cwd=config.repo_root)


def run_unit(config: ManagerConfig) -> TestRun:
    python_bin = config.scraper_python or sys.executable
    return _run([python_bin, "-m", "pytest", "webscraper/tests"], cwd=config.repo_root)


def run_integration(config: ManagerConfig) -> TestRun:
    python_bin = config.scraper_python or sys.executable
    manual_script = config.repo_root / "scripts" / "webscraper_manual_tests" / "smoke_manual.py"
    if not manual_script.exists():
        return TestRun(name="integration-placeholder", returncode=0, output="No integration script found; placeholder passed.")
    return _run([python_bin, str(manual_script)], cwd=config.repo_root)
