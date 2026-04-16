from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MANAGED_ENVS = {
    ".venv-web-manager": {
        "requirements": None,
        "packages": ["uvicorn", "fastapi"],
    },
    ".venv-webscraper": {
        # requirements.txt = scraper/browser deps (selenium etc.)
        # requirements_api.txt = API server deps (fastapi, uvicorn)
        # editable_install = installs the webscraper package itself so
        #   "webscraper.ticket_api.app" is importable from this venv
        "requirements": ROOT / "webscraper" / "requirements.txt",
        "extra_requirements": ROOT / "webscraper" / "requirements_api.txt",
        "editable_install": ROOT / "webscraper",
        "packages": [],
    },
}


def venv_python(venv_name: str) -> Path:
    import os
    if os.name == "nt":
        return ROOT / venv_name / "Scripts" / "python.exe"
    return ROOT / venv_name / "bin" / "python"


def create_venv(venv_name: str) -> None:
    venv_dir = ROOT / venv_name
    if venv_dir.exists():
        print(f"[bootstrap] {venv_name}: exists")
        return
    print(f"[bootstrap] {venv_name}: creating")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)


def module_installed(py: Path, module: str) -> bool:
    result = subprocess.run(
        [str(py), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def install_packages(py: Path, packages: list[str]) -> None:
    if not packages:
        return
    print(f"[bootstrap] installing packages: {' '.join(packages)}")
    subprocess.run([str(py), "-m", "pip", "install", *packages], check=True)


def install_requirements(py: Path, req_file: Path) -> None:
    print(f"[bootstrap] installing requirements from {req_file}")
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(req_file)], check=True)


def install_editable(py: Path, project_dir: Path) -> None:
    print(f"[bootstrap] installing editable package from {project_dir}")
    subprocess.run([str(py), "-m", "pip", "install", "-e", str(project_dir)], check=True)


def bootstrap_env(name: str, cfg: dict) -> None:
    create_venv(name)
    py = venv_python(name)

    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    req = cfg.get("requirements")
    extra_req = cfg.get("extra_requirements")
    editable = cfg.get("editable_install")
    packages = cfg.get("packages", [])

    if req and Path(req).exists():
        install_requirements(py, Path(req))

    if extra_req and Path(extra_req).exists():
        install_requirements(py, Path(extra_req))

    if editable and Path(editable).exists():
        install_editable(py, Path(editable))

    if req or extra_req or editable:
        return

    missing = [pkg for pkg in packages if not module_installed(py, pkg)]
    if missing:
        install_packages(py, missing)
    else:
        print(f"[bootstrap] {name}: dependencies OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Bootstrap all managed envs")
    args = parser.parse_args()

    if not args.all:
        print("Use --all")
        return 1

    for name, cfg in MANAGED_ENVS.items():
        bootstrap_env(name, cfg)

    print("[bootstrap] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())