#!/bin/bash
# Lean service startup (no git pull, no polycom build).
# Called by freepbx-tools.service on boot and by watchdog on crash recovery.
set -euo pipefail

REPO=/var/www/freePBX_Tools
DISPLAY_NUM=99

cd "$REPO"

# ── Load local environment (INGEST_API_KEY, etc.) ─────────────────────────────
if [ -f "$REPO/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$REPO/.env"
    set +a
fi

# ── Virtual display + VNC ─────────────────────────────────────────────────────
echo "[start] Setting up virtual display :${DISPLAY_NUM}..."
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
pkill -f "x11vnc.*:${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

if command -v Xvfb &>/dev/null; then
    Xvfb ":${DISPLAY_NUM}" -screen 0 1280x900x24 2>/dev/null &
    sleep 1
    DISPLAY=":${DISPLAY_NUM}" openbox 2>/dev/null &
    sleep 0.5
    x11vnc -display ":${DISPLAY_NUM}" -rfbport 5900 -nopw -forever -bg -quiet 2>/dev/null || true
    echo "[start] Virtual display :${DISPLAY_NUM} ready."
else
    echo "[WARN] Xvfb not found — Chrome scraping will fail."
fi

# ── Stop dead services and clear ports ───────────────────────────────────────
echo "[start] Stopping existing services..."
python3 scripts/stop_all_web_apps.py 2>/dev/null || true

for PORT in 3004 3005 3006 3011 5000 8787 8788; do
    PID=$(lsof -ti tcp:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "[start] Killing stale process on port $PORT (pid $PID)"
        kill "$PID" 2>/dev/null || true
    fi
done
sleep 3

# ── Ensure Apache is running (start if stopped, reload if already running) ────
if systemctl is-active --quiet apache2; then
    systemctl reload apache2 2>/dev/null && echo "[start] Apache reloaded." || true
else
    systemctl start apache2 2>/dev/null && echo "[start] Apache started." || echo "[WARN] Apache failed to start."
fi

# ── Start all services ────────────────────────────────────────────────────────
echo "[start] Starting all services..."
python3 scripts/run_all_web_apps.py \
    --browser none \
    --webscraper-mode api \
    --extras \
    --readiness-timeout 120

echo "[start] All services started."
