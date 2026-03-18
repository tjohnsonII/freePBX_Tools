from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.dev_runtime import LauncherError, ensure_manager_ui_dependencies, maybe_open_browser, repo_root, run_checked


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the full web tools stack using per-app launchers.")
    parser.add_argument("--no-bootstrap", action="store_true", help="Skip dependency bootstrap steps")
    parser.add_argument("--doctor", action="store_true", help="Run doctor checks before launches")
    parser.add_argument("--no-port-cleanup", action="store_true", help="Fail instead of cleaning occupied ports")
    parser.add_argument("--open-browser", action="store_true", help="Open dashboard after UI readiness")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:3004/dashboard")
    args = parser.parse_args()

    root = repo_root(Path(__file__))
    py = sys.executable

    try:
        if not args.no_bootstrap:
            run_checked([py, str(root / "scripts" / "bootstrap_venvs.py"), "--all"], cwd=root, section="bootstrap")
            ensure_manager_ui_dependencies(root)

        if args.doctor:
            run_checked([py, str(root / "scripts" / "doctor_devs.py")], cwd=root, section="doctor")

        run_manager = [py, str(root / "scripts" / "run_web_manager_app.py")]
        run_scraper = [py, str(root / "scripts" / "run_webscraper_app.py")]
        run_ui = [py, str(root / "scripts" / "run_manager_ui_app.py")]

        if args.no_bootstrap:
            run_manager.append("--no-bootstrap")
            run_scraper.append("--no-bootstrap")
            run_ui.append("--no-bootstrap")
        if args.no_port_cleanup:
            run_manager.append("--no-port-cleanup")
            run_ui.append("--no-port-cleanup")
        if args.doctor:
            run_manager.append("--doctor")
            run_scraper.append("--doctor")
            run_ui.append("--doctor")

        run_checked(run_manager, cwd=root, section="stack")
        run_checked(run_scraper, cwd=root, section="stack")
        run_checked(run_ui, cwd=root, section="stack")

        maybe_open_browser(args.dashboard_url, open_browser=args.open_browser)
        print("[success] web tools stack started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
