from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_venv.py"

FRONTEND_APPS: list[tuple[str, Path]] = [
    ("manager-ui", REPO_ROOT / "manager-ui"),
    ("freepbx-deploy-ui", REPO_ROOT / "freepbx-deploy-ui"),
    (
        "polycom-config-ui",
        REPO_ROOT / "PolycomYealinkMikrotikSwitchConfig-main" / "PolycomYealinkMikrotikSwitchConfig-main",
    ),
    ("traceroute-visualizer-ui", REPO_ROOT / "traceroute-visualizer-main" / "traceroute-visualizer-main"),
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def _python_env_check(fix: bool) -> CheckResult:
    if not BOOTSTRAP_SCRIPT.is_file():
        return CheckResult("python_envs", False, f"missing bootstrap script: {BOOTSTRAP_SCRIPT}")

    cmd = [sys.executable, str(BOOTSTRAP_SCRIPT), "--all", "--json"]
    if not fix:
        cmd.append("--verify-only")

    proc = _run(cmd, cwd=REPO_ROOT)
    raw = (proc.stdout or "").strip()
    if not raw:
        err = (proc.stderr or "bootstrap command returned no output").strip()
        return CheckResult("python_envs", False, err)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return CheckResult("python_envs", False, f"invalid JSON from bootstrap_venv.py: {raw[:240]}")

    summary = payload.get("summary") if isinstance(payload, dict) else None
    if not isinstance(summary, dict):
        return CheckResult("python_envs", False, "bootstrap payload missing summary")

    total = int(summary.get("total", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    ok = bool(payload.get("ok"))
    details = f"{passed}/{total} healthy"
    if failed:
        details += f" ({failed} failed)"
    if fix:
        details = f"bootstrap: {details}"
    else:
        details = f"doctor: {details}"
    return CheckResult("python_envs", ok, details)


def _check_frontend(name: str, app_dir: Path, fix_node: bool) -> CheckResult:
    package_json = app_dir / "package.json"
    node_modules = app_dir / "node_modules"

    if not package_json.is_file():
        return CheckResult(f"frontend:{name}", False, f"missing package.json ({package_json})")

    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    node_cmd = shutil.which("node")
    if not node_cmd:
        return CheckResult(f"frontend:{name}", False, "node not found in PATH")
    if not npm_cmd:
        return CheckResult(f"frontend:{name}", False, "npm not found in PATH")

    if node_modules.is_dir():
        return CheckResult(f"frontend:{name}", True, "node_modules present")

    if not fix_node:
        return CheckResult(f"frontend:{name}", False, f"node_modules missing ({node_modules})")

    proc = _run([npm_cmd, "install"], cwd=app_dir)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "npm install failed").strip().splitlines()[-1]
        return CheckResult(f"frontend:{name}", False, f"npm install failed: {err}")

    if node_modules.is_dir():
        return CheckResult(f"frontend:{name}", True, "node_modules installed")
    return CheckResult(f"frontend:{name}", False, "npm install finished but node_modules still missing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor/bootstrap helper for repo dev environments.")
    parser.add_argument("mode", choices=["doctor", "bootstrap"], help="doctor=read-only, bootstrap=fix mode")
    parser.add_argument("--skip-node", action="store_true", help="skip frontend dependency checks")
    parser.add_argument(
        "--fix-node",
        action="store_true",
        help="in bootstrap mode, install missing node_modules for known frontend apps",
    )
    args = parser.parse_args(argv)

    fix = args.mode == "bootstrap"
    fix_node = fix and bool(args.fix_node) and not bool(args.skip_node)

    results: list[CheckResult] = [_python_env_check(fix=fix)]
    if not args.skip_node:
        for name, app_dir in FRONTEND_APPS:
            results.append(_check_frontend(name, app_dir, fix_node=fix_node))

    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.details}")

    return 0 if all(item.ok for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
