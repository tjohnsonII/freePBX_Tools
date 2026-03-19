from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.dev_runtime import (
    LauncherError,
    ensure_manager_ui_dependencies,
    inspect_web_stack,
    launch_browser_mode,
    print_inspection,
    repo_root,
    run_checked,
    set_verbose,
    stop_all_known_services,
)


def _read_runtime_services(root: Path) -> dict[str, dict[str, Any]]:
    state_path = root / "var" / "web-app-launcher" / "run_state.json"
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    services = payload.get("services", {})
    return services if isinstance(services, dict) else {}


def _service_row(name: str, mode: str, cmd: list[str], state: dict[str, Any] | None, url: str | None) -> dict[str, Any]:
    state = state or {}
    return {
        "service_name": name,
        "pid": state.get("pid"),
        "mode": mode,
        "command": state.get("command") or " ".join(cmd),
        "log_file": state.get("log"),
        "readiness_status": state.get("readiness_status") or ("ready" if state.get("pid") else "not-started"),
        "readiness_reason": state.get("readiness_reason") or ("process started" if state.get("pid") else "service did not start"),
        "url": state.get("url") or url,
        "started": bool(state.get("pid")),
        "degraded": bool(state.get("degraded") or state.get("readiness_warning")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch manager backend + manager UI + webscraper roles with strict readiness.")
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--no-port-cleanup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="Print discovered services and exit")
    parser.add_argument("--readiness-timeout", type=int, default=180)
    parser.add_argument("--strict-readiness", action="store_true", default=True)
    parser.add_argument("--allow-open-port-fallback", action="store_true", help="Opt-in degraded frontend readiness fallback")
    parser.add_argument("--webscraper-mode", choices=["worker", "ui", "api", "combined", "none"], default="worker")
    parser.add_argument("--browser", choices=["none", "existing-profile", "persistent-profile"], default="none")
    parser.add_argument("--browser-profile-directory", default="Default")
    parser.add_argument("--browser-user-data-dir", default="var/web-app-launcher/browser-profile")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:3004/dashboard")
    parser.add_argument("--status-file", default="var/web-app-launcher/startup_summary.json")
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    py = sys.executable
    set_verbose(args.verbose)

    if args.inspect:
        print_inspection(root, browser_mode=args.browser)
        services = inspect_web_stack(root).get("services", {})
        ws_ui_exists = bool(services.get("webscraper_ui", {}).get("exists"))
        print(f"[inspect] webscraper_ui_exists={ws_ui_exists}")
        return 0

    run_manager = [py, str(root / "scripts" / "run_web_manager_app.py")]
    run_scraper = [py, str(root / "scripts" / "run_webscraper_app.py"), "--mode", args.webscraper_mode] if args.webscraper_mode != "none" else []
    run_ui = [py, str(root / "scripts" / "run_manager_ui_app.py")]

    common_flags = []
    if args.no_bootstrap:
        common_flags.append("--no-bootstrap")
    if args.no_port_cleanup:
        common_flags.append("--no-port-cleanup")
    if args.doctor:
        common_flags.append("--doctor")
    if args.dry_run:
        common_flags.append("--dry-run")
    if args.verbose:
        common_flags.append("--verbose")

    run_manager += common_flags
    run_ui += common_flags
    if run_scraper:
        run_scraper += common_flags

    run_ui.extend(["--readiness-timeout", str(args.readiness_timeout)])
    if args.allow_open_port_fallback:
        run_ui.append("--allow-open-port-fallback")

    try:
        if not args.no_bootstrap:
            run_checked([py, str(root / "scripts" / "bootstrap_venvs.py"), "--all"], cwd=root, section="bootstrap")
            ensure_manager_ui_dependencies(root)

        if not args.dry_run:
            stop_all_known_services(root, fallback_ports=[] if args.no_port_cleanup else [8787, 3004, 8788, 3005])

        run_checked(run_manager, cwd=root, section="stack")
        if run_scraper:
            run_checked(run_scraper, cwd=root, section="stack")
        run_checked(run_ui, cwd=root, section="stack")

        browser = launch_browser_mode(
            mode=args.browser,
            url=args.dashboard_url,
            profile_directory=args.browser_profile_directory,
            persistent_user_data_dir=root / args.browser_user_data_dir,
        )

        runtime_services = _read_runtime_services(root)
        summary = [
            _service_row("manager_backend", "backend", run_manager, runtime_services.get("webscraper_manager_api"), "http://127.0.0.1:8787/api/health"),
            _service_row("manager_frontend", "frontend", run_ui, runtime_services.get("manager_ui_frontend"), "http://127.0.0.1:3004/dashboard"),
        ]
        if run_scraper:
            summary.append(_service_row("webscraper_worker", args.webscraper_mode, run_scraper, runtime_services.get("webscraper_worker_service"), None))
            if args.webscraper_mode in {"api", "combined"}:
                summary.append(_service_row("webscraper_api", "api", run_scraper, runtime_services.get("webscraper_ticket_api"), "http://127.0.0.1:8788/api/health"))
            if args.webscraper_mode in {"ui", "combined"}:
                summary.append(_service_row("webscraper_ui", "ui", run_scraper, runtime_services.get("webscraper_ticket_ui"), "http://127.0.0.1:3005"))

        summary.append({
            "service_name": "login_browser_helper",
            "pid": None,
            "mode": browser.mode,
            "command": " ".join(browser.command),
            "log_file": None,
            "readiness_status": "ready" if browser.launched else "disabled",
            "readiness_reason": browser.reason,
            "url": browser.url,
            "started": browser.launched,
            "degraded": False,
            "browser_path": browser.browser_path,
            "user_data_dir": browser.user_data_dir,
            "profile_directory": browser.profile_directory,
        })

        degraded = [item for item in summary if item.get("degraded")]
        if args.strict_readiness and degraded:
            raise LauncherError(f"Startup completed in degraded state for: {', '.join(item['service_name'] for item in degraded)}")

        status_path = root / args.status_file
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps({"services": summary}, indent=2) + "\n", encoding="utf-8")

        print("[startup-summary]")
        for item in summary:
            print(f" - {item['service_name']}: started={item['started']} readiness={item['readiness_status']} reason={item['readiness_reason']}")
        print(f"[startup-summary] wrote {status_path}")
        print("[success] web tools stack started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
