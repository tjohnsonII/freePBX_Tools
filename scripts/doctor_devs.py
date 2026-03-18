from __future__ import annotations

import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

ENVS = {
    ".venv-web-manager": ["uvicorn", "fastapi"],
    ".venv-webscraper": [],
}


def venv_python(venv_name: str) -> Path:
    return ROOT / venv_name / "Scripts" / "python.exe"


def module_ok(py: Path, module: str) -> bool:
    result = subprocess.run(
        [str(py), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def main() -> int:
    rc = 0
    for env, modules in ENVS.items():
        py = venv_python(env)
        if not py.exists():
            print(f"{env}: missing venv")
            rc = 1
            continue

        missing = [m for m in modules if not module_ok(py, m)]
        if missing:
            print(f"{env}: missing modules -> {', '.join(missing)}")
            rc = 1
        else:
            print(f"{env}: OK")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())