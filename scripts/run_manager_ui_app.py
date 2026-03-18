from __future__ import annotations

import argparse
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    add_common_args,
    ensure_manager_ui_dependencies,
    ensure_paths_exist,
    ensure_port_available,
    npm_executable,
    repo_root,
    run_doctor,
    save_service_state,
    start_detached,
    wait_for_http,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch manager-ui frontend (Next.js dev server).")
    add_common_args(parser)
    parser.add_argument("--port", type=int, default=3004)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--readiness-timeout", type=int, default=90)
    parser.add_argument("--skip-npm-install", action="store_true", help="Skip manager-ui dependency self-heal")
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    try:
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

        npm = npm_executable()
        cmd = [npm, "--prefix", "manager-ui", "run", "dev"]

        entry = start_detached(
            root=root,
            service_name="manager_ui_frontend",
            cmd=cmd,
            cwd=root,
        )
        save_service_state(root, entry)

        wait_for_http(
            f"http://{args.host}:{args.port}/dashboard",
            timeout_s=args.readiness_timeout,
            ok_status_max=499,
            section="ready",
        )
        print("[success] manager-ui frontend started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
