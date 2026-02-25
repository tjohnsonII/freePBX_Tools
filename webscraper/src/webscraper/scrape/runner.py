"""Top-level scrape orchestration entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from webscraper import ultimate_scraper_legacy as legacy
from webscraper.cli.main import prepare_run_output_dir


def _build_config(mode: str, dry_run: bool) -> dict[str, Any]:
    output_dir = str((Path(__file__).resolve().parents[3] / "var" / "output").resolve())
    return {
        "url": "https://secure.123.net/customers.cgi",
        "output_dir": output_dir,
        "handles": [],
        "resume": mode == "incremental",
        "dry_run": dry_run,
    }


def run_scrape(
    config: dict[str, Any] | None = None,
    *,
    mode: str = "incremental",
    dry_run: bool = False,
) -> None:
    """Dispatch to the existing selenium runtime preserving behavior."""

    runtime_config = dict(config or _build_config(mode=mode, dry_run=dry_run))
    is_dry_run = bool(runtime_config.pop("dry_run", dry_run))

    if is_dry_run:
        prepare_run_output_dir(runtime_config.get("output_dir", "webscraper/output"), mode="cli_dry_run")
        return

    legacy.selenium_scrape_tickets(**runtime_config)


__all__ = ["run_scrape"]
