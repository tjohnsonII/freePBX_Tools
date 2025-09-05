#!/usr/bin/env bash
set -euo pipefail

# Files & defaults
SERVERS_FILE="${1:-ProductionServers.txt}"
LOCAL_FILE="${2:-env_check.sh}"
REMOTE_PATH="${3:-/home/123net/freepbx-tools/env_check.sh}"

# First try as 123net, then fall back to root if needed
PRIMARY_USER="${PRIMARY_USER:-123net}"
FALLBACK_USER="${FALLBACK_USER:-root}"

# Tweak SSH_OPTS if you want stricter host key checking
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)

logdir="push_logs"
mkdir -p "$logdir"

if [[ ! -f "$SERVERS_FILE" ]]; then
  echo "Servers file not found: $SERVERS_FILE" >&2
  exit 1
fi
if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Local file not found: $LOCAL_FILE" >&2
  exit 1
fi

while IFS= read -r host || [[ -n "${host:-}" ]]; do
  # strip comments/whitespace
  host="${host%%#*}"
  host="$(echo -n "$host" | tr -d ' \t\r')"
  [[ -z "$host" ]] && continue

  echo -ne "[$host] creating target dir... "
  if ssh "${SSH_OPTS[@]}" "${PRIMARY_USER}@${host}" "mkdir -p \"$(dirname "$REMOTE_PATH")\"" &>"$logdir/$host.log"; then
    echo "OK (as $PRIMARY_USER)"
  else
    echo "retry as $FALLBACK_USER..."
    if ! ssh "${SSH_OPTS[@]}" "${FALLBACK_USER}@${host}" "mkdir -p \"$(dirname "$REMOTE_PATH")\"" &>>"$logdir/$host.log"; then
      echo "FAILED (see $logdir/$host.log)"
      continue
    fi
  fi

  echo -ne "[$host] copying $LOCAL_FILE → $REMOTE_PATH ... "
  if scp "${SSH_OPTS[@]}" "$LOCAL_FILE" "${PRIMARY_USER}@${host}:$REMOTE_PATH" &>>"$logdir/$host.log"; then
    echo "OK (as $PRIMARY_USER)"
  elif scp "${SSH_OPTS[@]}" "$LOCAL_FILE" "${FALLBACK_USER}@${host}:$REMOTE_PATH" &>>"$logdir/$host.log"; then
    echo "OK (as $FALLBACK_USER)"
  else
    echo "FAILED (see $logdir/$host.log)"
    continue
  fi

  echo -ne "[$host] chmod +x ... "
  if ssh "${SSH_OPTS[@]}" "${PRIMARY_USER}@${host}" "chmod +x \"$REMOTE_PATH\"" &>>"$logdir/$host.log" \
     || ssh "${SSH_OPTS[@]}" "${FALLBACK_USER}@${host}" "chmod +x \"$REMOTE_PATH\"" &>>"$logdir/$host.log"; then
    echo "OK"
  else
    echo "FAILED (see $logdir/$host.log)"
  fi
done < "$SERVERS_FILE"

echo
echo "Done. Logs in $logdir/. Failed hosts (if any) will have details in their .log file."
