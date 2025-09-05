#!/usr/bin/env bash
# Fan out the detector to many PBXs, log in as 123net (no sudo needed)
set -euo pipefail

LIST="${1:?Usage: ./run_all.sh ProductionServers.txt [ssh_user] [parallel]}"
SSH_USER="${2:-123net}"
PAR="${3:-10}"

DETECT_LOCAL="${DETECT_LOCAL:-./detect_freepbx.sh}"   # your detector script filename
REPORT_DIR="${REPORT_DIR:-./reports}"
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8"

mkdir -p "$REPORT_DIR"

# Extract hosts from the list (works with IP-only, CSV, or TSV; skips header lines)
extract_hosts() {
  awk '
    NR==1 && ($0 ~ /IP|Host/i) {next}
    {gsub(/\r/,"")}
    # pick the first field that looks like an IPv4/hostname
    {
      for(i=1;i<=NF;i++){
        if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ || $i ~ /^[A-Za-z0-9._-]+$/) {print $i; break}
      }
    }
  ' FS='[,\t ]+' "$LIST" | sed '/^$/d' | sort -u
}

run_one() {
  host="$1"
  echo "==> $host"
  # copy detector to /tmp and run it
  scp $SSH_OPTS "$DETECT_LOCAL" "${SSH_USER}@${host}:/tmp/detect_freepbx.sh" >/dev/null
  ssh $SSH_OPTS "${SSH_USER}@${host}" 'bash -lc "chmod +x /tmp/detect_freepbx.sh && /tmp/detect_freepbx.sh"' || {
    echo "!! detector failed on $host" >&2
    return 1
  }
  # pull back the result saved in ~ of the remote user
  tmp_report="$(mktemp)"
  scp $SSH_OPTS "${SSH_USER}@${host}:~/freepbx_host_profile.conf" "$tmp_report" >/dev/null

  # add HOST_IP/HOST_NAME to the top and write into ./reports/<host>.conf
  host_name="$(ssh $SSH_OPTS "${SSH_USER}@${host}" 'hostname -f 2>/dev/null || hostname')"
  {
    echo "HOST_IP=$host"
    echo "HOST_NAME=$host_name"
    cat "$tmp_report"
  } > "${REPORT_DIR}/${host}.conf"
  rm -f "$tmp_report"
}

export -f run_one
export LIST SSH_USER DETECT_LOCAL REPORT_DIR SSH_OPTS

extract_hosts | xargs -n1 -P "$PAR" -I{} bash -lc 'run_one "$@"' _ {}

echo "All done. Per-host reports in: $REPORT_DIR"
