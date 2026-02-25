"""Run all-handle scraper defaults via `python -m webscraper`."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "scrape_all_handles.py"
    spec = importlib.util.spec_from_file_location("scrape_all_handles", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load scraper entrypoint: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
