#!/bin/sh
set -eu

# traceroute_server_ctl.sh
# Generic supervisor for traceroute_server_update.py-style scripts.
# - Runs the Python script in the background
# - Writes output to a log file
# - Provides real-time log streaming (tail -F)

SCRIPT_PATH=${SCRIPT_PATH:-traceroute_server_update.py}
# Auto-detect a python interpreter unless explicitly provided.
if [ "${PYTHON_BIN:-}" = "" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "ERROR: python interpreter not found (set PYTHON_BIN=python3 or PYTHON_BIN=python)" >&2
    exit 2
  fi
fi
WORKDIR=${WORKDIR:-"$(pwd)"}
WORKDIR_STRIPPED=${WORKDIR%/}
LOG_PATH=${LOG_PATH:-"${WORKDIR_STRIPPED}/traceroute_server.log"}
PIDFILE_PATH=${PIDFILE_PATH:-"${WORKDIR_STRIPPED}/.traceroute_server.pid"}

usage() {
  cat <<'USAGE'
Usage:
  ./traceroute_server_ctl.sh start            Start server in background (nohup)
  ./traceroute_server_ctl.sh stop             Stop background server
  ./traceroute_server_ctl.sh restart          Restart background server
  ./traceroute_server_ctl.sh status           Show running status
  ./traceroute_server_ctl.sh logs [N]         Follow logs (tail -F). Optional N lines (default 200)
  ./traceroute_server_ctl.sh start-follow     Start then follow logs
  ./traceroute_server_ctl.sh foreground       Run in foreground (no nohup)

Environment overrides:
  SCRIPT_PATH=traceroute_server_update.py
  PYTHON_BIN=python3
  WORKDIR=/path/to/dir
  LOG_PATH=/path/to/traceroute_server.log
  PIDFILE_PATH=/path/to/.traceroute_server.pid
USAGE
}

is_running() {
  if [ ! -f "$PIDFILE_PATH" ]; then
    return 1
  fi
  pid="$(cat "$PIDFILE_PATH" 2>/dev/null || echo '')"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_bg() {
  mkdir -p "$WORKDIR"
  cd "$WORKDIR"

  if [ ! -f "$SCRIPT_PATH" ]; then
    echo "ERROR: Script not found: $WORKDIR/$SCRIPT_PATH" >&2
    exit 2
  fi

  if is_running; then
    echo "Already running (pid $(cat "$PIDFILE_PATH"))"
    return 0
  fi

  # Make sure log exists so tail -F works immediately
  touch "$LOG_PATH"

  if command -v nohup >/dev/null 2>&1; then
    nohup "$PYTHON_BIN" -u "$SCRIPT_PATH" >>"$LOG_PATH" 2>&1 &
  else
    # Best-effort fallback (won't survive SIGHUP on logout)
    "$PYTHON_BIN" -u "$SCRIPT_PATH" >>"$LOG_PATH" 2>&1 &
  fi

  echo $! > "$PIDFILE_PATH"
  echo "Started: pid $(cat "$PIDFILE_PATH")"
  echo "Log: $LOG_PATH"
}

stop_bg() {
  if [ ! -f "$PIDFILE_PATH" ]; then
    echo "Not running (no pidfile: $PIDFILE_PATH)"
    return 0
  fi

  pid="$(cat "$PIDFILE_PATH" 2>/dev/null || echo '')"
  if [ -z "$pid" ]; then
    rm -f "$PIDFILE_PATH"
    echo "Not running (empty pidfile removed)"
    return 0
  fi

  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping pid $pid..."
    kill "$pid" 2>/dev/null || true

    # Wait a moment, then hard kill if needed
    i=0
    while [ "$i" -lt 10 ]; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 1
      i=$((i + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
      echo "Still running; sending SIGKILL..."
      kill -9 "$pid" 2>/dev/null || true
    fi

    echo "Stopped."
  else
    echo "Not running (stale pidfile: $pid)"
  fi

  rm -f "$PIDFILE_PATH"
}

status() {
  if is_running; then
    pid="$(cat "$PIDFILE_PATH")"
    echo "RUNNING pid=$pid script=$SCRIPT_PATH log=$LOG_PATH"
    # Optional extra detail if ps is available
    if command -v ps >/dev/null 2>&1; then
      ps -p "$pid" -o pid,ppid,etime,stat,command 2>/dev/null || true
    fi
  else
    echo "STOPPED script=$SCRIPT_PATH log=$LOG_PATH"
    return 1
  fi
}

logs() {
  n="${1:-200}"
  cd "$WORKDIR"
  touch "$LOG_PATH"
  if command -v tail >/dev/null 2>&1; then
    # Some older tails don't support -F; fall back to -f.
    tail -n "$n" -F "$LOG_PATH" 2>/dev/null || tail -n "$n" -f "$LOG_PATH"
  else
    echo "ERROR: 'tail' not found; cannot follow logs." >&2
    exit 2
  fi
}

foreground() {
  cd "$WORKDIR"
  exec "$PYTHON_BIN" -u "$SCRIPT_PATH"
}

cmd="${1:-}"
case "$cmd" in
  start)
    start_bg
    ;;
  stop)
    stop_bg
    ;;
  restart)
    stop_bg || true
    start_bg
    ;;
  status)
    status
    ;;
  logs)
    shift || true
    logs "${1:-200}"
    ;;
  start-follow)
    start_bg
    logs 200
    ;;
  foreground)
    foreground
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
