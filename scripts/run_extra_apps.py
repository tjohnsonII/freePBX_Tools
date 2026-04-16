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
import subprocess
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

REMOTE_TRACEROUTE_HOST = "192.168.50.1"
REMOTE_TRACEROUTE_USER = "tjohnson"
REMOTE_TRACEROUTE_DIR  = "~"          # directory containing traceroute_server_update.py
REMOTE_TRACEROUTE_CTL  = "~/traceroute_server_ctl.sh"

SERVICES = {
    "homelab": {
        "label": "HomeLab Network Mapping (CCNA Lab Tracker)",
        "service_name": "homelab_network_mapping",
        "rel_dir": "HomeLab_NetworkMapping/ccna-lab-tracker",
        "port": 3011,
        "host": "127.0.0.1",
        "kind": "npm-next",
        "health_paths": ["/"],
        "success_markers": ["Ready in", "Local:"],
    },
    "remote_traceroute": {
        "label": "Remote Traceroute Server (CAGE)",
        "service_name": "remote_traceroute",
        "kind": "ssh-remote",
        "host": REMOTE_TRACEROUTE_HOST,
        "user": REMOTE_TRACEROUTE_USER,
        "remote_dir": REMOTE_TRACEROUTE_DIR,
        "remote_ctl": REMOTE_TRACEROUTE_CTL,
        "port": 8000,   # informational only
    },
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
    "deploy_backend": {
        "label": "FreePBX Deploy Backend (FastAPI)",
        "service_name": "freepbx_deploy_backend",
        "rel_dir": "freepbx-deploy-backend/src",
        "venv": "freepbx-deploy-backend/.venv",
        "app": "freepbx_deploy_backend.main:app",
        "port": 8002,
        "host": "127.0.0.1",
        "kind": "uvicorn",
        "health_paths": ["/api/health", "/docs"],
    },
}


# ── Per-service start helpers ─────────────────────────────────────────────────


def _start_npm(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:
    """Start a Next.js or Vite dev server via npm run dev."""
    npm = npm_executable()
    svc_dir = (root / svc["rel_dir"]).resolve()
    if not (svc_dir / "package.json").exists():
        return _unavailable(svc, f"No package.json found at {svc_dir}")

    # Auto-install node_modules if missing (avoids "next: not found" on fresh servers)
    if not (svc_dir / "node_modules").exists():
        print(f"[npm] node_modules missing for {svc['label']} — running npm install")
        subprocess.run([npm, "install"], cwd=str(svc_dir), check=False)

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


def _start_ssh_remote(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:  # noqa: ARG001
    """Ensure the remote traceroute server is running via SSH + traceroute_server_ctl.sh."""
    import shutil
    ssh = shutil.which("ssh")
    if not ssh:
        return _unavailable(svc, "ssh not found in PATH")

    host = svc["host"]
    user = svc["user"]
    remote_dir = svc["remote_dir"]
    remote_ctl = svc["remote_ctl"]
    target = f"{user}@{host}"

    # Base SSH options — legacy device support:
    #   HostKeyAlgorithms=+ssh-dss   : accept DSA host key (old routers only offer this)
    #   PubkeyAcceptedAlgorithms=+ssh-rsa : allow SHA-1 RSA user key signing
    #                                       (old sshd rejects rsa-sha2-256 the modern default)
    # BatchMode=yes fails fast instead of hanging on a password prompt.
    ssh_opts = [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "HostKeyAlgorithms=+ssh-dss",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
    ]
    ssh_check = [ssh, *ssh_opts, target, "echo ok"]
    ssh_start = [ssh, *ssh_opts, target, f"cd {remote_dir} && sh {remote_ctl} start"]
    ssh_status = [ssh, *ssh_opts, target, f"cd {remote_dir} && sh {remote_ctl} status"]

    if dry_run:
        return _dry_run_result(svc, ssh_start)

    import subprocess
    import time as _time

    # Verify key-based auth works
    result = subprocess.run(ssh_check, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return _unavailable(
            svc,
            f"SSH key auth to {target} failed (set up keys with: ssh-copy-id {target})\n"
            f"  stderr: {result.stderr.strip()}",
        )

    # Check if already running before attempting start.
    # Calling start when the server is already on the port causes a new process
    # to crash immediately (Address already in use), making status report STOPPED
    # even though the original instance is healthy.
    result = subprocess.run(ssh_status, capture_output=True, text=True, timeout=15)
    already_running = result.returncode == 0 and "RUNNING" in result.stdout.upper()

    if not already_running:
        # Kill any orphaned instances that the ctl script's PID file lost track of.
        # Without this, the new start crashes with "Address already in use" because
        # an old process still owns the port, making status immediately show STOPPED.
        ssh_killall = [ssh, *ssh_opts, target, "pkill -f traceroute_server_update.py; sleep 1; true"]
        subprocess.run(ssh_killall, capture_output=True, text=True, timeout=15)

        result = subprocess.run(ssh_start, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return _unavailable(svc, f"Remote start failed: {result.stderr.strip() or result.stdout.strip()}")
        print(f"[remote] {result.stdout.strip()}")
        # Brief pause for process to stabilize before checking status
        _time.sleep(2)
        result = subprocess.run(ssh_status, capture_output=True, text=True, timeout=15)
    else:
        print(f"[remote] already running, skipping start")

    running = result.returncode == 0 and "RUNNING" in result.stdout.upper()
    status_out = result.stdout.strip()

    if not running:
        return _unavailable(svc, f"Remote status check failed: {status_out}")

    url = f"http://{host}:{svc['port']}"
    print(f"[startup] remote_traceroute started=True url={url}")
    return {
        "service_name": svc["service_name"],
        "label": svc["label"],
        "started": True,
        "pid": None,
        "port": svc["port"],
        "url": url,
        "readiness_status": "ready",
        "readiness_reason": status_out,
        "degraded": False,
        "log_file": None,
    }


def _start_uvicorn(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:
    """Start a FastAPI app via uvicorn using its own venv."""
    import os
    _sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    venv_python = root / svc["venv"] / _sub[0] / _sub[1]
    if not venv_python.exists():
        return _unavailable(svc, f"venv not found: {venv_python}. Run bootstrap first.")

    host = svc["host"]
    port = svc["port"]
    name = svc["service_name"]
    app_dir = (root / svc["rel_dir"]).resolve()

    cmd = [
        str(venv_python), "-m", "uvicorn",
        svc["app"],
        "--host", host,
        "--port", str(port),
    ]

    stop_service(root, name)

    if dry_run:
        return _dry_run_result(svc, cmd)

    entry = start_detached(root=root, service_name=name, cmd=cmd, cwd=app_dir)
    save_service_state(root, entry)

    wait_for_process_stable(int(entry["pid"]), timeout_s=10, section="ready", min_alive_s=2.0)
    health_paths = svc.get("health_paths", ["/"])
    health_url = f"http://{host}:{port}{health_paths[0]}"
    ok = wait_for_http(health_url, timeout_s=readiness_timeout, section="ready")
    reason = f"HTTP probe passed at {health_url}" if ok else f"HTTP probe timed out at {health_url}"
    url = f"http://{host}:{port}"
    update_service_state(root, name, readiness_status="ready" if ok else "degraded",
                         readiness_reason=reason, mode="backend", degraded=not ok, url=url)
    return _ok_result(svc, entry, reason, url)


def _start_flask(root: Path, svc: dict, *, dry_run: bool, readiness_timeout: int) -> dict:
    """Start the Flask web manager (web_manager.py)."""
    import os
    venv_sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    venv_py = root / ".venv-web-manager" / venv_sub[0] / venv_sub[1]
    import shutil
    py = str(venv_py) if venv_py.exists() else (shutil.which("python3") or shutil.which("python") or sys.executable)
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

    env = {
        "FLASK_RUN_HOST": host,
        "FLASK_RUN_PORT": str(port),
        "FLASK_ENV": "development",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
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
        "degraded": False,
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
            elif svc["kind"] == "uvicorn":
                result = _start_uvicorn(root, svc, dry_run=dry_run, readiness_timeout=readiness_timeout)
            elif svc["kind"] == "ssh-remote":
                result = _start_ssh_remote(root, svc, dry_run=dry_run, readiness_timeout=readiness_timeout)
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
