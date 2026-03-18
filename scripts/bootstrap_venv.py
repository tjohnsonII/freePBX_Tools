from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT_DIR = SCRIPT_DIR.parent
if str(REPO_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_DIR))

from scripts.venv_registry import REPO_ROOT, find_env_id_by_venv_path, get_env_config, iter_managed_envs, resolve_repo_path


@dataclass
class BootstrapResult:
    env_id: str | None
    app: str
    venv: str
    requirement_source: str | None
    ok: bool
    created: bool = False
    installed: bool = False
    missing_modules: list[str] = field(default_factory=list)
    message: str = ""


def _log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"[bootstrap] {message}")


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _missing_imports(python_exe: Path, modules: list[str], repo_root: Path) -> list[str]:
    if not modules:
        return []
    probe = (
        "import importlib.util, json, sys; "
        "mods=sys.argv[1:]; "
        "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
        "print(json.dumps(missing))"
    )
    completed = _run([str(python_exe), "-c", probe, *modules], cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "import probe failed").strip())
    try:
        loaded = json.loads((completed.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid import probe output: {exc}") from exc
    return [str(item) for item in loaded]


def _bootstrap_one(
    *,
    env_id: str | None,
    app: str,
    venv_rel: str,
    requirements: str | None,
    imports: list[str],
    fallback_packages: list[str],
    verify_only: bool,
    quiet: bool,
    python_launcher: str,
) -> BootstrapResult:
    repo_root = REPO_ROOT
    venv_dir = resolve_repo_path(venv_rel)
    assert venv_dir is not None

    requirement_path = resolve_repo_path(requirements)
    python_exe = _venv_python(venv_dir)

    result = BootstrapResult(
        env_id=env_id,
        app=app,
        venv=str(venv_rel),
        requirement_source=str(requirements) if requirements else None,
        ok=False,
    )

    created = False
    if python_exe.is_file():
        _log(f"{venv_rel}: venv exists", quiet=quiet)
    else:
        if verify_only:
            result.message = "venv missing"
            return result
        _log(f"{venv_rel}: venv missing -> creating", quiet=quiet)
        created_proc = _run([python_launcher, "-m", "venv", str(venv_dir)], cwd=repo_root)
        if created_proc.returncode != 0:
            result.message = (created_proc.stderr or created_proc.stdout or "venv creation failed").strip()
            return result
        created = True

    if not python_exe.is_file():
        result.message = f"python executable not found: {python_exe}"
        return result

    try:
        missing_modules = _missing_imports(python_exe, imports, repo_root)
    except Exception as exc:
        result.message = f"module probe failed: {exc}"
        return result

    result.missing_modules = missing_modules

    needs_install = created or bool(missing_modules)
    if needs_install and verify_only:
        result.message = (
            "venv missing" if created else f"missing modules: {', '.join(missing_modules)}"
        )
        return result

    installed = False
    if needs_install:
        if requirement_path and requirement_path.is_file():
            if missing_modules:
                _log(f"{venv_rel}: missing {', '.join(missing_modules)} -> installing from {requirements}", quiet=quiet)
            else:
                _log(f"{venv_rel}: installing dependencies from {requirements}", quiet=quiet)
            install_cmd = [str(python_exe), "-m", "pip", "install", "-r", str(requirement_path)]
        elif fallback_packages:
            _log(f"{venv_rel}: installing fallback packages: {' '.join(fallback_packages)}", quiet=quiet)
            install_cmd = [str(python_exe), "-m", "pip", "install", *fallback_packages]
        else:
            result.message = "no install source provided (requirements missing and no fallback packages)"
            return result

        install_proc = _run(install_cmd, cwd=repo_root)
        if install_proc.returncode != 0:
            result.message = (install_proc.stderr or install_proc.stdout or "dependency install failed").strip()
            return result
        installed = True

        try:
            missing_after = _missing_imports(python_exe, imports, repo_root)
        except Exception as exc:
            result.message = f"post-install module probe failed: {exc}"
            return result
        if missing_after:
            result.missing_modules = missing_after
            result.message = f"modules still missing after install: {', '.join(missing_after)}"
            return result

    result.created = created
    result.installed = installed
    result.ok = True
    result.message = "dependencies OK"
    _log(f"{venv_rel}: dependencies OK", quiet=quiet)
    return result


def _result_to_dict(result: BootstrapResult) -> dict[str, object]:
    return {
        "env_id": result.env_id,
        "app": result.app,
        "venv": result.venv,
        "requirement_source": result.requirement_source,
        "ok": result.ok,
        "created": result.created,
        "installed": result.installed,
        "missing_modules": result.missing_modules,
        "message": result.message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and verify managed Python virtual environments.")
    parser.add_argument("--venv", help="Venv path relative to repo root (e.g. .venv-webscraper).")
    parser.add_argument("--env-id", help="Managed environment id from scripts/venv_registry.py.")
    parser.add_argument("--all", action="store_true", help="Bootstrap all managed environments from the registry.")
    parser.add_argument("--requirements", help="Optional requirements file path relative to repo root.")
    parser.add_argument("--check-import", action="append", default=[], help="Import/module name to verify (repeatable).")
    parser.add_argument("--install-package", action="append", default=[], help="Fallback package to install if checks fail.")
    parser.add_argument("--python-launcher", default=sys.executable, help="Python executable used to create missing venvs.")
    parser.add_argument("--verify-only", action="store_true", help="Read-only mode; do not create/install anything.")
    parser.add_argument("--auto-from-registry", action="store_true", help="If --venv matches registry, auto-load requirements/import checks.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON summary.")
    parser.add_argument("--quiet", action="store_true", help="Suppress normal bootstrap logs.")
    args = parser.parse_args(argv)

    if args.all:
        results: list[BootstrapResult] = []
        for managed_env_id, config in iter_managed_envs():
            result = _bootstrap_one(
                env_id=managed_env_id,
                app=str(config.get("app", managed_env_id)),
                venv_rel=str(config["venv"]),
                requirements=str(config.get("requirements", "")) or None,
                imports=[str(item) for item in list(config.get("imports", []))],
                fallback_packages=[str(item) for item in list(config.get("packages", []))],
                verify_only=bool(args.verify_only),
                quiet=bool(args.quiet),
                python_launcher=str(args.python_launcher),
            )
            results.append(result)
        ok = all(item.ok for item in results)
        payload = {
            "ok": ok,
            "results": [_result_to_dict(item) for item in results],
            "summary": {
                "total": len(results),
                "passed": sum(1 for item in results if item.ok),
                "failed": sum(1 for item in results if not item.ok),
            },
        }
        if args.json_output:
            print(json.dumps(payload, indent=2))
        else:
            _log(
                f"summary: {payload['summary']['passed']}/{payload['summary']['total']} healthy"
                + ("" if ok else " (failures detected)"),
                quiet=bool(args.quiet),
            )
        return 0 if ok else 1

    env_id = args.env_id
    app = args.env_id or "custom"
    venv_rel = args.venv
    requirements = args.requirements
    check_imports = [str(item) for item in args.check_import]
    fallback_packages = [str(item) for item in args.install_package]

    if env_id:
        config = get_env_config(env_id)
        if not config:
            parser.error(f"Unknown env id: {env_id}")
        app = str(config.get("app", env_id))
        venv_rel = str(config["venv"])
        requirements = str(config.get("requirements", "")) or requirements
        check_imports = [str(item) for item in list(config.get("imports", []))]
        fallback_packages = [str(item) for item in list(config.get("packages", []))]
    elif venv_rel and args.auto_from_registry:
        discovered_env_id = find_env_id_by_venv_path(venv_rel)
        if discovered_env_id:
            config = get_env_config(discovered_env_id)
            if config:
                env_id = discovered_env_id
                app = str(config.get("app", discovered_env_id))
                requirements = str(config.get("requirements", "")) or requirements
                check_imports = [str(item) for item in list(config.get("imports", []))]
                fallback_packages = [str(item) for item in list(config.get("packages", []))]

    if not venv_rel:
        parser.error("Provide --venv, --env-id, or --all")

    if args.auto_from_registry and not env_id and not args.requirements and not check_imports:
        payload = {
            "ok": True,
            "skipped": True,
            "venv": venv_rel,
            "message": "venv is not registry-managed; skipped bootstrap",
        }
        if args.json_output:
            print(json.dumps(payload, indent=2))
        else:
            _log(f"{venv_rel}: not registry-managed -> skipping", quiet=bool(args.quiet))
        return 0

    result = _bootstrap_one(
        env_id=env_id,
        app=app,
        venv_rel=venv_rel,
        requirements=requirements,
        imports=check_imports,
        fallback_packages=fallback_packages,
        verify_only=bool(args.verify_only),
        quiet=bool(args.quiet),
        python_launcher=str(args.python_launcher),
    )

    if args.json_output:
        print(json.dumps({"ok": result.ok, "result": _result_to_dict(result)}, indent=2))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
