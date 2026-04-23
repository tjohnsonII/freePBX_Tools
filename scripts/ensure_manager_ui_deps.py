from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER_UI = ROOT / "manager-ui"
NODE_MODULES = MANAGER_UI / "node_modules"
PACKAGE_JSON = MANAGER_UI / "package.json"
PACKAGE_LOCK = MANAGER_UI / "package-lock.json"


def npm_executable() -> str:
    if sys.platform.startswith("win"):
        return "npm.cmd"
    return "npm"


def ensure_deps() -> int:
    if not PACKAGE_JSON.exists():
        print("[manager-ui deps] ERROR: manager-ui/package.json is missing")
        return 1

    if NODE_MODULES.exists():
        lock_state = "present" if PACKAGE_LOCK.exists() else "missing"
        print(f"[manager-ui deps] OK: node_modules present (package-lock.json: {lock_state})")
        return 0

    npm = shutil.which(npm_executable()) or shutil.which("npm")
    if not npm:
        print("[manager-ui deps] ERROR: npm was not found in PATH")
        return 1

    print("[manager-ui deps] node_modules missing; installing dependencies...")
    result = subprocess.run(
        [npm, "--prefix", "manager-ui", "install"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("[manager-ui deps] ERROR: npm install failed")
        return result.returncode

    if not NODE_MODULES.exists():
        print("[manager-ui deps] ERROR: install finished but node_modules is still missing")
        return 1

    print("[manager-ui deps] OK: dependencies installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(ensure_deps())
