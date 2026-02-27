from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .api import health_check, ping, tail
from .auth import authenticate
from .config import ensure_runtime_dirs, load_or_create_config
from .doctor import EXIT_DOCTOR_ISSUES, has_issues, run_doctor
from .fix import apply_safe_fixes
from .process import EXIT_START_FAILED, is_port_listening, relevant_processes, start_scraper, start_ui, stop_everything, stop_managed_process
from .tests import EXIT_TEST_FAILED, run_integration, run_smoke, run_unit

app = typer.Typer(help="Manage webscraper workflows")
api_app = typer.Typer(help="API checks")
auth_app = typer.Typer(help="Authentication helpers")
start_app = typer.Typer(help="Start services")
stop_app = typer.Typer(help="Stop services")
test_app = typer.Typer(help="Testing commands")
app.add_typer(api_app, name="api")
app.add_typer(auth_app, name="auth")
app.add_typer(start_app, name="start")
app.add_typer(stop_app, name="stop")
app.add_typer(test_app, name="test")
console = Console()


def _load(verbose: bool = False):
    cfg = load_or_create_config()
    ensure_runtime_dirs(cfg)
    if verbose:
        console.print(f"[dim]Repo root: {cfg.repo_root}[/dim]")
        console.print(f"[dim]Config file: {cfg.config_file}[/dim]")
    return cfg


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output"),
    version: bool = typer.Option(False, "--version", help="Print version", is_eager=True),
) -> None:
    if version:
        console.print(f"webscraper-manager {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        raise typer.Exit(2)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json"), fix: bool = typer.Option(False, "--fix")) -> None:
    cfg = _load()
    findings = run_doctor(cfg)

    if fix:
        actions = apply_safe_fixes(cfg)
        for action in actions:
            style = "green" if action.ok else "yellow"
            console.print(f"[{style}]fix::{action.name}[/{style}] {action.message}")

    if json_output:
        payload = [f.to_json() for f in findings]
        console.print(json.dumps(payload, indent=2))
    else:
        table = Table(title="webscraper-manager doctor")
        table.add_column("Status")
        table.add_column("Check")
        table.add_column("Message")
        table.add_column("Fix")
        symbol = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        for row in findings:
            table.add_row(symbol.get(row.status, "?"), row.key, row.message, row.fix or "")
        console.print(table)

    if has_issues(findings):
        raise typer.Exit(EXIT_DOCTOR_ISSUES)


@app.command()
def fix() -> None:
    cfg = _load()
    actions = apply_safe_fixes(cfg)
    for action in actions:
        color = "green" if action.ok else "yellow"
        console.print(f"[{color}] {action.name}: {action.message}")


@app.command()
def status() -> None:
    cfg = _load()
    table = Table(title="webscraper status")
    table.add_column("PID")
    table.add_column("Name")
    table.add_column("Cmd")
    for row in relevant_processes():
        table.add_row(str(row["pid"]), str(row["name"]), str(row["cmdline"]))
    console.print(table)
    console.print(f"Port 8787 listening: {'yes' if is_port_listening(8787) else 'no'}")
    console.print("Quick start: webscraper-manager start ui | webscraper-manager start scraper")


@api_app.command("health")
def api_health(url: Optional[str] = typer.Option(None, "--url")) -> None:
    cfg = _load()
    base = url or cfg.base_url
    rows = health_check(base)
    for row in rows:
        console.print(f"{row.status_code} {row.latency_ms}ms {row.url} -> {row.body_snippet[:80]}")


@api_app.command("ping")
def api_ping(
    url: str = typer.Option("http://127.0.0.1:8787", "--url"),
    path: str = typer.Option("/api/events/latest?limit=50", "--path"),
) -> None:
    row = ping(url, path)
    console.print(f"{row.status_code} {row.latency_ms}ms {row.url}\n{row.body_snippet}")


@api_app.command("tail")
def api_tail(
    url: str = typer.Option("http://127.0.0.1:8787", "--url"),
    path: str = typer.Option("/api/events/latest?limit=10", "--path"),
    seconds: int = typer.Option(20, "--seconds"),
    interval: float = typer.Option(2.0, "--interval"),
) -> None:
    rows = tail(url, path, seconds=seconds, interval=interval)
    for row in rows:
        console.print(f"{row.status_code} {row.latency_ms}ms {row.body_snippet[:80]}")


@auth_app.command("chrome")
def auth_chrome(
    login_url: Optional[str] = typer.Option(None, "--login-url"),
    headless: bool = typer.Option(False, "--headless"),
    timeout: int = typer.Option(180, "--timeout"),
) -> None:
    cfg = _load()
    result = authenticate(cfg, browser="chrome", login_url=login_url or cfg.login_url, timeout=timeout, headless=headless)
    if result.success:
        console.print(f"✅ {result.message}")
    else:
        console.print(f"❌ {result.message}")
        raise typer.Exit(EXIT_START_FAILED)


@auth_app.command("edge")
def auth_edge(
    login_url: Optional[str] = typer.Option(None, "--login-url"),
    headless: bool = typer.Option(False, "--headless"),
    timeout: int = typer.Option(180, "--timeout"),
) -> None:
    cfg = _load()
    result = authenticate(cfg, browser="edge", login_url=login_url or cfg.login_url, timeout=timeout, headless=headless)
    if result.success:
        console.print(f"✅ {result.message}")
    else:
        console.print(f"❌ {result.message}")
        raise typer.Exit(EXIT_START_FAILED)


@start_app.command("ui")
def start_ui_cmd(detach: bool = typer.Option(False, "--detach")) -> None:
    cfg = _load()
    proc = start_ui(cfg, detach=detach)
    console.print(f"Started UI pid={proc.pid} command={' '.join(proc.command)}")


@start_app.command("scraper")
def start_scraper_cmd(detach: bool = typer.Option(False, "--detach"), watch: bool = typer.Option(False, "--watch")) -> None:
    cfg = _load()
    proc = start_scraper(cfg, detach=detach, watch=watch)
    console.print(f"Started scraper pid={proc.pid} command={' '.join(proc.command)}")


@start_app.command("everything")
def start_everything(
    fix: bool = typer.Option(False, "--fix"),
    detach: bool = typer.Option(False, "--detach"),
    require_auth: bool = typer.Option(False, "--require-auth"),
) -> None:
    cfg = _load()
    findings = run_doctor(cfg)
    if has_issues(findings) and not fix:
        console.print("Doctor found issues. Re-run with --fix or run doctor.")
        raise typer.Exit(EXIT_DOCTOR_ISSUES)
    if fix:
        apply_safe_fixes(cfg)

    if require_auth:
        auth_file = cfg.manager_home / "auth" / "chrome_cookies.json"
        if not auth_file.exists():
            console.print("Missing auth state; run: webscraper-manager auth chrome")
            raise typer.Exit(EXIT_START_FAILED)

    ui_proc = start_ui(cfg, detach=detach)
    scraper_proc = start_scraper(cfg, detach=detach)
    console.print(f"Started ui={ui_proc.pid}, scraper={scraper_proc.pid}")


@stop_app.command("ui")
def stop_ui_cmd() -> None:
    cfg = _load()
    ok = stop_managed_process(cfg, "ui")
    console.print("Stopped ui" if ok else "No ui PID file found")


@stop_app.command("scraper")
def stop_scraper_cmd() -> None:
    cfg = _load()
    ok = stop_managed_process(cfg, "scraper")
    console.print("Stopped scraper" if ok else "No scraper PID file found")


@stop_app.command("everything")
def stop_all_cmd() -> None:
    cfg = _load()
    stopped = stop_everything(cfg)
    console.print(f"Stopped: {', '.join(stopped) if stopped else 'none'}")


@test_app.command("smoke")
def test_smoke() -> None:
    cfg = _load()
    run = run_smoke(cfg)
    console.print(run.output)
    if run.returncode != 0:
        raise typer.Exit(EXIT_TEST_FAILED)


@test_app.command("unit")
def test_unit() -> None:
    cfg = _load()
    run = run_unit(cfg)
    console.print(run.output)
    if run.returncode != 0:
        raise typer.Exit(EXIT_TEST_FAILED)


@test_app.command("integration")
def test_integration() -> None:
    cfg = _load()
    run = run_integration(cfg)
    console.print(run.output)
    if run.returncode != 0:
        raise typer.Exit(EXIT_TEST_FAILED)


@test_app.command("all")
def test_all(keep_going: bool = typer.Option(False, "--keep-going")) -> None:
    cfg = _load()
    runs = [run_smoke(cfg), run_unit(cfg), run_integration(cfg)]
    failed = False
    for run in runs:
        console.rule(run.name)
        console.print(run.output)
        if run.returncode != 0:
            failed = True
            if not keep_going:
                break
    if failed:
        raise typer.Exit(EXIT_TEST_FAILED)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
