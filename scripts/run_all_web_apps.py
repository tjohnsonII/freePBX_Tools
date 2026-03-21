from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from lib.dev_runtime import (
    BrowserLaunchDetails,
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

DEFAULT_STATUS_FILE = "var/web-app-launcher/startup_summary.json"
DEPRECATED_ARG_HINTS = {
    "--open-browser": "--open-browser is deprecated; use --browser existing-profile",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Canonical launcher for manager backend, manager UI, and optional webscraper roles."
    )
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--no-port-cleanup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="Print discovered services and exit")
    parser.add_argument("--readiness-timeout", type=int, default=180)
    parser.add_argument("--strict-readiness", action="store_true", help="Exit nonzero when any service reports degraded or failed readiness")
    parser.add_argument(
        "--allow-open-port-fallback",
        action="store_true",
        help="Opt-in degraded frontend readiness fallback",
    )
    parser.add_argument("--webscraper-mode", choices=["worker", "ui", "api", "combined", "none"], default="combined")
    parser.add_argument("--browser", choices=["none", "existing-profile", "persistent-profile"], default="none")
    parser.add_argument("--browser-profile-directory", default="Default")
    parser.add_argument("--browser-user-data-dir", default="var/web-app-launcher/browser-profile")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:3004/dashboard")
    parser.add_argument("--status-file", default=DEFAULT_STATUS_FILE)
    parser.add_argument(
        "--extras", action="store_true",
        help="Also start extra services: Traceroute Visualizer (3006), Polycom App (3002), FreePBX Web Manager (5000)",
    )
    parser.add_argument(
        "--only-extras", nargs="+", choices=["traceroute", "polycom", "web_manager"],
        metavar="SERVICE",
        help="With --extras, limit which extra services to start",
    )
    return parser.parse_args(argv)


def maybe_handle_deprecated_args(argv: list[str]) -> None:
    hits = [token for token in argv if token in DEPRECATED_ARG_HINTS]
    if hits:
        messages = [DEPRECATED_ARG_HINTS[token] for token in hits]
        raise LauncherError("; ".join(messages))


def validate_args(args: argparse.Namespace) -> None:
    if args.readiness_timeout <= 0:
        raise LauncherError("--readiness-timeout must be greater than zero.")
    if args.browser == "persistent-profile" and not str(args.browser_user_data_dir).strip():
        raise LauncherError("--browser-user-data-dir is required when --browser persistent-profile is used.")


def bootstrap(root: Path, py: str, *, skip: bool) -> None:
    if skip:
        return
    run_checked([py, str(root / "scripts" / "bootstrap_venvs.py"), "--all"], cwd=root, section="bootstrap")
    ensure_manager_ui_dependencies(root)


def run_doctor_phase(root: Path, py: str, *, enabled: bool) -> None:
    if not enabled:
        return
    run_checked([py, str(root / "scripts" / "doctor_devs.py")], cwd=root, section="doctor")


def cleanup_ports(root: Path, *, enabled: bool, dry_run: bool) -> None:
    fallback_ports = [8787, 3004, 8788, 3005]
    if dry_run:
        print(f"[dry-run] would stop known services and cleanup ports={fallback_ports if enabled else []}")
        return
    stop_all_known_services(root, fallback_ports=fallback_ports if enabled else [])


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


def _build_commands(root: Path, py: str, args: argparse.Namespace) -> dict[str, list[str]]:
    common_flags: list[str] = []
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

    manager_cmd = [py, str(root / "scripts" / "run_web_manager_app.py"), *common_flags, "--readiness-timeout", str(args.readiness_timeout)]
    ui_cmd = [
        py,
        str(root / "scripts" / "run_manager_ui_app.py"),
        *common_flags,
        "--readiness-timeout",
        str(args.readiness_timeout),
    ]
    if args.allow_open_port_fallback:
        ui_cmd.append("--allow-open-port-fallback")

    commands: dict[str, list[str]] = {
        "manager_backend": manager_cmd,
        "manager_frontend": ui_cmd,
    }
    if args.webscraper_mode != "none":
        commands["webscraper"] = [
            py,
            str(root / "scripts" / "run_webscraper_app.py"),
            "--mode",
            args.webscraper_mode,
            *common_flags,
            "--readiness-timeout",
            str(args.readiness_timeout),
        ]
    return commands


def start_services(root: Path, commands: dict[str, list[str]]) -> None:
    for service, cmd in commands.items():
        run_checked(cmd, cwd=root, section=f"launch:{service}")


def _service_row(
    *,
    name: str,
    mode: str,
    command: list[str],
    runtime_state: dict[str, Any] | None,
    expected_port: int | None,
    probe_url: str | None,
) -> dict[str, Any]:
    state = runtime_state or {}
    pid = state.get("pid")
    readiness_status = state.get("readiness_status") or ("ready" if pid else "not-started")
    readiness_reason = state.get("readiness_reason") or ("process started" if pid else "service did not start")
    started = bool(pid)
    degraded = bool(state.get("degraded") or state.get("readiness_warning") or readiness_status in {"degraded", "failed", "unavailable"})
    return {
        "service_name": name,
        "mode": mode,
        "started": started,
        "pid": pid,
        "command": state.get("command") or " ".join(command),
        "log_file": state.get("log"),
        "target_port": expected_port,
        "readiness_probe_url": probe_url,
        "readiness_status": readiness_status,
        "readiness_reason": readiness_reason,
        "readiness_elapsed_seconds": state.get("readiness_elapsed_seconds"),
        "degraded": degraded,
        "url": state.get("url") or probe_url,
    }


def wait_for_readiness(root: Path, args: argparse.Namespace, commands: dict[str, list[str]]) -> list[dict[str, Any]]:
    runtime = _read_runtime_services(root)
    summary: list[dict[str, Any]] = [
        _service_row(
            name="manager_backend",
            mode="backend",
            command=commands["manager_backend"],
            runtime_state=runtime.get("webscraper_manager_api"),
            expected_port=8787,
            probe_url="http://127.0.0.1:8787/api/health",
        ),
        _service_row(
            name="manager_frontend",
            mode="frontend",
            command=commands["manager_frontend"],
            runtime_state=runtime.get("manager_ui_frontend"),
            expected_port=3004,
            probe_url=args.dashboard_url,
        ),
    ]

    if "webscraper" in commands:
        summary.append(
            _service_row(
                name="webscraper_worker",
                mode=args.webscraper_mode,
                command=commands["webscraper"],
                runtime_state=runtime.get("webscraper_worker_service"),
                expected_port=None,
                probe_url=None,
            )
        )
        if args.webscraper_mode in {"api", "combined"}:
            summary.append(
                _service_row(
                    name="webscraper_api",
                    mode="api",
                    command=commands["webscraper"],
                    runtime_state=runtime.get("webscraper_ticket_api"),
                    expected_port=8788,
                    probe_url="http://127.0.0.1:8788/api/health",
                )
            )
        if args.webscraper_mode in {"ui", "combined"}:
            summary.append(
                _service_row(
                    name="webscraper_ui",
                    mode="ui",
                    command=commands["webscraper"],
                    runtime_state=runtime.get("webscraper_ticket_ui"),
                    expected_port=3005,
                    probe_url="http://127.0.0.1:3005",
                )
            )
    return summary


def maybe_launch_browser(root: Path, args: argparse.Namespace) -> BrowserLaunchDetails:
    return launch_browser_mode(
        mode=args.browser,
        url=args.dashboard_url,
        profile_directory=args.browser_profile_directory,
        persistent_user_data_dir=root / args.browser_user_data_dir,
    )


def write_status_file(
    *,
    root: Path,
    args: argparse.Namespace,
    services: list[dict[str, Any]],
    browser: BrowserLaunchDetails,
    failures: list[str],
    warnings: list[str],
) -> Path:
    status_payload = {
        "timestamp": int(time.time()),
        "args": vars(args),
        "services_attempted": [service["service_name"] for service in services],
        "services_started": [service["service_name"] for service in services if service.get("started")],
        "services": services,
        "browser": {
            "mode": browser.mode,
            "launched": browser.launched,
            "reason": browser.reason,
            "url": browser.url,
            "command": browser.command,
            "browser_path": browser.browser_path,
            "user_data_dir": browser.user_data_dir,
            "profile_directory": browser.profile_directory,
        },
        "warnings": warnings,
        "failures": failures,
    }
    status_path = root / args.status_file
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status_payload, indent=2) + "\n", encoding="utf-8")
    return status_path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        maybe_handle_deprecated_args(argv)
        args = parse_args(argv)
        validate_args(args)

        root = repo_root(Path(__file__))
        py = sys.executable
        set_verbose(args.verbose)

        if args.inspect:
            print_inspection(root, browser_mode=args.browser)
            services = inspect_web_stack(root).get("services", {})
            ws_ui_exists = bool(services.get("webscraper_ui", {}).get("exists"))
            print(f"[inspect] webscraper_ui_exists={ws_ui_exists}")
            return 0

        print("[phase] bootstrap")
        bootstrap(root, py, skip=args.no_bootstrap)

        print("[phase] doctor")
        run_doctor_phase(root, py, enabled=args.doctor)

        print("[phase] cleanup")
        cleanup_ports(root, enabled=not args.no_port_cleanup, dry_run=args.dry_run)

        print("[phase] launch")
        commands = _build_commands(root, py, args)
        start_services(root, commands)

        print("[phase] readiness")
        service_summary = wait_for_readiness(root, args, commands)

        if args.extras:
            print("[phase] extras")
            from run_extra_apps import start_extras  # noqa: PLC0415
            extra_results = start_extras(
                root,
                only=args.only_extras or None,
                dry_run=args.dry_run,
                readiness_timeout=args.readiness_timeout,
            )
            service_summary.extend(extra_results)

        warnings = [
            f"{item['service_name']}: {item['readiness_reason']}"
            for item in service_summary
            if item.get("degraded")
        ]

        print("[phase] browser")
        browser = maybe_launch_browser(root, args)

        failures: list[str] = []
        if args.strict_readiness and warnings:
            failures.append("strict readiness failed because one or more services are degraded")

        status_path = write_status_file(
            root=root,
            args=args,
            services=service_summary,
            browser=browser,
            failures=failures,
            warnings=warnings,
        )

        print("[startup-summary]")
        for item in service_summary:
            print(
                " - "
                f"{item['service_name']}: started={item['started']} pid={item['pid']} "
                f"port={item['target_port']} readiness={item['readiness_status']} "
                f"reason={item['readiness_reason']}"
            )
        print(f" - browser: mode={browser.mode} launched={browser.launched} reason={browser.reason}")
        print(f"[startup-summary] status_file={status_path}")

        if failures:
            raise LauncherError("; ".join(failures + warnings))

        print("[success] web tools stack started")
        return 0
    except LauncherError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
