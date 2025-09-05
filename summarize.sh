#!/usr/bin/env bash
# Build a single CSV from ./reports/*.conf
set -euo pipefail
REPORT_DIR="${1:-./reports}"

fields=(
  HOST_IP HOST_NAME
  OS_FAMILY ASTERISK_USER FREEPBX_CONF
  AMPDBNAME AMPDBUSER AMPDBPASS MYSQL_SOCKET
  DOT_BIN ASTERISK_BIN FWCONSOLE_BIN
  SELINUX_MODE CALLFLOWS_DIR CALLFLOWS_OWNER
)

# CSV header
(
  IFS=,
  echo "${fields[*]}"
  for f in "$REPORT_DIR"/*.conf; do
    [ -f "$f" ] || continue
    # shellcheck disable=SC1090
    . "$f"
    row=()
    for k in "${fields[@]}"; do
      v="${!k-}"
      # quote safely for CSV
      v="${v//\"/\"\"}"
      row+=("\"$v\"")
    done
    IFS=, ; echo "${row[*]}"
  done
)
