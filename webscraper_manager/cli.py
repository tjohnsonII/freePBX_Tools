from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from webscraper_manager import __version__

try:
    import typer

    TYPER_AVAILABLE = True
except Exception:
    typer = None  # type: ignore[assignment]
    TYPER_AVAILABLE = False

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:
    Console = Any  # type: ignore[assignment]
    RICH_AVAILABLE = False

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DOCTOR_ISSUES = 10

TITLE_TEXT = "FreePBX Webscraper Manager"
SUBTITLE_TEXT = "CLI manager for status, tests, auth, API checks, and start/stop"


@dataclass
class AppState:
    quiet: bool = False
    verbose: bool = False
    no_banner: bool = False
    color: bool = True
    json_output: bool = False


@dataclass
class Finding:
    check: str
    ok: bool
    details: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_console(state: AppState) -> Console | None:
    """Return a Rich console when available; otherwise use plain output."""
    if not RICH_AVAILABLE:
        return None
    return Console(no_color=not state.color)


def print_banner(console: Console | None, state: AppState) -> None:
    """Print a startup banner when output mode allows it."""
    if state.quiet or state.no_banner or state.json_output:
        return

    if console is None:
        print(f"{TITLE_TEXT}\n{SUBTITLE_TEXT}")
        return

    title = Text(TITLE_TEXT, style="bold cyan", justify="center")
    subtitle = Text(SUBTITLE_TEXT, style="bright_black", justify="center")
    banner_body = Text.assemble(title, "\n", subtitle)
    console.print(
        Panel(
            banner_body,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 3),
            expand=True,
        )
    )


def print_menu_banner(console: Console | None, state: AppState) -> None:
    """Always render the menu banner, regardless of quiet/json output mode."""
    forced = AppState(
        quiet=False,
        verbose=state.verbose,
        no_banner=False,
        color=state.color,
        json_output=False,
    )
    print_banner(console, forced)


def print_findings_table(console: Console | None, findings: list[Finding]) -> None:
    """Print doctor findings in table format, with fallback plain text."""
    if console is None:
        for finding in findings:
            symbol = "OK" if finding.ok else "FAIL"
            print(f"{finding.check}: {symbol} - {finding.details}")
        return

    table = Table(title="Doctor Checks", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Details", style="bright_black")

    for finding in findings:
        status = "[green]✅ OK[/green]" if finding.ok else "[red]❌ FAIL[/red]"
        table.add_row(finding.check, status, finding.details)

    console.print(table)


def print_result_panel(console: Console | None, ok: bool, message: str) -> None:
    """Print final status with Rich panel when available, plain text otherwise."""
    if console is None:
        print(message)
        return

    final_style = "green" if ok else "red"
    console.print(
        Panel(
            Text(message, justify="center", style=f"bold {final_style}"),
            border_style=final_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def print_version(state: AppState) -> None:
    """Print version using quiet/plain behavior rules."""
    if state.quiet or state.json_output:
        print(__version__)
        return

    console = get_console(state)
    if console is None:
        print(f"webscraper_manager {__version__}")
        return

    console.print(
        Panel(
            Text(f"webscraper_manager {__version__}", justify="center", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _doctor_findings() -> list[Finding]:
    root = _repo_root()
    return [
        Finding("repo_root", root.exists(), f"Found repo root at {root}"),
        Finding(
            "webscraper_dir",
            (root / "webscraper").is_dir(),
            f"Expected directory: {root / 'webscraper'}",
        ),
        Finding(
            "webscraper_requirements",
            (root / "webscraper" / "requirements.txt").is_file(),
            f"Expected file: {root / 'webscraper' / 'requirements.txt'}",
        ),
    ]


def run_doctor(state: AppState, json_out: bool = False) -> tuple[bool, list[Finding]]:
    """Run doctor checks and return the result without printing."""
    findings = _doctor_findings()
    ok = all(finding.ok for finding in findings)
    _ = json_out
    return ok, findings


def execute_doctor(state: AppState, json_out: bool = False, show_banner: bool = False) -> int:
    """Execute doctor output flow using shared check logic."""
    ok, findings = run_doctor(state, json_out=json_out)

    if json_out or state.json_output:
        payload = {
            "ok": ok,
            "findings": [asdict(finding) for finding in findings],
        }
        print(json.dumps(payload, indent=2))
    elif state.quiet:
        print("Doctor checks passed." if ok else "Doctor checks found issues.")
    else:
        console = get_console(state)
        if show_banner:
            print_banner(console, state)
        print_findings_table(console, findings)

        if state.verbose:
            message = f"Verbose: evaluated {len(findings)} checks from root: {_repo_root()}"
            if console is None:
                print(message)
            else:
                console.print(f"[bright_black]{message}[/bright_black]")

        final_message = "Doctor checks passed." if ok else "Doctor checks found issues."
        print_result_panel(console, ok, final_message)

    return EXIT_OK if ok else EXIT_DOCTOR_ISSUES


def _set_flag_from_source(ctx: Any, name: str, value: bool) -> Optional[bool]:
    """Return value when explicitly set on command line; otherwise None."""
    try:
        source = ctx.get_parameter_source(name)
        if source is not None and source.name != "DEFAULT":
            return value
    except Exception:
        if value:
            return value
    return None


def _clear_screen() -> None:
    command = "cls" if os.name == "nt" else "clear"
    os.system(command)


def _wait_for_enter() -> None:
    try:
        input("\nPress Enter to return to menu…")
    except KeyboardInterrupt:
        print("\nExiting menu.")
        raise


def _menu_options_table(console: Console | None) -> None:
    if console is None:
        print("\nMenu")
        print("[1] Doctor (normal) - Run doctor with normal output")
        print("[2] Doctor (quiet) - Run doctor with minimal output")
        print("[3] Doctor (global quiet before command) - Equivalent to --quiet doctor")
        print("[4] Doctor (json) - Run doctor and print JSON only")
        print("[5] Version - Show version")
        print("[q] Quit")
        return

    table = Table(title="Menu", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Option", justify="center", no_wrap=True)
    table.add_column("Command", style="white", no_wrap=True)
    table.add_column("Description", style="bright_black")
    table.add_row("1", "Doctor (normal)", "Same as: doctor")
    table.add_row("2", "Doctor (quiet)", "Same as: doctor --quiet")
    table.add_row("3", "Doctor (global quiet before command)", "Same as: --quiet doctor")
    table.add_row("4", "Doctor (json)", "Same as: doctor --json")
    table.add_row("5", "Version", "Same as: --version")
    table.add_row("q", "Quit", "Exit menu")
    console.print(table)


def run_menu(state: AppState) -> int:
    """Interactive menu for common commands."""
    console = get_console(state)

    while True:
        _clear_screen()
        print_menu_banner(console, state)
        _menu_options_table(console)

        try:
            choice = input("\nSelect an option [1-5, q]: ").strip().lower()
        except KeyboardInterrupt:
            print("\nExiting menu.")
            return EXIT_OK

        if choice == "q":
            return EXIT_OK

        try:
            if choice == "1":
                run_state = AppState(quiet=False, verbose=state.verbose, no_banner=False, color=state.color, json_output=False)
                execute_doctor(run_state, show_banner=True)
                _wait_for_enter()
            elif choice == "2":
                run_state = AppState(quiet=True, verbose=state.verbose, no_banner=True, color=state.color, json_output=False)
                execute_doctor(run_state)
                _wait_for_enter()
            elif choice == "3":
                run_state = AppState(quiet=True, verbose=state.verbose, no_banner=True, color=state.color, json_output=False)
                execute_doctor(run_state)
                _wait_for_enter()
            elif choice == "4":
                run_state = AppState(quiet=False, verbose=state.verbose, no_banner=True, color=state.color, json_output=True)
                execute_doctor(run_state, json_out=True)
                _wait_for_enter()
            elif choice == "5":
                print_version(state)
                _wait_for_enter()
            else:
                print("Invalid selection. Enter 1, 2, 3, 4, 5, or q.")
                _wait_for_enter()
        except KeyboardInterrupt:
            return EXIT_OK


if TYPER_AVAILABLE:
    app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)

    def _version_callback(value: bool) -> None:
        if not value:
            return
        print_version(AppState(quiet=True, no_banner=True))
        raise typer.Exit(EXIT_OK)

    @app.callback(invoke_without_command=False)
    def _root(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output (no banner)."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        no_banner: bool = typer.Option(
            False,
            "--no-banner",
            help="Suppress banner output (alias behavior of --quiet).",
        ),
        color: bool = typer.Option(True, "--color/--no-color", help="Enable color output."),
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ) -> None:
        """webscraper_manager command group.

        Global flags are defined here for `--quiet doctor` style usage. Commands also
        define the same options for `doctor --quiet`, then merge command values over
        callback values when explicitly provided.
        """
        del version
        if ctx.resilient_parsing:
            return

        state = AppState(
            quiet=quiet,
            verbose=verbose,
            no_banner=no_banner or quiet,
            color=color,
            json_output="--json" in sys.argv,
        )
        ctx.obj = state

        if (
            ctx.invoked_subcommand
            and ctx.invoked_subcommand != "menu"
            and not state.no_banner
            and not state.json_output
        ):
            print_banner(get_console(state), state)

    @app.command()
    def doctor(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        """Validate a minimal webscraper_manager setup."""
        state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()

        quiet_override = _set_flag_from_source(ctx, "quiet", quiet)
        verbose_override = _set_flag_from_source(ctx, "verbose", verbose)
        json_override = _set_flag_from_source(ctx, "json_output", json_output)

        if quiet_override is not None:
            state.quiet = quiet_override
            state.no_banner = quiet_override
        if verbose_override is not None:
            state.verbose = verbose_override
        if json_override is not None:
            state.json_output = json_override

        exit_code = execute_doctor(state)
        if exit_code:
            raise typer.Exit(exit_code)

    @app.command()
    def menu(ctx: typer.Context) -> None:
        """Open interactive command menu."""
        state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()
        exit_code = run_menu(state)
        if exit_code:
            raise typer.Exit(exit_code)


def _argparse_fallback(argv: list[str] | None = None) -> int:
    """Minimal CLI when Typer is unavailable (wrong interpreter/missing deps)."""
    argv = list(argv or sys.argv[1:])

    quiet = False
    verbose = False
    normalized_argv: list[str] = []
    for token in argv:
        if token == "--quiet":
            quiet = True
            continue
        if token == "--verbose":
            verbose = True
            continue
        normalized_argv.append(token)

    root = argparse.ArgumentParser(prog="webscraper_manager", description="Manage webscraper workflows")
    root.add_argument("--version", action="store_true", help="Show version and exit")

    subparsers = root.add_subparsers(dest="command")
    doctor_parser = subparsers.add_parser("doctor", help="Run doctor checks")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    subparsers.add_parser("menu", help="Open interactive menu")

    args = root.parse_args(normalized_argv)
    if args.version:
        print_version(AppState(quiet=True, no_banner=True))
        return EXIT_OK

    if args.command == "menu":
        return run_menu(AppState(quiet=quiet, verbose=verbose, no_banner=quiet))

    if args.command != "doctor":
        root.print_help()
        return EXIT_USAGE if normalized_argv else EXIT_OK

    state = AppState(
        quiet=quiet,
        verbose=verbose,
        no_banner=quiet,
        json_output=bool(args.json_output),
    )

    if not TYPER_AVAILABLE and state.verbose:
        print(
            "Warning: Typer is not installed in this Python environment. "
            "Using minimal argparse fallback. Install typer with: pip install typer[all]"
        )
    if not RICH_AVAILABLE and state.verbose and not state.json_output:
        print("Info: Rich is not installed; using plain text output. Install with: pip install rich")

    if not state.no_banner and not state.json_output:
        print_banner(get_console(state), state)
    return execute_doctor(state)


def main() -> None:
    if TYPER_AVAILABLE:
        app()
        return

    argv = sys.argv[1:]
    quiet_mode = "--quiet" in argv
    json_mode = "--json" in argv
    if not quiet_mode and not json_mode:
        print(
            "Warning: Typer dependency is missing; running minimal fallback CLI. "
            "Install typer with: pip install typer[all]"
        )
    raise SystemExit(_argparse_fallback(argv))


if __name__ == "__main__":
    main()
