#!/bin/bash
# Run env_check.sh on all IPs from server_ips.txt
# Copies env_check.sh to /tmp on each server, runs it, and saves output locally.

IP_LIST="server_ips.txt"
SCRIPT="env_check.sh"
REMOTE_PATH="/home/123net/env_check.sh"
USER="root"  # Change if needed

while read -r ip; do
  echo "Processing $ip..."
  # Copy the script
  scp "$SCRIPT" "$USER@$ip:$REMOTE_PATH"
  # Run the script and save output
  ssh "$USER@$ip" "bash $REMOTE_PATH" > "env_check_${ip}.txt"
done < "$IP_LIST"