from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    add_common_args,
    ensure_paths_exist,
    ensure_python_env,
    inspect_web_stack,
    npm_executable,
    print_inspection,
    repo_root,
    run_doctor,
    save_service_state,
    set_verbose,
    start_detached,
    stop_service,
    update_service_state,
    wait_for_dev_server_ready,
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


def _start_worker(root: Path, args: argparse.Namespace) -> dict[str, object]:
    worker_py = ensure_python_env(root, ".venv-webscraper", bootstrap=not args.no_bootstrap)
    worker_cmd, worker_cwd, worker_enabled = _load_worker_config(root)
    if not worker_enabled:
        print("[warn] worker.enabled=false in config; explicit launch mode still starting worker.")

    if worker_cmd and worker_cmd[0].lower() in {"python", "py", "python3", "python.exe"}:
        worker_cmd[0] = str(worker_py)

    cmd_str = " ".join(worker_cmd)
    if "headless" in cmd_str.lower():
        print("[warn] worker command includes headless mode; launcher records this explicitly.")

    stop_service(root, "webscraper_worker_service")
    if args.dry_run:
        return {
            "service_name": "webscraper_worker",
            "started": False,
            "mode": "worker",
            "command": worker_cmd,
            "readiness_status": "dry-run",
            "readiness_reason": "dry-run mode",
            "degraded": False,
            "url": None,
            "pid": None,
            "log_file": None,
        }

    edgedriver_path = "/root/.cache/selenium/msedgedriver/linux64/147.0.3912.72/msedgedriver"
    chrome_profile = str(root / "webscraper" / "var" / "chrome-profile")
    worker_env: dict[str, str] = {
        "DISPLAY": ":99",
        "WEBSCRAPER_BROWSER": "chrome",
        "WEBSCRAPER_CHROME_PROFILE_DIR": chrome_profile,
    }
    if os.path.exists(edgedriver_path):
        worker_env["EDGEDRIVER_PATH"] = edgedriver_path
    entry = start_detached(root=root, service_name="webscraper_worker_service", cmd=worker_cmd, cwd=worker_cwd, env_overrides=worker_env)
    save_service_state(root, entry)
    wait_for_process_stable(int(entry["pid"]), timeout_s=args.readiness_timeout, section="ready", min_alive_s=4.0)
    update_service_state(root, "webscraper_worker_service", readiness_status="ready", readiness_reason="worker process stable", mode="worker", degraded=False)
    return {
        "service_name": "webscraper_worker",
        "started": True,
        "mode": "worker",
        "command": worker_cmd,
        "readiness_status": "ready",
        "readiness_reason": "worker process stable",
        "degraded": False,
        "url": None,
        "pid": entry["pid"],
        "log_file": entry["log"],
    }


def _start_api(root: Path, args: argparse.Namespace) -> dict[str, object]:
    py = ensure_python_env(root, ".venv-webscraper", bootstrap=not args.no_bootstrap)
    api_cmd = [str(py), "-m", "uvicorn", "webscraper.ticket_api.app:app", "--host", args.api_host, "--port", str(args.api_port)]
    stop_service(root, "webscraper_ticket_api")
    if args.dry_run:
        return {
            "service_name": "webscraper_api",
            "started": False,
            "mode": "api",
            "command": api_cmd,
            "readiness_status": "dry-run",
            "readiness_reason": "dry-run mode",
            "degraded": False,
            "url": f"http://{args.api_host}:{args.api_port}",
            "pid": None,
            "log_file": None,
        }
    chrome_profile = str(root / "webscraper" / "var" / "chrome-profile")
    api_env: dict[str, str] = {"DISPLAY": ":99"}
    if os.path.isdir(chrome_profile):
        api_env["WEBSCRAPER_CHROME_PROFILE_DIR"] = chrome_profile
    entry = start_detached(root=root, service_name="webscraper_ticket_api", cmd=api_cmd, cwd=root,
                           env_overrides=api_env)
    save_service_state(root, entry)
    wait_for_process_stable(int(entry["pid"]), timeout_s=10, section="ready", min_alive_s=3.0)
    health_url = f"http://{args.api_host}:{args.api_port}/api/health"
    wait_for_http(health_url, timeout_s=args.readiness_timeout, section="ready")
    update_service_state(root, "webscraper_ticket_api", readiness_status="ready", readiness_reason=f"HTTP probe passed at {health_url}", mode="api", degraded=False, url=health_url)
    return {
        "service_name": "webscraper_api",
        "started": True,
        "mode": "api",
        "command": api_cmd,
        "readiness_status": "ready",
        "readiness_reason": f"HTTP probe passed at {health_url}",
        "degraded": False,
        "url": f"http://{args.api_host}:{args.api_port}",
        "pid": entry["pid"],
        "log_file": entry["log"],
    }


def _start_ui(root: Path, args: argparse.Namespace) -> dict[str, object]:
    if not (root / "webscraper" / "ticket-ui" / "package.json").exists():
        return {
            "service_name": "webscraper_ui",
            "started": False,
            "mode": "ui",
            "command": [],
            "readiness_status": "unavailable",
            "readiness_reason": "No standalone webscraper ticket-ui project detected",
            "degraded": True,
            "url": None,
            "pid": None,
            "log_file": None,
        }

    ui_cmd = [npm_executable(), "--prefix", "webscraper/ticket-ui", "run", "start", "--", "--port", str(args.ui_port), "--hostname", args.ui_host]
    stop_service(root, "webscraper_ticket_ui")
    if args.dry_run:
        return {
            "service_name": "webscraper_ui",
            "started": False,
            "mode": "ui",
            "command": ui_cmd,
            "readiness_status": "dry-run",
            "readiness_reason": "dry-run mode",
            "degraded": False,
            "url": f"http://{args.ui_host}:{args.ui_port}",
            "pid": None,
            "log_file": None,
        }

    ui_env = {
        "TICKET_API_PROXY_TARGET": f"http://{args.api_host}:{args.api_port}",
        "NEXT_PUBLIC_TICKET_API_PROXY_TARGET": f"http://{args.api_host}:{args.api_port}",
    }
    entry = start_detached(root=root, service_name="webscraper_ticket_ui", cmd=ui_cmd, cwd=root, env_overrides=ui_env)
    save_service_state(root, entry)
    reason = wait_for_dev_server_ready(
        pid=int(entry["pid"]),
        host=args.ui_host,
        port=args.ui_port,
        timeout_s=args.readiness_timeout,
        http_paths=["/", "/auth"],
        log_path=Path(entry["log"]),
        section="ready",
        allow_open_port_fallback=False,
        success_markers=["Ready in", "Local:"],
    )
    update_service_state(root, "webscraper_ticket_ui", readiness_status="ready", readiness_reason=reason, mode="ui", degraded=False, url=f"http://{args.ui_host}:{args.ui_port}")
    return {
        "service_name": "webscraper_ui",
        "started": True,
        "mode": "ui",
        "command": ui_cmd,
        "readiness_status": "ready",
        "readiness_reason": reason,
        "degraded": False,
        "url": f"http://{args.ui_host}:{args.ui_port}",
        "pid": entry["pid"],
        "log_file": entry["log"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch webscraper runtime roles (worker/ui/api/combined).")
    add_common_args(parser)
    parser.add_argument("--mode", choices=["worker", "ui", "api", "combined"], default="worker")
    parser.add_argument("--readiness-timeout", type=int, default=45)
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8788)
    parser.add_argument("--ui-host", default="127.0.0.1")
    parser.add_argument("--ui-port", type=int, default=3005)
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    try:
        set_verbose(args.verbose)
        if args.inspect:
            print_inspection(root, browser_mode="none")
            exists = inspect_web_stack(root).get("services", {}).get("webscraper_ui", {}).get("exists")
            if not exists:
                print("[inspect] webscraper_ui: unavailable (no standalone UI)")
            return 0

        ensure_paths_exist(root, ["webscraper/__main__.py", "scripts/bootstrap_venv.py"], section="preflight")
        if args.doctor:
            run_doctor(root)

        results: list[dict[str, object]] = []
        if args.mode in {"worker", "combined"}:
            results.append(_start_worker(root, args))
        if args.mode in {"api", "combined"}:
            results.append(_start_api(root, args))
        if args.mode in {"ui", "combined"}:
            results.append(_start_ui(root, args))

        for item in results:
            print(f"[startup] {item['service_name']} started={item['started']} readiness={item['readiness_status']} reason={item['readiness_reason']}")
        print("[success] webscraper launcher completed")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
