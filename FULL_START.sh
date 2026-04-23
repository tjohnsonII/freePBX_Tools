#!/bin/bash
set -euo pipefail

FORCE_REBUILD=false
for arg in "$@"; do
    case "$arg" in
        --force-rebuild) FORCE_REBUILD=true ;;
        *) echo "[ERROR] Unknown argument: $arg"; exit 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] FULL_START.sh must be run as root. Use: sudo ./FULL_START.sh"
    exit 1
fi

REPO=/var/www/freePBX_Tools
LOG_DIR="$REPO/var/logs/startup"
LOG_FILE="$LOG_DIR/full_start_$(date +%Y%m%d_%H%M%S).log"
POLYCOM_DIR="$REPO/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo " FULL_START  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

cd "$REPO"

# ── Load local environment (INGEST_API_KEY, etc.) ─────────────────────────
if [ -f "$REPO/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$REPO/.env"
    set +a
fi

# ── 1. Pull latest code ────────────────────────────────────────────────────
echo ""
echo "[1/6] Pulling latest code..."
git config --global --add safe.directory "$REPO" 2>/dev/null || true
CURRENT_BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "Server")
if ! git pull --rebase origin "$CURRENT_BRANCH"; then
    echo "[WARN] git pull failed — continuing with local code."
fi

# ── 2. Rebuild front-ends if source changed ────────────────────────────────
echo ""
echo "[2/6] Checking front-end builds..."

DEPLOY_UI_DIR="$REPO/freepbx-deploy-ui"
HOMELAB_DIR="$REPO/HomeLab_NetworkMapping/ccna-lab-tracker"
MANAGER_UI_DIR="$REPO/manager-ui"
TICKET_UI_DIR="$REPO/webscraper/ticket-ui"
TRACEROUTE_DIR="$REPO/traceroute-visualizer-main/traceroute-visualizer-main"

if [ "$FORCE_REBUILD" = true ]; then
    echo "[2/6] --force-rebuild: clearing all build caches and output dirs..."
    rm -f "$DEPLOY_UI_DIR/.src_hash" \
          "$HOMELAB_DIR/.src_hash" \
          "$MANAGER_UI_DIR/.src_hash" \
          "$TICKET_UI_DIR/.src_hash" \
          "$TRACEROUTE_DIR/.src_hash" \
          "$POLYCOM_DIR/.src_hash"
    rm -rf "$DEPLOY_UI_DIR/dist" \
           "$HOMELAB_DIR/.next" \
           "$MANAGER_UI_DIR/.next" \
           "$TICKET_UI_DIR/.next" \
           "$TRACEROUTE_DIR/.next" \
           "$POLYCOM_DIR/dist"
fi

# Set the API base URL for browser-side fetches (LogViewer, ServicePanel, WebscraperStatus etc.)
# manager-api.123hostedtools.com proxies to 8787 — this is how the browser reaches the API.
MANAGER_ENV="$MANAGER_UI_DIR/.env.local"
echo "NEXT_PUBLIC_API_BASE=https://manager-api.123hostedtools.com" > "$MANAGER_ENV"
echo "[2/6] Set NEXT_PUBLIC_API_BASE=https://manager-api.123hostedtools.com"

# Generic rebuild function — works for Next.js and Vite apps
rebuild_app() {
    local label=$1
    local dir=$2
    local dist_dir=${3:-.next}   # third arg is the output dir to check (default .next)
    local src_hash
    src_hash=$(find "$dir" \( -path "$dir/.next" -o -path "$dir/dist" -o -path "$dir/node_modules" \) -prune \
        -o \( -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.js" -o -name "*.mjs" \
           -o -name "next.config.*" -o -name "vite.config.*" \) \
        -print 2>/dev/null | sort | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1)
    local hash_file="$dir/.src_hash"
    if [ ! -d "$dir/$dist_dir" ] || [ ! -f "$hash_file" ] || [ "$src_hash" != "$(cat "$hash_file")" ]; then
        echo "[2/6] $label: source changed or build missing — rebuilding..."
        cd "$dir"
        if ! npm ci --silent; then
            echo "[ERROR] $label npm ci failed — check $LOG_FILE"; exit 1
        fi
        if ! npm run build; then
            echo "[ERROR] $label npm build failed — check $LOG_FILE"; exit 1
        fi
        echo "$src_hash" > "$hash_file"
        # Fix ownership so non-root user can write/delete build artifacts later
        if [ -n "${SUDO_USER:-}" ]; then
            chown -R "$SUDO_USER:$SUDO_USER" "$dir/$dist_dir" "$hash_file" 2>/dev/null || true
        fi
        cd "$REPO"
        echo "[2/6] $label build complete."
    else
        echo "[2/6] $label: up to date — skipping build."
    fi
}

rebuild_app "manager-ui"    "$MANAGER_UI_DIR"  ".next"
rebuild_app "ticket-ui"     "$TICKET_UI_DIR"   ".next"
rebuild_app "homelab"       "$HOMELAB_DIR"     ".next"
rebuild_app "traceroute"    "$TRACEROUTE_DIR"  ".next"
rebuild_app "deploy-ui"     "$DEPLOY_UI_DIR"   "dist"
rebuild_app "polycom"       "$POLYCOM_DIR"     "dist"

# ── 2c. Ensure systemd override for Apache auto-restart is in place ──────
APACHE_OVERRIDE="/etc/systemd/system/apache2.service.d/override.conf"
if [ ! -f "$APACHE_OVERRIDE" ]; then
    mkdir -p "$(dirname "$APACHE_OVERRIDE")"
    printf '[Service]\nRestart=on-failure\nRestartSec=10\n' > "$APACHE_OVERRIDE"
    systemctl daemon-reload
    echo "[2c] Apache systemd Restart=on-failure override installed."
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

# If config is invalid, attempt cert renewal once before giving up
if ! apache2ctl configtest 2>/dev/null; then
    echo "[4/6] Apache config invalid — attempting certbot renewal..."
    if certbot renew --force-renewal -q 2>&1; then
        echo "[4/6] Certs renewed."
    else
        echo "[WARN] certbot renewal failed — Apache may not start."
    fi
fi

if systemctl is-active apache2 &>/dev/null; then
    if systemctl reload apache2; then
        echo "[4/6] Apache reloaded."
    else
        echo "[WARN] Apache reload failed — trying restart..."
        systemctl restart apache2 2>&1 || echo "[WARN] Apache restart also failed — check: journalctl -u apache2 -n 20"
    fi
elif apache2ctl configtest 2>/dev/null; then
    systemctl start apache2 && echo "[4/6] Apache started." || echo "[WARN] Apache start failed — check: journalctl -u apache2 -n 20"
else
    echo "[ERROR] Apache config still invalid after cert renewal attempt."
    echo "[ERROR] Run manually: sudo certbot renew --force-renewal && sudo systemctl start apache2"
    apache2ctl configtest 2>&1 || true
fi

# ── 5. Start all services ─────────────────────────────────────────────────
echo ""
echo "[5/6] Starting all services..."
if ! python3 scripts/run_all_web_apps.py \
    --browser none \
    --webscraper-mode api \
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
echo " Tickets: https://tickets.123hostedtools.com"
echo " API:     http://127.0.0.1:8788/api/health"
echo " Ingest:  POST /api/ingest/* (requires X-Ingest-Key)"
echo "─────────────────────────────────────────────────────────"
