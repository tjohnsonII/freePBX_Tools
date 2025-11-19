"""
VARIABLE MAP LEGEND - run_comprehensive_scrape.py
-------------------------------------------------
subprocess: Python module for running external commands
sys: Python module for system-specific parameters and functions

response: (str) User input to confirm whether to proceed
cmd: (list) Command to run the comprehensive scrape (Python executable, script, and arguments)
result: (CompletedProcess) Result object from subprocess.run, contains return code

Script prints banners, warnings, and progress to the console.
-------------------------------------------------
"""

#!/usr/bin/env python3
"""
Run comprehensive scraping on ALL 556 entries
WARNING: This will take 2-3 hours to complete

This script launches a full scrape of all VPBX entries using scrape_vpbx_tables.py
in comprehensive mode. It is intended for large-scale data collection and will
scrape thousands of pages, including all detail and sub-pages for each entry.
"""


# Import required modules
import subprocess
import sys


# Print banner and warnings
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


# Prompt user for confirmation before starting the long-running scrape
response = input("Continue? (yes/no): ").strip().lower()
if response != 'yes':
    print("Cancelled.")
    sys.exit(0)


# Announce start
print()
print("Starting comprehensive scrape...")
print()


# Build the command to run the comprehensive scrape
cmd = [
    sys.executable,  # Use the current Python interpreter
    "scrape_vpbx_tables.py",  # Script to run
    "--output", "freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive",  # Output directory
    "--comprehensive"  # Enable comprehensive mode
]


# Show the command being run
print(f"Running: {' '.join(cmd)}")
print()


# Run the command in the specified working directory
result = subprocess.run(cmd, cwd=r"c:\freepbx-tools")

# Exit with the same return code as the subprocess
sys.exit(result.returncode)
