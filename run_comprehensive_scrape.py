#!/usr/bin/env python3
"""
Run comprehensive scraping on ALL 556 entries
WARNING: This will take 2-3 hours to complete
"""

import subprocess
import sys

print("=" * 80)
print("COMPREHENSIVE SCRAPING - ALL 556 ENTRIES")
print("=" * 80)
print()
print("⚠️  WARNING: This will scrape approximately 3,336 pages ⚠️")
print()
print("Estimated time: 2-3 hours")
print()
print("For each of 556 entries, this will scrape:")
print("  1. Main detail page")
print("  2. Site Notes")
print("  3. Site Specific Config")
print("  4. Edit page")
print("  5. View Config (under Edit)")
print("  6. Bulk Attribute Edit (under Edit)")
print()
print("Output: freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive")
print()
print("=" * 80)
print()

response = input("Continue? (yes/no): ").strip().lower()
if response != 'yes':
    print("Cancelled.")
    sys.exit(0)

print()
print("Starting comprehensive scrape...")
print()

# Run the scraper with comprehensive mode on ALL entries
cmd = [
    sys.executable,
    "scrape_vpbx_tables.py",
    "--output", "freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive",
    "--comprehensive"
]

print(f"Running: {' '.join(cmd)}")
print()

result = subprocess.run(cmd, cwd=r"c:\freepbx-tools")
sys.exit(result.returncode)
