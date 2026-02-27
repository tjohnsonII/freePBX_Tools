from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_MODULES = ["typer", "rich", "psutil", "packaging"]
BOOTSTRAP_ENV_VAR = "WS_MANAGER_BOOTSTRAPPED"
ORIGINAL_CWD_ENV_VAR = "WS_MANAGER_ORIGINAL_CWD"

repo_root = Path(__file__).resolve().parents[1]
repo_root_str = str(repo_root)
if not sys.path or sys.path[0] != repo_root_str:
    if repo_root_str in sys.path:
        sys.path.remove(repo_root_str)
    sys.path.insert(0, repo_root_str)

_original_cwd = os.environ.get(ORIGINAL_CWD_ENV_VAR)
if _original_cwd:
    os.chdir(_original_cwd)


def _in_virtualenv() -> bool:
    if os.environ.get("VIRTUAL_ENV"):
        return True
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def _missing_modules() -> list[str]:
    missing: list[str] = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    return missing


def _install_missing(missing: list[str]) -> int:
    cmd = [sys.executable, "-m", "pip", "install", *missing]
    return subprocess.call(cmd)


def ensure_runtime_dependencies() -> None:
    original_cwd = os.getcwd()
    missing = _missing_modules()
    if not missing:
        return

    missing_text = ", ".join(missing)
    print(f"Missing manager dependencies: {missing_text}")

    if not _in_virtualenv():
        print("Do not run with global python. Use: .\\.venv-web-manager\\Scripts\\python.exe -m webscraper_manager ...")
        raise SystemExit(2)

    if os.environ.get(BOOTSTRAP_ENV_VAR) == "1":
        print("Dependency bootstrap already attempted and modules are still missing.")
        print("Run manually: python -m pip install -r webscraper_manager/requirements.txt")
        raise SystemExit(2)

    print("Installing missing dependencies into current virtual environment...")
    rc = _install_missing(missing)
    if rc != 0:
        print("Dependency installation failed. Run: python -m pip install -r webscraper_manager/requirements.txt")
        raise SystemExit(2)

    print("Restarting webscraper_manager...")
    args = [sys.executable, "-m", "webscraper_manager", *sys.argv[1:]]
    env = os.environ.copy()
    env[BOOTSTRAP_ENV_VAR] = "1"
    env[ORIGINAL_CWD_ENV_VAR] = original_cwd
    env["PYTHONPATH"] = repo_root_str + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    os.chdir(repo_root)
    os.execve(sys.executable, args, env)


ensure_runtime_dependencies()

from webscraper_manager.cli import main

if __name__ == "__main__":
    main()
