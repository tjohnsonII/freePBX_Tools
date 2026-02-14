"""CLI entrypoint for the webscraper ultimate scraper."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Sequence

from webscraper import ultimate_scraper_legacy as legacy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Selenium ticket scraper (config-driven)",
        add_help=True,
    )
    parser.add_argument("--dry-run", action="store_true", help="Create run metadata and exit without launching Selenium")
    parser.add_argument("--out", default=os.path.join("webscraper", "output"), help="Output directory")
    return parser


def prepare_run_output_dir(base_out_dir: str, mode: str = "cli_dry_run") -> tuple[str, dict[str, str]]:
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    run_dir = os.path.abspath(os.path.join(base_out_dir, run_id))
    os.makedirs(run_dir, exist_ok=True)
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "run_id": run_id,
        "out_dir": run_dir,
    }
    metadata_path = os.path.join(run_dir, "run_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
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
