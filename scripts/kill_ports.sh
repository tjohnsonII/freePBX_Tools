#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/webscraper/var/logs"
LOG_FILE="${LOG_DIR}/kill_ports.log"

mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

append_log() {
  printf '%s [kill_ports] %s\n' "$(timestamp)" "$1" >> "$LOG_FILE"
}

collect_pids() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sed '/^$/d'
    return 0
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -lptn 2>/dev/null | awk -v p=":$port" '
      index($0, p) {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART + 4, RLENGTH - 4)
          $0 = substr($0, RSTART + RLENGTH)
        }
      }
    ' | sed '/^$/d'
    return 0
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -lptn 2>/dev/null | awk -v p=":$port" '
      index($4, p) {
        split($7, parts, "/")
        if (parts[1] ~ /^[0-9]+$/) print parts[1]
      }
    ' | sed '/^$/d'
    return 0
  fi

  append_log "No supported port inspection tool found for port $port"
  return 0
}

seen=""
for port in 8787 3004; do
  pids="$(collect_pids "$port" | sort -u)"
  if [ -z "$pids" ]; then
    continue
  fi

  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    case "$seen" in
      *";$pid;"*)
        continue
        ;;
    esac

    append_log "Killing PID $pid on port $port"
    kill -9 "$pid" >/dev/null 2>&1 || true
    seen="${seen};${pid};"
  done <<EOF
$pids
EOF

done

exit 0
