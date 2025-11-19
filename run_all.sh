###############################################################
# VARIABLE MAP LEGEND - run_all.sh
# ------------------------------------------------------------
# LIST:        Path to the host list file (CSV, TSV, or plain IPs)
# SSH_USER:    SSH username to use for remote login (default: 123net)
# PAR:         Number of parallel jobs to run (default: 10)
# DETECT_LOCAL:Path to the detector script to copy to each host
# REPORT_DIR:  Directory to store per-host report files
# SSH_OPTS:    SSH options for batch mode, host key checking, and timeout
#
# Functions:
#   extract_hosts: Extracts unique hostnames/IPs from the LIST file
#   run_one:       Runs the detector on a single host, collects the report
# tmp_report:     Temporary file for pulling remote report
# host_name:      FQDN or hostname of the remote host
# ------------------------------------------------------------
###############################################################
#!/usr/bin/env bash
# Fan out the detector to many PBXs, log in as 123net (no sudo needed)
# This script runs a detector script (detect_freepbx.sh) on a fleet of PBX servers in parallel.
# It copies the detector to each host, runs it remotely, and collects the results into ./reports.
# Exit on error, unset variable, or failed pipeline
set -euo pipefail


# Parse arguments and set defaults
LIST="${1:?Usage: ./run_all.sh ProductionServers.txt [ssh_user] [parallel]}"  # Host list file
SSH_USER="${2:-123net}"   # SSH user (default: 123net)
PAR="${3:-10}"            # Parallelism (default: 10)

# Detector script and report directory
DETECT_LOCAL="${DETECT_LOCAL:-./detect_freepbx.sh}"   # Detector script to copy/run
REPORT_DIR="${REPORT_DIR:-./reports}"                 # Where to store reports
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8"  # SSH options

# Ensure the report directory exists
mkdir -p "$REPORT_DIR"

# Function: extract_hosts
# Extracts unique hostnames/IPs from the LIST file (supports CSV, TSV, or plain IPs)
extract_hosts() {
  awk '
    NR==1 && ($0 ~ /IP|Host/i) {next}  # Skip header if present
    {gsub(/\r/,"")}                   # Remove carriage returns
    # Pick the first field that looks like an IPv4 or hostname
    {
      for(i=1;i<=NF;i++){
        if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ || $i ~ /^[A-Za-z0-9._-]+$/) {print $i; break}
      }
    }
  ' FS='[,\t ]+' "$LIST" | sed '/^$/d' | sort -u
}

# Function: run_one
# Runs the detector script on a single host, collects the report, and saves it locally
run_one() {
  host="$1"
  echo "==> $host"  # Announce which host is being processed

  # Copy the detector script to the remote host's /tmp directory
  scp $SSH_OPTS "$DETECT_LOCAL" "${SSH_USER}@${host}:/tmp/detect_freepbx.sh" >/dev/null

  # Run the detector script remotely (as a login shell for env setup)
  ssh $SSH_OPTS "${SSH_USER}@${host}" 'bash -lc "chmod +x /tmp/detect_freepbx.sh && /tmp/detect_freepbx.sh"' || {
    echo "!! detector failed on $host" >&2
    return 1
  }

  # Pull back the result file from the remote user's home directory
  tmp_report="$(mktemp)"
  scp $SSH_OPTS "${SSH_USER}@${host}:~/freepbx_host_profile.conf" "$tmp_report" >/dev/null

  # Add HOST_IP and HOST_NAME to the top of the report, then save to ./reports/<host>.conf
  host_name="$(ssh $SSH_OPTS "${SSH_USER}@${host}" 'hostname -f 2>/dev/null || hostname')"
  {
    echo "HOST_IP=$host"
    echo "HOST_NAME=$host_name"
    cat "$tmp_report"
  } > "${REPORT_DIR}/${host}.conf"
  rm -f "$tmp_report"
}


# Export functions and variables for use in xargs parallel jobs


# Run the detector in parallel across all hosts
extract_hosts | xargs -n1 -P "$PAR" -I{} bash -lc 'run_one "$@"' _ {}


# Final message
echo "All done. Per-host reports in: $REPORT_DIR"
