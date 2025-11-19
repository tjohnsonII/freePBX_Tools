
#!/usr/bin/env bash
# push_env_check.sh
# -----------------
# Deploys the env_check.sh script to a fleet of servers listed in a file.
# Handles directory creation, file transfer, and permission setting, with logging and fallback to root if needed.

set -euo pipefail  # Exit on error, unset vars are errors, fail on pipeline errors

# =========================
# Variable Map & Defaults
# =========================
# SERVERS_FILE: List of target servers (default: ProductionServers.txt)
# LOCAL_FILE:   Path to local env_check.sh to push (default: freepbx-tools/bin/env_check.sh)
# REMOTE_PATH:  Target path on remote server (default: /home/123net/freepbx-tools/bin/env_check.sh)
# PRIMARY_USER: First SSH user to try (default: 123net)
# FALLBACK_USER: Fallback SSH user if primary fails (default: root)
# SSH_OPTS:     SSH options for host key and timeout
# logdir:       Directory for per-host logs

SERVERS_FILE="${1:-ProductionServers.txt}"
LOCAL_FILE="${2:-freepbx-tools/bin/env_check.sh}"
REMOTE_PATH="${3:-/home/123net/freepbx-tools/bin/env_check.sh}"

PRIMARY_USER="${PRIMARY_USER:-123net}"
FALLBACK_USER="${FALLBACK_USER:-root}"

# SSH options: accept new host keys, set connect timeout
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)

# Create log directory for per-host logs
logdir="push_logs"
mkdir -p "$logdir"

# =========================
# Pre-flight Checks
# =========================
# Ensure servers file and local script exist
if [[ ! -f "$SERVERS_FILE" ]]; then
  echo "Servers file not found: $SERVERS_FILE" >&2
  exit 1
fi
if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Local file not found: $LOCAL_FILE" >&2
  exit 1
fi

# =========================
# Main Loop: Deploy to Each Host
# =========================
while IFS= read -r host || [[ -n "${host:-}" ]]; do
  # Remove comments and whitespace from host line
  host="${host%%#*}"
  host="$(echo -n "$host" | tr -d ' \t\r')"
  [[ -z "$host" ]] && continue  # Skip blank lines

  # --- Step 1: Create target directory on remote host ---
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

  # --- Step 2: Copy env_check.sh to remote host ---
  echo -ne "[$host] copying $LOCAL_FILE → $REMOTE_PATH ... "
  if scp "${SSH_OPTS[@]}" "$LOCAL_FILE" "${PRIMARY_USER}@${host}:$REMOTE_PATH" &>>"$logdir/$host.log"; then
    echo "OK (as $PRIMARY_USER)"
  elif scp "${SSH_OPTS[@]}" "$LOCAL_FILE" "${FALLBACK_USER}@${host}:$REMOTE_PATH" &>>"$logdir/$host.log"; then
    echo "OK (as $FALLBACK_USER)"
  else
    echo "FAILED (see $logdir/$host.log)"
    continue
  fi

  # --- Step 3: Set executable permissions on remote script ---
  echo -ne "[$host] chmod +x ... "
  if ssh "${SSH_OPTS[@]}" "${PRIMARY_USER}@${host}" "chmod +x \"$REMOTE_PATH\"" &>>"$logdir/$host.log" \
     || ssh "${SSH_OPTS[@]}" "${FALLBACK_USER}@${host}" "chmod +x \"$REMOTE_PATH\"" &>>"$logdir/$host.log"; then
    echo "OK"
  else
    echo "FAILED (see $logdir/$host.log)"
  fi
done < "$SERVERS_FILE"

# =========================
# Completion Message
# =========================
echo
echo "Done. Logs in $logdir/. Failed hosts (if any) will have details in their .log file."
