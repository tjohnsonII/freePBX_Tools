#!/usr/bin/env python3
"""
Test comprehensive scraping on just 2 entries
"""

import subprocess
import sys

print("=" * 80)
print("Testing Comprehensive Scraping (2 entries only)")
print("=" * 80)
print()
print("This will scrape:")
print("  • Main detail pages")
print("  • Site Notes")
print("  • Site Specific Config")
print("  • Edit page")
print("  • View Config (under Edit)")
print("  • Bulk Attribute Edit (under Edit)")
print()
print("Output: freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive")
print()
print("=" * 80)
print()

# Run the scraper with comprehensive mode on just 2 entries
cmd = [
    sys.executable,
    "scrape_vpbx_tables.py",
    "--output", "freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive",
    "--max-details", "2",
    "--comprehensive"
]

print(f"Running: {' '.join(cmd)}")
print()

result = subprocess.run(cmd, cwd=r"c:\freepbx-tools")
sys.exit(result.returncode)
