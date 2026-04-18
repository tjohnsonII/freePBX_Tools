#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] FULL_START.sh must be run as root. Use: sudo ./FULL_START.sh"
    exit 1
fi

REPO=/var/www/freePBX_Tools
LOG_DIR="$REPO/var/logs/startup"
LOG_FILE="$LOG_DIR/full_start_$(date +%Y%m%d_%H%M%S).log"
POLYCOM_DIR="$REPO/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main"
PROFILE_DIR="$REPO/webscraper/var/chrome-profile"
DISPLAY_NUM=99
VNC_PORT=5900
VNC_BIND_IP="192.168.100.10"
AUTH_MAX_AGE_DAYS=7

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo " FULL_START  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

cd "$REPO"

# ── VPN check ─────────────────────────────────────────────────────────────
echo ""
if ip link show tun0 &>/dev/null && ip addr show tun0 | grep -q "inet "; then
    VPN_IP=$(ip addr show tun0 | grep "inet " | awk '{print $2}')
    echo "[vpn] Connected — tun0 ${VPN_IP}"
else
    echo "[vpn] tun0 not up — starting VPN (config: work)..."
    openvpn3 session-start --config work
    echo "[vpn] Waiting for tun0..."
    for i in $(seq 1 15); do
        if ip link show tun0 &>/dev/null && ip addr show tun0 | grep -q "inet "; then
            VPN_IP=$(ip addr show tun0 | grep "inet " | awk '{print $2}')
            echo "[vpn] Connected — tun0 ${VPN_IP}"
            break
        fi
        sleep 2
    done
    if ! ip link show tun0 &>/dev/null || ! ip addr show tun0 | grep -q "inet "; then
        echo "[ERROR] VPN failed to connect after 30s — aborting."
        exit 1
    fi
fi

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
    x11vnc -display ":${DISPLAY_NUM}" -listen "${VNC_BIND_IP}" -nopw -forever -bg -quiet 2>/dev/null
    echo "[0/6] Virtual display :${DISPLAY_NUM} and VNC on ${VNC_BIND_IP}:${VNC_PORT} ready."
    echo ""
else
    echo "[WARN] Xvfb not found — run: sudo apt install -y xvfb x11vnc openbox"
fi

# ── 0b. Auth session check ─────────────────────────────────────────────────
echo ""
COOKIES_FILE="$PROFILE_DIR/Default/Cookies"
AUTH_NEEDED=false

if [ ! -f "$COOKIES_FILE" ]; then
    echo "[auth] No saved session found."
    AUTH_NEEDED=true
else
    AGE_DAYS=$(( ( $(date +%s) - $(stat -c %Y "$COOKIES_FILE") ) / 86400 ))
    if [ "$AGE_DAYS" -ge "$AUTH_MAX_AGE_DAYS" ]; then
        echo "[auth] Session is ${AGE_DAYS} days old — refreshing."
        AUTH_NEEDED=true
    else
        echo "[auth] Session is ${AGE_DAYS} day(s) old — reusing saved profile."
    fi
fi

if [ "$AUTH_NEEDED" = true ]; then
    echo "[auth] VNC is ready at ${VNC_BIND_IP}:${VNC_PORT} — connect now, then press Enter to launch Chrome."
    read -r -p ""
    export DISPLAY=":${DISPLAY_NUM}"
    mkdir -p "$PROFILE_DIR"
    google-chrome \
        --user-data-dir="$PROFILE_DIR" \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --window-size=1280,900 \
        "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi" &
    CHROME_PID=$!
    echo "[auth] Chrome open — log in via VNC, then close Chrome to save the session."
    wait "$CHROME_PID" 2>/dev/null || true
    echo "[auth] Session saved."
fi

# ── 1. Pull latest code ────────────────────────────────────────────────────
echo ""
echo "[1/6] Pulling latest code..."
git config --global --add safe.directory "$REPO" 2>/dev/null || true
CURRENT_BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "Server")
if ! git pull --rebase origin "$CURRENT_BRANCH"; then
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
    if ! npm ci --silent; then
        echo "[ERROR] polycom npm ci failed — check $LOG_FILE"
        exit 1
    fi
    if ! npm run build; then
        echo "[ERROR] polycom npm build failed — check $LOG_FILE"
        exit 1
    fi
    echo "$POLYCOM_SRC_HASH" > "$POLYCOM_HASH_FILE"
    cd "$REPO"
    echo "[2/6] Polycom build complete."
else
    echo "[2/6] Polycom dist is up to date — skipping build."
fi

# ── 3. Stop all services cleanly ──────────────────────────────────────────
echo ""
echo "[3/6] Stopping all services..."
if ! python3 scripts/stop_all_web_apps.py 2>&1; then
    echo "[WARN] stop_all_web_apps.py reported errors — continuing anyway."
fi

for PORT in 3004 3005 3006 3011 5000 8787 8788; do
    PID=$(lsof -ti tcp:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "  Killing stale process on port $PORT (pid $PID)"
        kill "$PID" 2>/dev/null || true
    fi
done

echo "[3/6] Waiting for ports to clear..."
sleep 4

# ── 4. Reload/start Apache (picks up any vhost changes) ──────────────────
echo ""
echo "[4/6] Starting Apache..."
if systemctl is-active apache2 &>/dev/null; then
    if systemctl reload apache2; then
        echo "[4/6] Apache reloaded."
    else
        echo "[WARN] Apache reload failed — trying restart..."
        systemctl restart apache2 2>&1 || echo "[WARN] Apache restart also failed — check: journalctl -u apache2 -n 20"
    fi
elif apache2ctl configtest 2>/dev/null; then
    systemctl start apache2 && echo "[4/6] Apache started." || echo "[WARN] Apache start failed — services will continue without it."
else
    echo "[WARN] Apache config invalid (missing SSL cert?) — services will start without Apache."
    echo "[WARN] To fix: sudo certbot renew --force-renewal"
fi

# ── 5. Start all services ─────────────────────────────────────────────────
echo ""
echo "[5/6] Starting all services..."
if ! python3 scripts/run_all_web_apps.py \
    --browser none \
    --webscraper-mode combined \
    --extras \
    --readiness-timeout 120; then
    echo "[ERROR] run_all_web_apps.py failed — check $LOG_FILE"
    exit 1
fi

# ── 6. Health check each subdomain ────────────────────────────────────────
echo ""
echo "[6/6] Health checks..."

FAILURES=0
FAILED_SERVICES=()

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
    echo "    → check log: tail -20 $LOG_DIR/../web-app-launcher/logs/$(echo "$label" | tr ' -' '_' | tr '[:upper:]' '[:lower:]').log 2>/dev/null"
    return 1
}

check_port "manager-ui"  3004 / || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("manager-ui:3004"); }
check_port "ticket-ui"   3005 / || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("ticket-ui:3005"); }
check_port "traceroute"  3006 / || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("traceroute:3006"); }
check_port "homelab"     3011 / || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("homelab:3011"); }
check_port "manager-api" 8787 /api/health || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("manager-api:8787"); }
check_port "ticket-api"  8788 /api/health || { FAILURES=$((FAILURES+1)); FAILED_SERVICES+=("ticket-api:8788"); }

# Polycom is a static dist — check file exists, not a port
if [ -f "$POLYCOM_DIR/dist/index.html" ]; then
    echo "  ✓ polycom (static dist exists)"
else
    echo "  ✗ polycom — dist/index.html missing, rebuild needed"
    FAILURES=$((FAILURES+1))
    FAILED_SERVICES+=("polycom:static")
fi

echo ""
echo "=========================================="
if [ $FAILURES -eq 0 ]; then
    echo " ALL SERVICES UP  $(date '+%H:%M:%S')"
else
    echo " $FAILURES SERVICE(S) FAILED  $(date '+%H:%M:%S')"
    echo ""
    for svc in "${FAILED_SERVICES[@]}"; do
        echo "   ✗ $svc"
    done
    echo ""
    echo " Full log: $LOG_FILE"
fi
echo "=========================================="
echo ""
echo "─────────────────────────────────────────────────────────"
echo " Scrape:  curl -X POST http://127.0.0.1:8788/api/scrape/start"
echo " Tickets: https://tickets.123hostedtools.com"
echo " VNC:     ${VNC_BIND_IP}:${VNC_PORT}  (no tunnel needed)"
echo "─────────────────────────────────────────────────────────"
