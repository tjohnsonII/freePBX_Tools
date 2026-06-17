#!/usr/bin/env python3
"""Legacy entrypoint stub. See webscraper/legacy for real implementation."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    legacy_path = Path(__file__).resolve().parent / "webscraper" / "legacy" / "batch_ticket_scrape.py"
    print(f"Moved to webscraper/legacy/{legacy_path.name}. Running forwarded script.")
    sys.path.insert(0, str(legacy_path.parent))
    runpy.run_path(str(legacy_path), run_name="__main__")


if __name__ == "__main__":
    main()
