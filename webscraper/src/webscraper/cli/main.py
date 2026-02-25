"""CLI entrypoint for the webscraper ultimate scraper."""

from __future__ import annotations

import argparse
import os
from typing import Sequence

from webscraper import ultimate_scraper_legacy as legacy
from webscraper.utils.io import make_run_id, safe_write_json, utc_now_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Selenium ticket scraper (config-driven)",
        add_help=True,
    )
    parser.add_argument("--dry-run", action="store_true", help="Create run metadata and exit without launching Selenium")
    parser.add_argument("--out", default=os.path.join("webscraper", "output"), help="Output directory")
    return parser


def prepare_run_output_dir(base_out_dir: str, mode: str = "cli_dry_run") -> tuple[str, dict[str, str]]:
    started_utc = utc_now_iso()
    run_id = make_run_id(handle=None, mode=mode, browser="edge", base_url="", started_utc=started_utc)
    run_dir = os.path.abspath(os.path.join(base_out_dir, run_id))
    os.makedirs(run_dir, exist_ok=True)
    metadata = {
        "timestamp_utc": started_utc,
        "started_utc": started_utc,
        "mode": mode,
        "browser": "edge",
        "run_id": run_id,
        "out_dir": run_dir,
    }
    metadata_path = os.path.join(run_dir, "run_metadata.json")
    safe_write_json(metadata_path, metadata)
    return run_dir, metadata


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)

    if args.dry_run:
        run_dir, _metadata = prepare_run_output_dir(args.out)
        print(f"[INFO] Dry run complete: {run_dir}")
        return 0

    if argv is not None and unknown:
        # Preserve legacy behavior for caller-provided argv by delegating unchanged args.
        return legacy.main()

    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main", "prepare_run_output_dir"]
