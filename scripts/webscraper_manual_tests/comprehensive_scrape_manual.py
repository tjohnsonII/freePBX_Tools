#!/usr/bin/env python3
# Manual / integration script; not run by pytest.
"""Run a small comprehensive VPBX scrape for manual validation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    scraper_script = repo_root / "webscraper" / "legacy" / "scrape_vpbx_tables.py"

    print("=" * 80)
    print("Testing Comprehensive Scraping (2 entries only)")
    print("=" * 80)
    print("Output: freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive")
    print()

    cmd = [
        sys.executable,
        str(scraper_script),
        "--output",
        "freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive",
        "--max-details",
        "2",
        "--comprehensive",
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
