from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    in_menu: bool = False
    pure_json_mode: bool = False
    clear_screen: bool = False


@dataclass
class Finding:
    check: str
    ok: bool
    details: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_console(state: AppState) -> Console | None:
    if not RICH_AVAILABLE:
        return None
    no_color = bool(os.environ.get("NO_COLOR"))
    return Console(no_color=no_color)


def should_print_banner(state: AppState, json_out: bool, is_help: bool) -> bool:
    if is_help:
        return False
    if state.in_menu:
        return False
    if state.quiet:
        return False
    if json_out:
        return False
    return True


def print_banner(console: Console | None) -> None:
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


def print_findings_table(console: Console | None, findings: list[Finding]) -> None:
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


def run_doctor(console: Console | None, state: AppState, json_out: bool) -> tuple[int, dict[str, Any] | None]:
    findings = _doctor_findings()
    ok = all(finding.ok for finding in findings)
    payload = {
        "ok": ok,
        "findings": [asdict(finding) for finding in findings],
    }

    if json_out:
        print(json.dumps(payload, indent=2))
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), payload

    if state.quiet:
        print("Doctor checks passed." if ok else "Doctor checks found issues.")
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None

    print_findings_table(console, findings)

    if state.verbose:
        message = f"Verbose: evaluated {len(findings)} checks from root: {_repo_root()}"
        if console is None:
            print(message)
        else:
            console.print(f"[bright_black]{message}[/bright_black]")

    final_message = "Doctor checks passed." if ok else "Doctor checks found issues."
    print_result_panel(console, ok, final_message)
    return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None


def run_version(console: Console | None, state: AppState) -> None:
    if state.quiet:
        print(__version__)
        return
    if console is None:
        print(__version__)
        return
    console.print(
        Panel(
            Text(f"webscraper_manager {__version__}", justify="center", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _set_flag_from_source(ctx: Any, name: str, value: bool) -> bool | None:
    try:
        source = ctx.get_parameter_source(name)
        if source is not None and source.name != "DEFAULT":
            return value
    except Exception:
        if value:
            return value
    return None


def _clear_screen(state: AppState) -> None:
    if not state.clear_screen:
        return
    if os.name == "nt":
        os.system("cls")
        return
    os.system("clear")


def _read_line(prompt: str) -> str:
    return input(prompt).strip().lower()


def _confirm_quit() -> bool:
    try:
        answer = _read_line("Quit? [y/N] ")
    except KeyboardInterrupt:
        print()
        return False
    return answer in {"y", "yes"}


def render_menu(console: Console | None, state: AppState) -> None:
    _clear_screen(state)
    print_banner(console)
    clear_status = "ON" if state.clear_screen else "OFF"
    pure_json_status = "ON" if state.pure_json_mode else "OFF"

    if console is None:
        print(f"\nToggles: pure_json_mode: {pure_json_status} | clear: {clear_status}")
        print("\nMenu")
        print("[1] Doctor (normal)")
        print("[2] Doctor (quiet)")
        print("[3] Doctor (global quiet before command)")
        print("[4] Doctor (json)")
        print("[5] Version")
        print("[r] Refresh")
        print(f"[t] Toggle pure JSON mode (currently {pure_json_status})")
        print("[q] Quit")
        return

    table = Table(title="Menu", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Option", justify="center", no_wrap=True)
    table.add_column("Command", style="white", no_wrap=True)
    table.add_column("Description", style="bright_black")
    table.caption = f"pure_json_mode: {pure_json_status} | clear: {clear_status}"
    table.add_row("1", "Doctor (normal)", "Same as: doctor")
    table.add_row("2", "Doctor (quiet)", "Same as: doctor --quiet")
    table.add_row("3", "Doctor (global quiet before command)", "Same as: --quiet doctor")
    table.add_row("4", "Doctor (json)", "Same as: doctor --json")
    table.add_row("5", "Version", "Same as: --version")
    table.add_row("r", "Refresh", "Redraw the menu")
    table.add_row("t", "Toggle pure JSON mode", f"Currently: {pure_json_status}")
    table.add_row("q", "Quit", "Exit menu (with confirmation)")
    console.print(table)


def _run_menu_action(console: Console | None, state: AppState, choice: str) -> int:
    if choice == "1":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "2":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "3":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "4":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
        )
        if not state.pure_json_mode:
            print("Running: doctor --json")
        code, _ = run_doctor(console, action_state, json_out=True)
        return code
    if choice == "5":
        action_state = AppState(
            quiet=state.quiet,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
        )
        run_version(console, action_state)
        return EXIT_OK
    return EXIT_USAGE


def pause_for_user() -> None:
    print()
    print("Press Enter to return to menu…")
    try:
        if not sys.stdin.isatty():
            print("(No interactive stdin; returning to menu in 2s...)")
            time.sleep(2)
            return
        input()
    except EOFError:
        print("(No interactive stdin; returning to menu in 2s...)")
        time.sleep(2)
    except KeyboardInterrupt:
        print()
        return


def run_menu(state: AppState) -> int:
    state.in_menu = True
    console = get_console(state)

    while True:
        render_menu(console, state)
        try:
            choice = _read_line("\nSelect an option [1-5, r, t, q]: ")
        except KeyboardInterrupt:
            print()
            continue

        if choice == "r":
            continue

        if choice == "t":
            state.pure_json_mode = not state.pure_json_mode
            mode = "ON" if state.pure_json_mode else "OFF"
            print(f"pure_json_mode: {mode}")
            continue

        if choice == "q":
            if _confirm_quit():
                return EXIT_OK
            continue

        if choice not in {"1", "2", "3", "4", "5"}:
            print("Invalid selection. Enter 1, 2, 3, 4, 5, r, t, or q.")
            continue

        try:
            _run_menu_action(console, state, choice)
        except KeyboardInterrupt:
            if not state.pure_json_mode:
                print("Canceled.")
            continue

        pause_for_user()


def _build_state_from_ctx(ctx: Any, quiet: bool, verbose: bool) -> AppState:
    state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()

    quiet_override = _set_flag_from_source(ctx, "quiet", quiet)
    verbose_override = _set_flag_from_source(ctx, "verbose", verbose)

    if quiet_override is not None:
        state.quiet = quiet_override
    if verbose_override is not None:
        state.verbose = verbose_override
    return state


if TYPER_AVAILABLE:
    app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)

    def _version_callback(value: bool) -> None:
        if not value:
            return
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        raise typer.Exit(EXIT_OK)

    @app.callback(invoke_without_command=False)
    def _root(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output (no banner)."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ) -> None:
        del version
        if ctx.resilient_parsing:
            return
        ctx.obj = AppState(quiet=quiet, verbose=verbose)

    @app.command()
    def doctor(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose)
        json_override = _set_flag_from_source(ctx, "json_output", json_output)
        use_json = bool(json_override) if json_override is not None else json_output

        if should_print_banner(state, json_out=use_json, is_help=False):
            print_banner(get_console(state))

        code, _ = run_doctor(get_console(state), state, json_out=use_json)
        if code:
            raise typer.Exit(code)

    @app.command()
    def menu(
        ctx: typer.Context,
        clear_screen: bool = typer.Option(
            False,
            "--clear",
            "--clear-screen",
            help="Clear the screen at the start of each menu render.",
        ),
        no_clear: bool = typer.Option(False, "--no-clear", help="Do not clear the screen between menu draws."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output for menu actions."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose)
        state.clear_screen = bool(clear_screen and not no_clear)
        code = run_menu(state)
        if code:
            raise typer.Exit(code)


def _argparse_fallback(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])

    root = argparse.ArgumentParser(prog="webscraper_manager", description="Manage webscraper workflows")
    root.add_argument("--version", action="store_true", help="Show version and exit")

    subparsers = root.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Run doctor checks")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    doctor_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    doctor_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    menu_parser = subparsers.add_parser("menu", help="Open interactive menu")
    menu_parser.add_argument("--clear", "--clear-screen", action="store_true", dest="clear_screen", help="Clear the screen when drawing the menu")
    menu_parser.add_argument("--no-clear", action="store_true", help="Do not clear the screen")
    menu_parser.add_argument("--quiet", action="store_true", help="Minimal output for menu actions")
    menu_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    root.add_argument("--quiet", action="store_true", help="Minimal output")
    root.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = root.parse_args(argv)

    if args.version:
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        return EXIT_OK

    if args.command == "menu":
        state = AppState(
            quiet=bool(args.quiet),
            verbose=bool(args.verbose),
            clear_screen=bool(args.clear_screen and not args.no_clear),
        )
        return run_menu(state)

    if args.command == "doctor":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose))
        if should_print_banner(state, json_out=bool(args.json_output), is_help=False):
            print_banner(get_console(state))
        code, _ = run_doctor(get_console(state), state, json_out=bool(args.json_output))
        return code

    root.print_help()
    return EXIT_USAGE if argv else EXIT_OK


def main() -> None:
    argv = sys.argv[1:]
    if TYPER_AVAILABLE:
        app()
        return

    try:
        raise SystemExit(_argparse_fallback(argv))
    except KeyboardInterrupt:
        raise


if __name__ == "__main__":
    main()

# Test commands
# python -m webscraper_manager menu
# python -m webscraper_manager doctor --quiet
# python -m webscraper_manager doctor --json
# python -m webscraper_manager --version
