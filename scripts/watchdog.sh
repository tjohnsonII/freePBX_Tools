#!/bin/bash
# Service health watchdog — called every 5 minutes by freepbx-tools-watchdog.timer.
# Checks known ports and restarts freepbx-tools.service if any are down.
set -euo pipefail

declare -A HEALTH_PATHS=(
    [3004]="/"
    [3005]="/"
    [3006]="/"
    [3011]="/"
    [8787]="/api/health"
    [8788]="/api/health"
)
LABELS=(manager-ui ticket-ui traceroute homelab manager-api ticket-api)
PORTS=(3004 3005 3006 3011 8787 8788)
NEEDS_RESTART=0

for i in "${!PORTS[@]}"; do
    PORT=${PORTS[$i]}
    LABEL=${LABELS[$i]}
    PATH_=${HEALTH_PATHS[$PORT]:-/}
    if ! curl -sf --max-time 3 "http://127.0.0.1:$PORT$PATH_" -o /dev/null 2>/dev/null; then
        echo "[watchdog] FAIL: $LABEL (port $PORT) not responding"
        NEEDS_RESTART=1
    fi
done

if [ "$NEEDS_RESTART" -eq 1 ]; then
    echo "[watchdog] One or more services are down — restarting freepbx-tools.service"
    systemctl restart freepbx-tools.service
else
    echo "[watchdog] All services healthy."
fi
