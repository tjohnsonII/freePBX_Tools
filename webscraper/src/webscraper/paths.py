from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def var_dir() -> Path:
    return project_root() / "var"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    return ensure_dir(var_dir() / "runs")


def discovery_dir() -> Path:
    return ensure_dir(var_dir() / "discovery")


def profiles_dir() -> Path:
    return ensure_dir(var_dir() / "profiles")


def cookies_dir() -> Path:
    return ensure_dir(var_dir() / "cookies")


def db_dir() -> Path:
    return ensure_dir(var_dir() / "db")


def knowledge_base_dir() -> Path:
    return ensure_dir(db_dir() / "knowledge_base")


def tickets_db_path() -> Path:
    return db_dir() / "tickets.sqlite"


def discovery_db_path() -> Path:
    return discovery_dir() / "tickets.db"


def handles_master_path() -> Path:
    return project_root() / "configs" / "handles" / "handles_master.txt"


def new_run_dir(prefix: str = "run") -> Path:
    run_id = f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    return ensure_dir(runs_dir() / run_id)


def set_latest_run(run_dir: Path) -> Path:
    latest_ptr = latest_run_pointer_path()
    latest_ptr.write_text(run_dir.name + "\n", encoding="utf-8")
    return latest_ptr


def latest_run_pointer_path() -> Path:
    return runs_dir() / "LATEST_RUN.txt"


def latest_run_dir() -> Path:
    ptr = latest_run_pointer_path()
    legacy_ptr = runs_dir() / "latest.txt"
    chosen = ptr if ptr.exists() else legacy_ptr
    if chosen.exists():
        run_name = chosen.read_text(encoding="utf-8").strip()
        if run_name:
            candidate = runs_dir() / run_name
            if candidate.exists():
                return candidate
    return runs_dir() / "latest"


def tickets_all_json_path(run_dir: Path | None = None) -> Path:
    if run_dir is not None:
        return run_dir / "tickets_all.json"
    return latest_run_dir() / "tickets_all.json"


def runtime_profile_dir(browser: str = "edge") -> Path:
    prefix = "edge" if browser.lower().startswith("edge") else "chrome"
    return ensure_dir(profiles_dir() / prefix / "default")


def env_or_default_path(env_name: str, default: Path) -> str:
    explicit = os.environ.get(env_name)
    return str(Path(explicit).expanduser().resolve()) if explicit else str(default.resolve())
