from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ENVS = {
    ".venv-web-manager": ["uvicorn", "fastapi"],
    ".venv-webscraper": [],
}

MANAGER_UI = ROOT / "manager-ui"
MANAGER_UI_PACKAGE_JSON = MANAGER_UI / "package.json"
MANAGER_UI_NODE_MODULES = MANAGER_UI / "node_modules"
MANAGER_UI_LOCKFILE = MANAGER_UI / "package-lock.json"


def venv_python(venv_name: str) -> Path:
    return ROOT / venv_name / "Scripts" / "python.exe"


def module_ok(py: Path, module: str) -> bool:
    result = subprocess.run(
        [str(py), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def check_python_envs() -> int:
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


def check_frontend() -> int:
    rc = 0

    if not MANAGER_UI_PACKAGE_JSON.exists():
        print("manager-ui: package.json missing")
        return 1

    if not MANAGER_UI_NODE_MODULES.exists():
        print("manager-ui: node_modules missing")
        rc = 1
    else:
        print("manager-ui: OK")

    lockfile_state = "present" if MANAGER_UI_LOCKFILE.exists() else "missing"
    print(f"manager-ui: package-lock.json {lockfile_state}")

    return rc


def main() -> int:
    rc = 0
    rc |= check_python_envs()
    rc |= check_frontend()
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
