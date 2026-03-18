from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    add_common_args,
    ensure_paths_exist,
    ensure_python_env,
    repo_root,
    run_doctor,
    save_service_state,
    start_detached,
    stop_service,
    wait_for_http,
    wait_for_process_stable,
)


def _load_worker_config(root: Path) -> tuple[list[str], Path, bool]:
    config_path = root / ".webscraper_manager" / "services.json"
    default_cmd = ["python", "-m", "webscraper", "--mode", "incremental"]
    default_cwd = root
    worker_enabled = True

    if not config_path.exists():
        return default_cmd, default_cwd, worker_enabled

    try:
        services = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return default_cmd, default_cwd, worker_enabled

    worker_cfg = services.get("worker", {}) if isinstance(services, dict) else {}
    if isinstance(worker_cfg, dict):
        worker_enabled = bool(worker_cfg.get("enabled", True))
        cmd = worker_cfg.get("cmd")
        cwd = worker_cfg.get("cwd")
        if isinstance(cmd, list) and cmd:
            default_cmd = [str(part) for part in cmd]
        if isinstance(cwd, str) and cwd.strip():
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute():
                cwd_path = root / cwd_path
            default_cwd = cwd_path

    return default_cmd, default_cwd, worker_enabled


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch the webscraper worker process used by webscraper_manager."
    )
    add_common_args(parser)
    parser.add_argument("--readiness-timeout", type=int, default=30)
    parser.add_argument(
        "--manager-health-url",
        default="http://127.0.0.1:8787/api/health",
        help="Manager API health URL used for readiness context checks",
    )
    parser.add_argument(
        "--allow-manager-down",
        action="store_true",
        help="Do not fail startup when manager API health endpoint is unavailable",
    )
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    try:
        ensure_paths_exist(
            root,
            [
                "webscraper_manager/cli.py",
                "scripts/bootstrap_venv.py",
            ],
            section="preflight",
        )
        worker_py = ensure_python_env(root, ".venv-webscraper", bootstrap=not args.no_bootstrap)

        if args.doctor:
            run_doctor(root)

        worker_cmd, worker_cwd, worker_enabled = _load_worker_config(root)
        if not worker_enabled:
            print(
                "[warn] .webscraper_manager/services.json has worker.enabled=false; "
                "starting worker anyway because this launcher is worker-only."
            )
        if not worker_cwd.exists():
            raise LauncherError(f"Worker cwd does not exist: {worker_cwd}")

        if worker_cmd and worker_cmd[0].lower() in {"python", "py", "python3", "python.exe"}:
            worker_cmd[0] = str(worker_py)

        stop_service(root, "webscraper_worker_service")
        entry = start_detached(
            root=root,
            service_name="webscraper_worker_service",
            cmd=worker_cmd,
            cwd=worker_cwd,
        )
        save_service_state(root, entry)
        wait_for_process_stable(entry["pid"], timeout_s=args.readiness_timeout, section="ready", min_alive_s=5.0)

        try:
            wait_for_http(args.manager_health_url, timeout_s=5, section="ready")
        except LauncherError:
            if args.allow_manager_down:
                print(
                    f"[warn] manager API health check failed at {args.manager_health_url}; "
                    "worker is running and launcher is continuing (--allow-manager-down)."
                )
            else:
                raise LauncherError(
                    "Worker started, but manager API health check failed. "
                    "Start the manager backend first or pass --allow-manager-down."
                )

        print("[success] webscraper worker service started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
