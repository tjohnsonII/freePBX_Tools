from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lib.dev_runtime import clear_runtime_state, repo_root, stop_all_known_services, venv_python


def main() -> int:
    root = repo_root(Path(__file__))

    manager_py = venv_python(root, ".venv-web-manager")
    if manager_py.exists():
        subprocess.run(
            [str(manager_py), "-m", "webscraper_manager", "stop", "all", "--quiet"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "webscraper_manager", "stop", "all", "--quiet"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    stop_all_known_services(root, fallback_ports=[8787, 3004])
    clear_runtime_state(root)
    print("[success] stop routine completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
