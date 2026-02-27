import importlib
import os
import subprocess
import sys

REQUIRED_MODULES = [
    "psutil",
    # add other required modules here
]


def ensure_dependencies() -> bool:
    missing: list[str] = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)

    if not missing:
        return False

    print("\n[BOOTSTRAP] Missing dependencies detected:")
    for module_name in missing:
        print(f" - {module_name}")

    print("\n[BOOTSTRAP] Installing missing dependencies...\n")

    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        *missing,
    ])

    return True


# Prevent infinite restart loop
if os.environ.get("WS_MANAGER_BOOTSTRAPPED") != "1":
    if ensure_dependencies():
        print("\n[BOOTSTRAP] Restarting CLI...\n")
        os.environ["WS_MANAGER_BOOTSTRAPPED"] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)

from webscraper_manager.cli import main

if __name__ == "__main__":
    main()
