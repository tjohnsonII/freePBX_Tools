"""Launcher for extra dev services not covered by run_all_web_apps.py.

Services managed here:
  traceroute_ui      - Traceroute Visualizer (Next.js, port 3006)
  polycom_ui         - Polycom/Yealink/Mikrotik Config App (Vite, port 3002)
  freepbx_web_manager- FreePBX Tools Web Manager (Flask, port 5000)

Usage:
  python scripts/run_extra_apps.py              # start all three
  python scripts/run_extra_apps.py --only traceroute polycom
  python scripts/run_extra_apps.py --dry-run
  python scripts/run_extra_apps.py --readiness-timeout 120
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.dev_runtime import (
    LauncherError,
    npm_executable,
    repo_root,
    save_service_state,
    set_verbose,
    start_detached,
    stop_service,
    update_service_state,
    wait_for_dev_server_ready,
    wait_for_http,
    wait_for_process_stable,
)

# ── Service definitions ───────────────────────────────────────────────────────

SERVICES = {
    "traceroute": {
        "label": "Traceroute Visualizer",
        "service_name": "traceroute_ui",
        "rel_dir": "traceroute-visualizer-main/traceroute-visualizer-main",
        "port": 3006,
        "host": "127.0.0.1",
        "kind": "npm-next",
        "health_paths": ["/"],
        "success_markers": ["Ready in", "Local:"],
    },
    "polycom": {
        "label": "Polycom/Yealink/Mikrotik Config App",
        "service_name": "polycom_ui",
        "rel_dir": "PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main",
        "port": 3002,
        "host": "127.0.0.1",
        "kind": "npm-vite",
        "health_paths": ["/"],
        "success_markers": ["Local:", "ready in", "VITE"],
    },
    "web_manager": {
        "label": "FreePBX Tools Web Manager (Flask)",
        "service_name": "freepbx_web_manager",
        "rel_dir": ".",
        "port": 5000,
        "host": "127.0.0.1",
        "kind": "flask",
        "health_paths": ["/"],
        "success_markers": ["Running on"],
    },
}


# ── Per-service start helpers ─────────────────────────────────────────────────


def _start_npm(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:
    """Start a Next.js or Vite dev server via npm run dev."""
    npm = npm_executable()
    svc_dir = (root / svc["rel_dir"]).resolve()
    if not (svc_dir / "package.json").exists():
        return _unavailable(svc, f"No package.json found at {svc_dir}")

    host = svc["host"]
    port = svc["port"]
    name = svc["service_name"]

    # Vite uses --port directly; Next.js uses -- --port
    if svc["kind"] == "npm-vite":
        cmd = [npm, "run", "dev", "--", "--port", str(port), "--host", host]
    else:
        cmd = [npm, "run", "dev", "--", "--port", str(port), "--hostname", host]

    stop_service(root, name)

    if dry_run:
        return _dry_run_result(svc, cmd)

    entry = start_detached(root=root, service_name=name, cmd=cmd, cwd=svc_dir)
    save_service_state(root, entry)

    log_path = Path(entry["log"])
    reason = wait_for_dev_server_ready(
        pid=int(entry["pid"]),
        host=host,
        port=port,
        timeout_s=readiness_timeout,
        http_paths=svc["health_paths"],
        log_path=log_path,
        section="ready",
        allow_open_port_fallback=False,
        success_markers=svc["success_markers"],
    )
    url = f"http://{host}:{port}"
    update_service_state(root, name, readiness_status="ready", readiness_reason=reason,
                         mode="ui", degraded=False, url=url)
    return _ok_result(svc, entry, reason, url)


def _start_flask(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:
    """Start the Flask web manager (web_manager.py)."""
    import shutil
    py = shutil.which("python") or sys.executable
    svc_dir = root
    web_manager = root / "web_manager.py"
    if not web_manager.exists():
        return _unavailable(svc, f"web_manager.py not found at {web_manager}")

    host = svc["host"]
    port = svc["port"]
    name = svc["service_name"]
    cmd = [py, str(web_manager)]

    stop_service(root, name)

    if dry_run:
        return _dry_run_result(svc, cmd)

    env = {"FLASK_RUN_HOST": host, "FLASK_RUN_PORT": str(port), "FLASK_ENV": "development"}
    entry = start_detached(root=root, service_name=name, cmd=cmd, cwd=svc_dir,
                           env_overrides=env)
    save_service_state(root, entry)
    wait_for_process_stable(int(entry["pid"]), timeout_s=10, section="ready", min_alive_s=3.0)
    health_url = f"http://{host}:{port}/"
    wait_for_http(health_url, timeout_s=readiness_timeout, section="ready")
    url = f"http://{host}:{port}"
    update_service_state(root, name, readiness_status="ready",
                         readiness_reason=f"HTTP probe passed at {health_url}",
                         mode="flask", degraded=False, url=url)
    return _ok_result(svc, entry, f"HTTP probe passed at {health_url}", url)


# ── Result shape helpers ──────────────────────────────────────────────────────


def _ok_result(svc: dict, entry: dict, reason: str, url: str) -> dict:
    return {
        "service_name": svc["service_name"],
        "label": svc["label"],
        "started": True,
        "pid": entry["pid"],
        "port": svc["port"],
        "url": url,
        "readiness_status": "ready",
        "readiness_reason": reason,
        "degraded": False,
        "log_file": entry.get("log"),
    }


def _unavailable(svc: dict, reason: str) -> dict:
    print(f"[warn] {svc['label']}: {reason}")
    return {
        "service_name": svc["service_name"],
        "label": svc["label"],
        "started": False,
        "pid": None,
        "port": svc["port"],
        "url": None,
        "readiness_status": "unavailable",
        "readiness_reason": reason,
        "degraded": True,
        "log_file": None,
    }


def _dry_run_result(svc: dict, cmd: list) -> dict:
    print(f"[dry-run] would start {svc['label']}: {' '.join(cmd)}")
    return {
        "service_name": svc["service_name"],
        "label": svc["label"],
        "started": False,
        "pid": None,
        "port": svc["port"],
        "url": None,
        "readiness_status": "dry-run",
        "readiness_reason": "dry-run mode",
        "degraded": False,
        "log_file": None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def start_extras(
    root: Path,
    *,
    only: list[str] | None = None,
    dry_run: bool = False,
    readiness_timeout: int = 120,
) -> list[dict]:
    """Start extra services. Returns list of result dicts."""
    keys = only if only else list(SERVICES.keys())
    results: list[dict] = []

    for key in keys:
        svc = SERVICES.get(key)
        if svc is None:
            print(f"[warn] Unknown service key '{key}' — valid: {list(SERVICES.keys())}")
            continue
        print(f"[launch] {svc['label']} (port {svc['port']})")
        try:
            if svc["kind"] in ("npm-next", "npm-vite"):
                result = _start_npm(root, svc, dry_run=dry_run, readiness_timeout=readiness_timeout)
            elif svc["kind"] == "flask":
                result = _start_flask(root, svc, dry_run=dry_run, readiness_timeout=readiness_timeout)
            else:
                result = _unavailable(svc, f"Unknown kind '{svc['kind']}'")
        except Exception as exc:
            print(f"[error] {svc['label']} failed to start: {exc}")
            result = _unavailable(svc, str(exc))
        results.append(result)
        print(f"[startup] {result['service_name']} started={result['started']} "
              f"readiness={result['readiness_status']} url={result.get('url')}")

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start extra dev services (traceroute, polycom, web_manager)."
    )
    parser.add_argument(
        "--only", nargs="+", choices=list(SERVICES.keys()),
        metavar="SERVICE",
        help=f"Start only these services. Choices: {list(SERVICES.keys())}",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--readiness-timeout", type=int, default=120)
    args = parser.parse_args(argv)

    root = repo_root(Path(__file__))
    set_verbose(args.verbose)

    results = start_extras(
        root,
        only=args.only,
        dry_run=args.dry_run,
        readiness_timeout=args.readiness_timeout,
    )

    degraded = [r for r in results if r.get("degraded")]
    if degraded:
        for r in degraded:
            print(f"[warn] {r['service_name']}: {r['readiness_reason']}")
        return 1
    print("[success] extra apps started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
