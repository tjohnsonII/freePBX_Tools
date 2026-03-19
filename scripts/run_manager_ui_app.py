from __future__ import annotations

import argparse
import time
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    add_common_args,
    ensure_manager_ui_dependencies,
    ensure_paths_exist,
    ensure_port_available,
    maybe_open_browser,
    npm_executable,
    repo_root,
    run_doctor,
    save_service_state,
    set_verbose,
    stop_service,
    start_detached,
    update_service_state,
    wait_for_dev_server_ready,
    print_inspection,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch manager-ui frontend (Next.js dev server).")
    add_common_args(parser)
    parser.add_argument("--port", type=int, default=3004)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--readiness-timeout", type=int, default=180)
    parser.add_argument(
        "--readiness-path",
        action="append",
        dest="readiness_paths",
        default=None,
        help="HTTP readiness path. Repeatable (default: /, /dashboard, /api/health).",
    )
    parser.add_argument(
        "--allow-open-port-fallback",
        action="store_true",
        help="Allow open-port fallback readiness mode (degraded). Disabled by default.",
    )
    parser.add_argument("--open-port-fallback-seconds", type=int, default=12, help="Open-port fallback stability window.")
    parser.add_argument(
        "--readiness-marker",
        action="append",
        dest="readiness_markers",
        default=None,
        help="Log marker that indicates frontend readiness. Repeatable.",
    )
    parser.add_argument("--open-browser", action="store_true", help="Open dashboard URL after readiness passes")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:3004/dashboard")
    parser.add_argument("--skip-npm-install", action="store_true", help="Skip manager-ui dependency self-heal")
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    try:
        set_verbose(args.verbose)
        if args.inspect:
            print_inspection(root, browser_mode="none")
            return 0
        ensure_paths_exist(
            root,
            [
                "manager-ui/package.json",
                "manager-ui/next.config.mjs",
            ],
            section="preflight",
        )

        if not args.skip_npm_install:
            ensure_manager_ui_dependencies(root)

        if args.doctor:
            run_doctor(root)

        ensure_port_available(args.port, cleanup=not args.no_port_cleanup, section="ports")
        stop_service(root, "manager_ui_frontend")

        npm = npm_executable()
        cmd = [npm, "--prefix", "manager-ui", "run", "dev"]
        if args.dry_run:
            print(f"[dry-run] would launch manager_ui_frontend: {' '.join(cmd)}")
            return 0

        entry = start_detached(
            root=root,
            service_name="manager_ui_frontend",
            cmd=cmd,
            cwd=root,
        )
        save_service_state(root, entry)
        readiness_paths = args.readiness_paths or ["/", "/dashboard", "/api/health"]
        readiness_markers = args.readiness_markers or ["Ready in", "Local: http://localhost:3004"]
        reason = wait_for_dev_server_ready(
            pid=int(entry["pid"]),
            host=args.host,
            port=args.port,
            timeout_s=args.readiness_timeout,
            http_paths=readiness_paths,
            log_path=Path(entry["log"]),
            section="ready",
            open_port_fallback_s=max(1, args.open_port_fallback_seconds),
            allow_open_port_fallback=args.allow_open_port_fallback,
            success_markers=readiness_markers,
        )
        warning = "open port fallback" in reason.lower()
        update_service_state(
            root,
            "manager_ui_frontend",
            readiness_reason=reason,
            readiness_warning=warning,
            readiness_checked_at=int(time.time()),
        )
        if warning:
            print(f"[warn] {reason}")
        else:
            print(f"[ready] {reason}")
        print("[changelog] manager-ui readiness now uses markers, port checks, multi-path HTTP probes, and fallback mode.")
        maybe_open_browser(args.dashboard_url, open_browser=args.open_browser)
        print("[success] manager-ui frontend started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
