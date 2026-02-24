from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Sequence


def _run_api(host: str, port: int, db_path: str, reload: bool) -> int:
    cmd = [
        sys.executable,
        "-m",
        "webscraper.ticket_api.app",
        "--host",
        host,
        "--port",
        str(port),
        "--db",
        db_path,
    ]
    if reload:
        cmd.append("--reload")
    return subprocess.call(cmd)


def _run_ticket_stack(host: str, api_port: int, ui_port: int, db_path: str, reload: bool) -> int:
    api_cmd = [
        sys.executable,
        "-m",
        "webscraper.ticket_api.app",
        "--host",
        host,
        "--port",
        str(api_port),
        "--db",
        db_path,
    ]
    if reload:
        api_cmd.append("--reload")

    ui_env = os.environ.copy()
    ui_env.setdefault("TICKET_API_PROXY_TARGET", f"http://127.0.0.1:{api_port}")
    ui_env.setdefault("PORT", str(ui_port))
    ui_cmd = ["npm", "run", "dev"]

    api = subprocess.Popen(api_cmd)
    ui = subprocess.Popen(ui_cmd, cwd=os.path.join("webscraper", "ticket-ui"), env=ui_env)
    try:
        ui_rc = ui.wait()
        return ui_rc
    finally:
        for proc in (api, ui):
            if proc.poll() is None:
                proc.terminate()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Webscraper dev launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8787)
    parser.add_argument("--ui-port", type=int, default=3000)
    parser.add_argument("--db", default=os.path.join("webscraper", "output", "tickets.sqlite"))
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--ticket-stack",
        action="store_true",
        help="Run ticket API + Next.js ticket-ui together",
    )
    args = parser.parse_args(argv)

    if args.ticket_stack:
        return _run_ticket_stack(args.host, args.api_port, args.ui_port, args.db, args.reload)
    return _run_api(args.host, args.api_port, args.db, args.reload)


if __name__ == "__main__":
    raise SystemExit(main())
