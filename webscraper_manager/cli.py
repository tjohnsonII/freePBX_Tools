from __future__ import annotations

from pathlib import Path

import typer

EXIT_DOCTOR_ISSUES = 10

app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@app.callback()
def _root() -> None:
    """webscraper_manager command group."""

@app.command()
def doctor() -> None:
    """Validate a minimal webscraper_manager setup."""
    root = _repo_root()
    checks = {
        "repo_root": root.exists(),
        "webscraper_dir": (root / "webscraper").is_dir(),
        "webscraper_requirements": (root / "webscraper" / "requirements.txt").is_file(),
    }

    has_issues = False
    for key, ok in checks.items():
        symbol = "✅" if ok else "❌"
        typer.echo(f"{symbol} {key}")
        if not ok:
            has_issues = True

    if has_issues:
        raise typer.Exit(EXIT_DOCTOR_ISSUES)

    typer.echo("Doctor checks passed.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
