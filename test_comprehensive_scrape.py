#!/usr/bin/env python3
"""
Test comprehensive scraping on just 2 entries
---------------------------------------------
This script runs the comprehensive VPBX table scraper in test mode, limiting to 2 entries.
It verifies that all major scraping features work and outputs results to a test directory.

====================================
Variable Map Legend (Key Variables)
====================================

cmd (list[str]): Command and arguments to run the scraper subprocess
result (subprocess.CompletedProcess): Result object from running the scraper

"""

import subprocess
import sys


# Print test header and what will be scraped
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


# Build the command to run the scraper in comprehensive mode, limited to 2 entries
cmd = [
    sys.executable,  # Use the current Python interpreter
    "scrape_vpbx_tables.py",
    "--output", "freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive",
    "--max-details", "2",
    "--comprehensive"
]

# Print the command for visibility
print(f"Running: {' '.join(cmd)}")
print()

# Run the scraper subprocess in the specified working directory
result = subprocess.run(cmd, cwd=r"c:\freepbx-tools")

# Exit with the same return code as the scraper
sys.exit(result.returncode)
