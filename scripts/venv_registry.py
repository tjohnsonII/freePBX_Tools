from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


MANAGED_ENVS: dict[str, dict[str, object]] = {
    "webscraper": {
        "venv": ".venv-webscraper",
        "app": "webscraper stack + webscraper_manager CLI",
        "requirements": "webscraper/requirements.txt",
        "imports": ["selenium", "bs4", "lxml", "requests", "multipart"],
        "packages": [],
        "notes": "Used by VS Code webscraper stack tasks via scripts/run_py.bat.",
    },
    "web_manager": {
        "venv": ".venv-web-manager",
        "app": "webscraper_manager API backend",
        "requirements": "webscraper_manager/requirements.txt",
        "imports": ["fastapi", "uvicorn", "typer", "rich", "psutil", "packaging"],
        "packages": [],
        "notes": "Used by webscraper dashboard backend task.",
    },
    "deploy_backend": {
        "venv": "freepbx-deploy-backend/.venv",
        "app": "freepbx-deploy-backend FastAPI service",
        "requirements": "freepbx-deploy-backend/requirements.txt",
        "imports": ["fastapi", "uvicorn", "pydantic", "multipart"],
        "packages": [],
        "notes": "Used by deploy-backend tasks through scripts/run_py.bat.",
    },
    "traceroute_backend": {
        "venv": "traceroute-visualizer-main/backend/.venv",
        "app": "traceroute visualizer FastAPI backend",
        "requirements": "traceroute-visualizer-main/backend/requirements.txt",
        "imports": ["fastapi", "uvicorn", "httpx"],
        "packages": [],
        "notes": "Documented backend requirements for traceroute stack.",
    },
}


def iter_managed_envs() -> list[tuple[str, dict[str, object]]]:
    return list(MANAGED_ENVS.items())


def get_env_config(env_id: str) -> dict[str, object] | None:
    return MANAGED_ENVS.get(env_id)


def normalize_venv_path(venv_path: str) -> str:
    normalized = venv_path.strip().replace("\\", "/").strip("/")
    return normalized.lower()


def find_env_id_by_venv_path(venv_path: str) -> str | None:
    target = normalize_venv_path(venv_path)
    for env_id, config in MANAGED_ENVS.items():
        configured = normalize_venv_path(str(config["venv"]))
        if configured == target:
            return env_id
    return None


def resolve_repo_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str)
    return path if path.is_absolute() else (REPO_ROOT / path)
