#!/bin/bash
set -euo pipefail

REPO=/var/www/freePBX_Tools
LOG_DIR="$REPO/var/logs/startup"
LOG_FILE="$LOG_DIR/full_start_$(date +%Y%m%d_%H%M%S).log"
POLYCOM_DIR="$REPO/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main"
PROFILE_DIR="$REPO/webscraper/var/chrome-profile"
DISPLAY_NUM=99
VNC_PORT=5900

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo " FULL_START  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

cd "$REPO"

# ── 0. Start persistent virtual display + VNC ─────────────────────────────
echo ""
echo "[0/6] Starting virtual display and VNC..."

pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
pkill -f "x11vnc.*:${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

if command -v Xvfb &>/dev/null; then
    Xvfb ":${DISPLAY_NUM}" -screen 0 1280x900x24 2>/dev/null &
    sleep 1
    DISPLAY=":${DISPLAY_NUM}" openbox 2>/dev/null &
    sleep 0.5
    x11vnc -display ":${DISPLAY_NUM}" -localhost -nopw -forever -bg -quiet 2>/dev/null
    echo "[0/6] Virtual display :${DISPLAY_NUM} and VNC on localhost:${VNC_PORT} ready."
    echo ""
    echo "  When a scrape is triggered, Chrome will open on this display."
    echo "  If login is required, connect via VNC:"
    echo "    ssh -L 5901:127.0.0.1:5900 $(hostname -s)"
    echo "    Then open VNC client → localhost:5901"
    echo ""
else
    echo "[WARN] Xvfb not found — run: sudo apt install -y xvfb x11vnc openbox"
fi

# ── 1. Pull latest code ────────────────────────────────────────────────────
echo ""
echo "[1/6] Pulling latest code..."
if ! git pull --rebase origin main; then
    echo "[WARN] git pull failed — continuing with local code."
fi

# ── 2. Rebuild polycom static dist if source changed ──────────────────────
echo ""
echo "[2/6] Checking polycom build..."
POLYCOM_SRC_HASH=$(find "$POLYCOM_DIR/src" -name "*.ts" -o -name "*.tsx" -o -name "*.css" 2>/dev/null | sort | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1)
POLYCOM_HASH_FILE="$POLYCOM_DIR/.src_hash"

if [ ! -d "$POLYCOM_DIR/dist" ] || [ ! -f "$POLYCOM_HASH_FILE" ] || [ "$POLYCOM_SRC_HASH" != "$(cat $POLYCOM_HASH_FILE)" ]; then
    echo "[2/6] Source changed or dist missing — rebuilding polycom..."
    cd "$POLYCOM_DIR"
    npm ci --silent
    npm run build
    echo "$POLYCOM_SRC_HASH" > "$POLYCOM_HASH_FILE"
    cd "$REPO"
    echo "[2/6] Polycom build complete."
else
    echo "[2/6] Polycom dist is up to date — skipping build."
fi

# ── 3. Stop all services cleanly ──────────────────────────────────────────
echo ""
echo "[3/6] Stopping all services..."
python3 scripts/stop_all_web_apps.py || true

# Kill any stragglers — only the known ports, not every node/uvicorn process
for PORT in 3004 3005 3006 3011 5000 8787 8788; do
    PID=$(lsof -ti tcp:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "  Killing stale process on port $PORT (pid $PID)"
        kill "$PID" 2>/dev/null || true
    fi
done

echo "[3/6] Waiting for ports to clear..."
sleep 4

# ── 4. Reload Apache (picks up any vhost changes) ─────────────────────────
echo ""
echo "[4/6] Reloading Apache..."
systemctl reload apache2 && echo "[4/6] Apache reloaded." || echo "[WARN] Apache reload failed."

# ── 5. Start all services ─────────────────────────────────────────────────
echo ""
echo "[5/6] Starting all services..."
python3 scripts/run_all_web_apps.py \
    --browser none \
    --webscraper-mode combined \
    --extras \
    --readiness-timeout 120

# ── 6. Health check each subdomain ────────────────────────────────────────
echo ""
echo "[6/6] Health checks..."

check_port() {
    local label=$1
    local port=$2
    local path=${3:-/}
    local deadline=$((SECONDS + 20))
    while [ $SECONDS -lt $deadline ]; do
        if curl -sf "http://127.0.0.1:$port$path" -o /dev/null 2>/dev/null; then
            echo "  ✓ $label (port $port)"
            return 0
        fi
        sleep 2
    done
    echo "  ✗ $label (port $port) — not responding after 20s"
    return 1
}

FAILURES=0
check_port "manager-ui"         3004 /dashboard  || FAILURES=$((FAILURES+1))
check_port "ticket-ui"          3005 /           || FAILURES=$((FAILURES+1))
check_port "traceroute"         3006 /           || FAILURES=$((FAILURES+1))
check_port "homelab"            3011 /tracker    || FAILURES=$((FAILURES+1))
check_port "manager-api"        8787 /api/health || FAILURES=$((FAILURES+1))
check_port "ticket-api"         8788 /api/health || FAILURES=$((FAILURES+1))
check_port "polycom (static)"   443  /           2>/dev/null || \
    (ls "$POLYCOM_DIR/dist/index.html" &>/dev/null && echo "  ✓ polycom (static dist exists)") || \
    { echo "  ✗ polycom dist missing"; FAILURES=$((FAILURES+1)); }

echo ""
echo "=========================================="
if [ $FAILURES -eq 0 ]; then
    echo " ALL SERVICES UP  $(date '+%H:%M:%S')"
else
    echo " $FAILURES SERVICE(S) FAILED — check $LOG_FILE"
fi
echo "=========================================="
echo ""
echo "Log saved to: $LOG_FILE"
echo ""
echo "─────────────────────────────────────────────────────────"
echo " To start scraping: trigger a scrape from the ticket UI"
echo " or via: curl -X POST http://127.0.0.1:8788/api/scrape/start"
echo " Chrome will open on the virtual display. If login is"
echo " needed, VNC in:  ssh -L 5901:127.0.0.1:5900 $(hostname -s)"
echo "─────────────────────────────────────────────────────────"
