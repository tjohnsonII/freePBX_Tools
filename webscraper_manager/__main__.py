from __future__ import annotations

import importlib
import os
import subprocess
import sys

REQUIRED_MODULES = ["typer", "rich", "psutil", "packaging"]
BOOTSTRAP_ENV_VAR = "WS_MANAGER_BOOTSTRAPPED"


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
    os.environ[BOOTSTRAP_ENV_VAR] = "1"
    os.execv(sys.executable, [sys.executable, *sys.argv])


ensure_runtime_dependencies()

from webscraper_manager.cli import main

if __name__ == "__main__":
    main()
