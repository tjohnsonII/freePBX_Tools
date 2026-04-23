"""Top-level scrape orchestration entrypoint."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from webscraper import ultimate_scraper_legacy as legacy
from webscraper.cli.main import prepare_run_output_dir
from webscraper.config import load_config
from webscraper.handles_loader import load_handles


def _build_config(mode: str, dry_run: bool) -> dict[str, Any]:
    output_dir = str((Path(__file__).resolve().parents[3] / "var" / "output").resolve())
    cfg = load_config()
    handles = load_handles()
    return {
        "url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
        "output_dir": output_dir,
        "handles": handles,
        "resume": True,
        "dry_run": dry_run,
        "browser": cfg.browser,
        "headless": True,
        "profile_dir": str(cfg.profile_dir),
        "profile_name": cfg.profile_name,
        "cookie_file": os.getenv("WEBSCRAPER_COOKIES_FILE", str((Path(__file__).resolve().parents[3] / "var" / "auth" / "cookies.json").resolve())),
        "auth_check_url": (os.getenv("WEBSCRAPER_AUTH_URLS", "").split(",")[0].strip() or "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"),
        "auth_timeout": cfg.auth_timeout,
        "show_browser": True,
        "auth_orchestration": True,
        "db_path": str((Path(__file__).resolve().parents[3] / "var" / "output" / "tickets.sqlite").resolve()),
    }


def run_scrape(
    config: dict[str, Any] | None = None,
    *,
    mode: str = "incremental",
    dry_run: bool = False,
    limit: int = 25,
) -> None:
    """Dispatch to the existing selenium runtime preserving behavior."""

    runtime_config = dict(config or _build_config(mode=mode, dry_run=dry_run))
    is_dry_run = bool(runtime_config.pop("dry_run", dry_run))

    if is_dry_run:
        prepare_run_output_dir(runtime_config.get("output_dir", "webscraper/output"), mode="cli_dry_run")
        return

    if mode == "tickets":
        runtime_config.update(
            {
                "scrape_ticket_details_enabled": True,
                "max_tickets": limit,
                "handles": runtime_config.get("handles") or ["123NET"],
            }
        )

    legacy.selenium_scrape_tickets(**runtime_config)

    if mode == "tickets":
        out_dir = Path("webscraper") / "var" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        latest = out_dir / "tickets_latest.json"
        generated = Path(runtime_config["output_dir"]) / "tickets_all.json"
        if generated.exists():
            latest.write_text(generated.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[SCRAPE] tickets_latest.json written: {latest}")


__all__ = ["run_scrape"]
