#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/webscraper/var/logs"
LOG_FILE="$LOG_DIR/kill_ports.log"

mkdir -p "$LOG_DIR"

timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

log() {
  echo "$(timestamp) [kill_ports] $*" | tee -a "$LOG_FILE"
}

kill_port_lsof() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      for pid in $pids; do
        log "Killing PID $pid on port $port"
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
    return 0
  fi
  return 1
}

kill_port_ss() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    local pids
    pids="$(ss -lptn 2>/dev/null | awk -v p=":$port" '$0 ~ p && $0 ~ /users:\(\(".*",pid=/ {print}' \
      | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
    if [[ -n "$pids" ]]; then
      for pid in $pids; do
        log "Killing PID $pid on port $port"
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
    return 0
  fi
  return 1
}

kill_port_netstat() {
  local port="$1"
  if command -v netstat >/dev/null 2>&1; then
    # netstat output varies; attempt best-effort parsing
    local pids
    pids="$(netstat -lptn 2>/dev/null | awk -v p=":$port" '$4 ~ p && $6 == "LISTEN" {print $7}' \
      | sed -n 's#/.*##p' | sort -u)"
    if [[ -n "$pids" ]]; then
      for pid in $pids; do
        log "Killing PID $pid on port $port"
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
    return 0
  fi
  return 1
}

log "Checking ports 8787 and 3004..."
for port in 8787 3004; do
  kill_port_lsof "$port" || kill_port_ss "$port" || kill_port_netstat "$port" || true
done
log "Done."
