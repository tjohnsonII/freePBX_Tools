
#!/usr/bin/env bash
# summarize.sh - Aggregate .conf reports into a single CSV summary
# ---------------------------------------------------------------
# This script scans a directory of .conf files (default: ./reports),
# sources each file, and outputs a CSV with selected fields for each host.
# Intended for summarizing FreePBX/Asterisk fleet diagnostics.
#
# ====================================
# Variable Map Legend (Key Variables)
# ====================================
#
# REPORT_DIR (string): Directory containing .conf report files (default: ./reports or $1)
# fields (array): List of variable names to extract from each .conf file
# f (string): Path to each .conf file in the loop
# k (string): Name of each field/variable to extract
# v (string): Value of the variable $k from the sourced .conf file
# row (array): Array of quoted values for the current CSV row
#

# Exit on error, unset variable, or failed pipeline
set -euo pipefail

# Directory containing .conf report files (default: ./reports or $1)
REPORT_DIR="${1:-./reports}"

# List of fields (variables) to extract from each .conf file
fields=(
  HOST_IP HOST_NAME
  OS_FAMILY ASTERISK_USER FREEPBX_CONF
  AMPDBNAME AMPDBUSER AMPDBPASS MYSQL_SOCKET
  DOT_BIN ASTERISK_BIN FWCONSOLE_BIN
  SELINUX_MODE CALLFLOWS_DIR CALLFLOWS_OWNER
)

# Output CSV: print header, then one row per .conf file
(
  # Set comma as field separator for CSV
  IFS=,
  # Print CSV header row
  echo "${fields[*]}"
  # Loop over all .conf files in the report directory
  for f in "$REPORT_DIR"/*.conf; do
    [ -f "$f" ] || continue  # Skip if not a file
    # Source the .conf file to load its variables (safe in this context)
    # shellcheck disable=SC1090
    . "$f"
    row=()
    # For each field, extract its value (or empty if unset)
    for k in "${fields[@]}"; do
      v="${!k-}"
      # Escape double quotes for CSV safety
      v="${v//\"/\"\"}"
      row+=("\"$v\"")
    done
    # Print the row as a CSV line
    IFS=, ; echo "${row[*]}"
  done
)
