from __future__ import annotations

import argparse
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    add_common_args,
    ensure_paths_exist,
    ensure_port_available,
    ensure_python_env,
    repo_root,
    run_doctor,
    save_service_state,
    set_verbose,
    stop_service,
    start_detached,
    print_inspection,
    update_service_state,
    wait_for_http,
    wait_for_process_stable,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the web manager backend (webscraper_manager FastAPI API).")
    add_common_args(parser)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--readiness-timeout", type=int, default=60)
    parser.add_argument(
        "--readiness-path",
        default="/api/health",
        help="HTTP path used for readiness checks (default: /api/health)",
    )
    parser.add_argument(
        "--allow-readiness-fail",
        action="store_true",
        help="Do not fail launcher if readiness check times out (dev-friendly mode)",
    )
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
                "webscraper_manager/api/server.py",
                "scripts/bootstrap_venv.py",
            ],
            section="preflight",
        )
        py = ensure_python_env(root, ".venv-web-manager", bootstrap=not args.no_bootstrap)

        if args.doctor:
            run_doctor(root)

        ensure_port_available(args.port, cleanup=not args.no_port_cleanup, section="ports")
        stop_service(root, "webscraper_manager_api")

        cmd = [
            str(py),
            "-m",
            "uvicorn",
            "webscraper_manager.api.server:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        if args.dry_run:
            print(f"[dry-run] would launch webscraper_manager_api: {' '.join(cmd)}")
            return 0

        entry = start_detached(
            root=root,
            service_name="webscraper_manager_api",
            cmd=cmd,
            cwd=root,
        )
        save_service_state(root, entry)
        wait_for_process_stable(entry["pid"], timeout_s=10, section="ready")

        readiness_path = args.readiness_path if args.readiness_path.startswith("/") else f"/{args.readiness_path}"
        readiness_url = f"http://{args.host}:{args.port}{readiness_path}"
        try:
            wait_for_http(
                readiness_url,
                timeout_s=args.readiness_timeout,
                section="ready",
            )
        except LauncherError:
            if args.allow_readiness_fail:
                update_service_state(root, "webscraper_manager_api", readiness_status="degraded", readiness_reason=f"readiness timed out for {readiness_url}", degraded=True)
                print(
                    "[warn] readiness check timed out; continuing because --allow-readiness-fail is enabled "
                    f"({readiness_url}, timeout={args.readiness_timeout}s)"
                )
            else:
                raise
        else:
            update_service_state(root, "webscraper_manager_api", readiness_status="ready", readiness_reason=f"HTTP probe passed at {readiness_url}", degraded=False, url=readiness_url, mode="backend")
        print("[success] web manager backend started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
