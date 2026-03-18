from __future__ import annotations

import argparse
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
    wait_for_http,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch the webscraper backend service via webscraper_manager CLI."
    )
    add_common_args(parser)
    parser.add_argument("--readiness-url", default="http://127.0.0.1:8787/api/tickets/status")
    parser.add_argument("--readiness-timeout", type=int, default=60)
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
        py = ensure_python_env(root, ".venv-webscraper", bootstrap=not args.no_bootstrap)

        if args.doctor:
            run_doctor(root)

        cmd = [
            str(py),
            "-m",
            "webscraper_manager",
            "start",
            "--json",
            "--no-kill-ports",
        ]

        entry = start_detached(
            root=root,
            service_name="webscraper_backend_service",
            cmd=cmd,
            cwd=root,
        )
        save_service_state(root, entry)

        wait_for_http(args.readiness_url, timeout_s=args.readiness_timeout, ok_status_max=499, section="ready")
        print("[success] webscraper backend service started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
