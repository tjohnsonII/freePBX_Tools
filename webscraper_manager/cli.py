from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import typer

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # Rich is optional; keep CLI usable without it.
    Console = Any  # type: ignore[assignment]
    RICH_AVAILABLE = False

EXIT_DOCTOR_ISSUES = 10

TITLE_TEXT = "FreePBX Webscraper Manager"
SUBTITLE_TEXT = "CLI manager for status, tests, auth, API checks, and start/stop"

app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)


@dataclass
class Finding:
    check: str
    ok: bool
    details: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_console() -> Console | None:
    """Return a Rich console when available; otherwise use plain output."""
    if not RICH_AVAILABLE:
        return None
    return Console()


def _is_json_mode() -> bool:
    return "--json" in sys.argv


def print_banner(console: Console | None) -> None:
    """Print a centered startup banner."""
    if console is None:
        typer.echo(f"{TITLE_TEXT}\n{SUBTITLE_TEXT}")
        return

    title = Text(TITLE_TEXT, style="bold cyan", justify="center")
    subtitle = Text(SUBTITLE_TEXT, style="bright_black", justify="center")
    banner_body = Text.assemble(title, "\n", subtitle)
    console.print(
        Panel(
            banner_body,
            border_style="blue",
            box=box.DOUBLE_EDGE,
            padding=(1, 4),
            expand=True,
        )
    )


def print_findings_table(console: Console | None, findings: list[Finding]) -> None:
    """Print doctor findings in table format, with fallback plain text."""
    if console is None:
        for finding in findings:
            symbol = "✅" if finding.ok else "❌"
            typer.echo(f"{finding.check}: {symbol} - {finding.details}")
        return

    table = Table(title="Doctor Checks", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Details", style="bright_black")

    for finding in findings:
        status = "[green]✅ OK[/green]" if finding.ok else "[red]❌ FAIL[/red]"
        table.add_row(finding.check, status, finding.details)

    console.print(table)


@app.callback()
def _root(
    ctx: typer.Context,
    quiet: bool = typer.Option(False, "--quiet", help="Minimal output (no banner)."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
) -> None:
    """webscraper_manager command group."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose
    ctx.obj["console"] = get_console()

    if ctx.resilient_parsing:
        return

    if not quiet and not _is_json_mode():
        print_banner(ctx.obj["console"])


@app.command()
def doctor(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
) -> None:
    """Validate a minimal webscraper_manager setup."""
    root = _repo_root()
    findings = [
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

    has_issues = any(not finding.ok for finding in findings)

    if json_output:
        payload = {
            "ok": not has_issues,
            "findings": [asdict(finding) for finding in findings],
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        console = (ctx.obj or {}).get("console") if ctx.obj else None
        print_findings_table(console, findings)

        verbose = bool((ctx.obj or {}).get("verbose")) if ctx.obj else False
        if verbose:
            message = f"Verbose: evaluated {len(findings)} checks from root: {root}"
            if console is None:
                typer.echo(message)
            else:
                console.print(f"[bright_black]{message}[/bright_black]")

        if console is None:
            typer.echo("Doctor checks found issues." if has_issues else "Doctor checks passed.")
        else:
            final_message = "Doctor checks found issues." if has_issues else "Doctor checks passed."
            final_style = "red" if has_issues else "green"
            console.print(
                Panel(
                    Text(final_message, justify="center", style=f"bold {final_style}"),
                    border_style=final_style,
                    box=box.ROUNDED,
                    padding=(0, 2),
                )
            )

    if has_issues:
        raise typer.Exit(EXIT_DOCTOR_ISSUES)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
