#!/bin/bash
# RESTART.sh — interactive menu to restart services, or pass a service name directly
# Usage:
#   sudo ./RESTART.sh            — interactive menu
#   sudo ./RESTART.sh <service>  — non-interactive (for scripting)

REPO=/var/www/freePBX_Tools
DISPLAY_NUM=99
VNC_PORT=5900

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERROR]${RESET} RESTART.sh must be run as root.  Use: sudo ./RESTART.sh"
    exit 1
fi

cd "$REPO"
export DISPLAY=":${DISPLAY_NUM}"

# ── helpers ───────────────────────────────────────────────────────────────────
_port_status() {
    # returns "UP" or "DOWN"
    local PORT=$1
    ss -tln 2>/dev/null | grep -q ":${PORT} " && echo "UP" || echo "DOWN"
}

_status_line() {
    local LABEL=$1 PORT=$2
    if [ -z "$PORT" ]; then
        # process-only service (worker)
        local PROCS
        PROCS=$(pgrep -fc "webscraper.*headless" 2>/dev/null || true)
        if [ "${PROCS:-0}" -gt 0 ]; then
            printf "${GREEN}%-6s${RESET}" "UP"
        else
            printf "${RED}%-6s${RESET}" "DOWN"
        fi
    else
        local STATUS
        STATUS=$(_port_status "$PORT")
        if [ "$STATUS" = "UP" ]; then
            printf "${GREEN}%-6s${RESET}" "UP"
        else
            printf "${RED}%-6s${RESET}" "DOWN"
        fi
    fi
}

_kill_port() {
    local PORT=$1
    local PIDS
    PIDS=$(ss -tlnp 2>/dev/null | awk "/:${PORT} /{print}" | grep -oP 'pid=\K[0-9]+' || true)
    if [ -n "$PIDS" ]; then
        echo "  Killing pids on port $PORT: $PIDS"
        kill $PIDS 2>/dev/null || true
        sleep 1
        PIDS=$(ss -tlnp 2>/dev/null | awk "/:${PORT} /{print}" | grep -oP 'pid=\K[0-9]+' || true)
        [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
    fi
}

_wait_port() {
    local LABEL=$1 PORT=$2 PATH_=${3:-/}
    local DEADLINE=$((SECONDS + 30))
    printf "  Waiting for %s on :%s" "$LABEL" "$PORT"
    while [ $SECONDS -lt $DEADLINE ]; do
        if curl -sf "http://127.0.0.1:${PORT}${PATH_}" -o /dev/null 2>/dev/null; then
            echo -e " ${GREEN}UP${RESET}"
            return 0
        fi
        printf "."
        sleep 1
    done
    echo -e " ${RED}TIMEOUT${RESET}"
    return 1
}

# ── action functions ──────────────────────────────────────────────────────────
do_full_start() {
    echo -e "${BOLD}[RESTART]${RESET} Full stack — running FULL_START.sh"
    exec "$REPO/FULL_START.sh"
}

_kill_service_pid() {
    # Kill a service by looking up its PID in run_state.json (does NOT wipe other services)
    local SERVICE=$1
    local PID
    PID=$(python3 -c "
import json,sys
try:
    d=json.load(open('var/web-app-launcher/run_state.json'))
    print(d.get('services',{}).get('$SERVICE',{}).get('pid',''))
except: pass
" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "  Stopping $SERVICE (pid $PID)"
        kill "$PID" 2>/dev/null || true
        sleep 1
        kill -9 "$PID" 2>/dev/null || true
    fi
}

do_manager_api() {
    echo -e "${BOLD}[RESTART]${RESET} Manager API (port 8787)..."
    _kill_service_pid webscraper_manager_api
    _kill_port 8787
    .venv-web-manager/bin/python -m uvicorn webscraper_manager.api.server:app \
        --host 127.0.0.1 --port 8787 \
        >> /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_manager_api.log 2>&1 &
    _wait_port "manager-api" 8787 /api/health
}

do_manager_ui() {
    echo -e "${BOLD}[RESTART]${RESET} Manager UI (port 3004)..."
    _kill_service_pid manager_ui_frontend
    _kill_port 3004
    npm --prefix manager-ui run start -- --port 3004 --hostname 127.0.0.1 \
        >> /var/www/freePBX_Tools/var/web-app-launcher/logs/manager_ui_frontend.log 2>&1 &
    _wait_port "manager-ui" 3004 /
}

do_ticket_api() {
    echo -e "${BOLD}[RESTART]${RESET} Ticket API (port 8788)..."
    _kill_service_pid webscraper_ticket_api
    _kill_port 8788
    .venv-webscraper/bin/python -m uvicorn webscraper.ticket_api.app:app \
        --host 0.0.0.0 --port 8788 \
        >> /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_ticket_api.log 2>&1 &
    _wait_port "ticket-api" 8788 /api/health
}

do_ticket_ui() {
    echo -e "${BOLD}[RESTART]${RESET} Ticket UI (port 3005)..."
    _kill_service_pid webscraper_ticket_ui
    _kill_port 3005
    npm --prefix webscraper/ticket-ui run start -- --port 3005 --hostname 127.0.0.1 \
        >> /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_ticket_ui.log 2>&1 &
    _wait_port "ticket-ui" 3005 /
}

do_worker() {
    echo -e "${BOLD}[RESTART]${RESET} Scraper Worker..."
    _kill_service_pid webscraper_worker_service
    pkill -f "webscraper.*headless" 2>/dev/null || true
    sleep 0.5
    sudo -H -u tim2 -- \
    env DISPLAY=:20 \
    WEBSCRAPER_BROWSER=chrome \
    WEBSCRAPER_CHROME_PROFILE_DIR="$REPO/webscraper/var/chrome-profile" \
    CHROME_USER_DATA_DIR="$REPO/webscraper/var/chrome-profile" \
    WEBSCRAPER_AUTH_TIMEOUT_SEC=300 \
    HOME=/home/tim2 \
    "$REPO/.venv-webscraper/bin/python" -m webscraper --mode headless \
        >> /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_worker_service.log 2>&1 &
    echo "  Worker started in background (PID $!)."
}

do_apache() {
    echo -e "${BOLD}[RESTART]${RESET} Apache..."
    if systemctl is-active apache2 &>/dev/null; then
        if systemctl reload apache2; then
            echo -e "  ${GREEN}Apache reloaded.${RESET}"
        else
            systemctl restart apache2 && echo -e "  ${GREEN}Apache restarted.${RESET}"
        fi
    else
        systemctl start apache2 && echo -e "  ${GREEN}Apache started.${RESET}"
    fi
}

OVPN_FILE="/home/tim2/1767636174601.ovpn"
OVPN3_PROFILE_DIR="/var/lib/openvpn3/configs"
OVPN3_PROFILE_NAME="work"

do_vpn() {
    echo -e "${BOLD}[RESTART]${RESET} VPN Connect"
    echo ""
    echo -e "  ${DIM}Profile file  : $OVPN_FILE${RESET}"
    echo -e "  ${DIM}Imported name : $OVPN3_PROFILE_NAME${RESET}"
    echo -e "  ${DIM}Profile store : $OVPN3_PROFILE_DIR/${RESET}"
    echo ""

    # Validate the .ovpn file exists
    if [ ! -f "$OVPN_FILE" ]; then
        echo -e "  ${RED}[ERROR] .ovpn file not found: $OVPN_FILE${RESET}"
        echo -e "  ${YELLOW}  → Upload the profile to that path and retry.${RESET}"
        return 1
    fi

    # Show currently imported profiles
    echo -e "  ${DIM}Imported openvpn3 profiles:${RESET}"
    openvpn3 configs-list 2>/dev/null | grep -v "^$\|^---\|^Config" || echo "    (none)"
    echo ""

    # Disconnect any existing session
    echo "  Disconnecting existing sessions..."
    openvpn3 session-manage --disconnect --config "$OVPN3_PROFILE_NAME" 2>/dev/null || true
    openvpn3 session-manage --disconnect --config "$OVPN_FILE" 2>/dev/null || true
    sleep 2

    # Try connecting with the .ovpn file directly
    echo "  Starting session from: $OVPN_FILE"
    if ! openvpn3 session-start --config "$OVPN_FILE" 2>&1; then
        echo -e "  ${YELLOW}Direct file start failed — importing profile and retrying...${RESET}"
        openvpn3 config-import --config "$OVPN_FILE" --name "$OVPN3_PROFILE_NAME" --persistent 2>&1 || true
        echo -e "  ${DIM}Profile saved to: $OVPN3_PROFILE_DIR/${RESET}"
        if ! openvpn3 session-start --config "$OVPN3_PROFILE_NAME" 2>&1; then
            echo -e "  ${RED}[ERROR] VPN session failed to start.${RESET}"
            echo -e "  ${YELLOW}  → Check profile: $OVPN_FILE${RESET}"
            echo -e "  ${YELLOW}  → Check store:   $OVPN3_PROFILE_DIR/${RESET}"
            echo -e "  ${YELLOW}  → Run manually:  openvpn3 session-start --config $OVPN3_PROFILE_NAME${RESET}"
            return 1
        fi
    fi

    echo "  Waiting for tun0..."
    for i in $(seq 1 20); do
        if ip link show tun0 &>/dev/null && ip addr show tun0 | grep -q "inet "; then
            VPN_IP=$(ip addr show tun0 | grep "inet " | awk '{print $2}')
            echo -e "  ${GREEN}VPN connected — tun0 $VPN_IP${RESET}"
            return 0
        fi
        sleep 2
    done
    echo -e "  ${RED}[ERROR] tun0 did not come up after 40s.${RESET}"
    echo -e "  ${YELLOW}  → Check: openvpn3 sessions-list${RESET}"
    echo -e "  ${YELLOW}  → Logs:  journalctl -u openvpn3 -n 30${RESET}"
    return 1
}

do_vnc() {
    echo -e "${BOLD}[RESTART]${RESET} VNC (x11vnc on :${DISPLAY_NUM})..."

    # Kill stale processes cleanly
    pkill -f "x11vnc" 2>/dev/null || true
    pkill -9 -f "xfce4-session|xfwm4|xfdesktop|xfsettingsd|xfce4-panel" 2>/dev/null || true
    pkill -f "dbus-launch" 2>/dev/null || true
    sleep 1

    # Restart Xvfb if not running
    if ! pgrep -f "Xvfb :${DISPLAY_NUM}" &>/dev/null; then
        Xvfb ":${DISPLAY_NUM}" -screen 0 1280x900x24 \
            -ac -noreset +extension RANDR -nolisten tcp 2>/dev/null &
        sleep 1
    fi

    # Start XFCE fresh
    rm -f /tmp/xfce4_root.log
    DISPLAY=":${DISPLAY_NUM}" XAUTHORITY=/root/.Xauthority \
        /usr/bin/dbus-launch --exit-with-session /usr/bin/startxfce4 \
        > /tmp/xfce4_root.log 2>&1 &
    sleep 4

    # Start x11vnc
    x11vnc -display ":${DISPLAY_NUM}" -rfbport "${VNC_PORT}" \
        -nopw -forever -shared -ncache 10 -bg -quiet 2>/dev/null
    sleep 0.5
    echo -e "  ${GREEN}VNC running on 0.0.0.0:${VNC_PORT}${RESET}"
}

do_crd() {
    echo -e "${BOLD}[RESTART]${RESET} Chrome Remote Desktop..."

    # Stop the service first so it releases the display
    systemctl stop chrome-remote-desktop@tim2 2>/dev/null || true
    sleep 2

    # Kill any stale Xorg :20 process left over from a previous CRD session.
    # Without this, CRD can't claim :20 and stays stuck in "starting up".
    STALE_XORG=$(pgrep -f "Xorg :20" || true)
    if [ -n "$STALE_XORG" ]; then
        echo "  Killing stale Xorg :20 (pid $STALE_XORG)..."
        kill $STALE_XORG 2>/dev/null || true
        sleep 1
        kill -9 $STALE_XORG 2>/dev/null || true
    fi

    # Remove stale X lock if present
    rm -f /tmp/.X20-lock

    systemctl start chrome-remote-desktop@tim2
    sleep 3
    if systemctl is-active chrome-remote-desktop@tim2 &>/dev/null; then
        echo -e "  ${GREEN}CRD running — wait ~30 sec for it to appear online in browser.${RESET}"
    else
        echo -e "  ${RED}CRD failed to start — check: journalctl -u chrome-remote-desktop@tim2 -n 20${RESET}"
    fi
}

do_desktop() {
    echo -e "${BOLD}[RESTART]${RESET} Full desktop recovery (VNC + CRD)..."
    do_vnc
    do_crd
    echo -e "  ${GREEN}Done. VNC: 192.168.100.10:5900 — CRD: online in ~2 min${RESET}"
}

# ── non-interactive mode (arg passed) ────────────────────────────────────────
if [ -n "${1:-}" ]; then
    case "$1" in
        all|full-start)  do_full_start ;;
        manager-api)     do_manager_api ;;
        manager-ui)      do_manager_ui ;;
        ticket-api)      do_ticket_api ;;
        ticket-ui)       do_ticket_ui ;;
        worker)          do_worker ;;
        apache)          do_apache ;;
        vpn)             do_vpn ;;
        vnc)             do_vnc ;;
        crd)             do_crd ;;
        desktop)         do_desktop ;;
        *)
            echo -e "${RED}[ERROR]${RESET} Unknown service: $1"
            echo "Valid: all | manager-api | manager-ui | ticket-api | ticket-ui | worker | apache | vpn | vnc | crd | desktop"
            exit 1
            ;;
    esac
    echo -e "${GREEN}[DONE]${RESET}"
    exit 0
fi

# ── interactive menu ──────────────────────────────────────────────────────────
show_menu() {
    clear
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║         123 Hosted Tools — RESTART           ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo -e "  ${DIM}Live status checked at menu open. Re-open to refresh.${RESET}"
    echo ""

    # Pre-check statuses
    local S_MAPI S_MUI S_TAPI S_TUI S_WORK S_APACHE S_VPN S_VNC S_CRD
    S_MAPI=$(_status_line "manager-api"  8787)
    S_MUI=$(_status_line  "manager-ui"   3004)
    S_TAPI=$(_status_line "ticket-api"   8788)
    S_TUI=$(_status_line  "ticket-ui"    3005)
    S_WORK=$(_status_line "worker"       "")
    S_APACHE=$(systemctl is-active apache2 &>/dev/null && printf "${GREEN}%-6s${RESET}" "UP" || printf "${RED}%-6s${RESET}" "DOWN")
    S_VPN=$(ip link show tun0 &>/dev/null && ip addr show tun0 2>/dev/null | grep -q "inet " && printf "${GREEN}%-6s${RESET}" "UP" || printf "${RED}%-6s${RESET}" "DOWN")
    S_VNC=$(pgrep -f "x11vnc" &>/dev/null && printf "${GREEN}%-6s${RESET}" "UP" || printf "${RED}%-6s${RESET}" "DOWN")
    S_CRD=$(systemctl is-active chrome-remote-desktop@tim2 &>/dev/null && printf "${GREEN}%-6s${RESET}" "UP" || printf "${RED}%-6s${RESET}" "DOWN")

    echo -e "  ${BOLD} #   Service              Status  Port${RESET}"
    echo     "  ─────────────────────────────────────────────"
    echo -e "  ${BOLD}1)${RESET}  FULL_START.sh        ${GREEN}(full stack restart)${RESET}"
    echo     "  ─────────────────────────────────────────────"
    printf "  ${BOLD}2)${RESET}  Manager API          %b  8787\n"  "$S_MAPI"
    printf "  ${BOLD}3)${RESET}  Manager UI           %b  3004\n"  "$S_MUI"
    printf "  ${BOLD}4)${RESET}  Ticket API           %b  8788\n"  "$S_TAPI"
    printf "  ${BOLD}5)${RESET}  Ticket UI            %b  3005\n"  "$S_TUI"
    printf "  ${BOLD}6)${RESET}  Scraper Worker       %b  (bg)\n"  "$S_WORK"
    echo     "  ─────────────────────────────────────────────"
    printf "  ${BOLD}7)${RESET}  Apache               %b\n"        "$S_APACHE"
    printf "  ${BOLD}8)${RESET}  VPN (OpenVPN work)   %b\n"        "$S_VPN"
    printf "  ${BOLD}9)${RESET}  VNC (x11vnc :99)     %b\n"        "$S_VNC"
    printf "  ${BOLD}a)${RESET}  Chrome Remote Desktop%b  :20\n"   "$S_CRD"
    printf "  ${BOLD}b)${RESET}  Desktop (VNC + CRD)  %b\n"        "$S_VNC"
    echo     "  ─────────────────────────────────────────────"
    echo -e "  ${BOLD}0)${RESET}  Exit"
    echo ""
    printf "  Choose [0-9/a/b]: "
}

run_choice() {
    local CHOICE=$1
    echo ""
    case "$CHOICE" in
        1) do_full_start ;;
        2) do_manager_api ;;
        3) do_manager_ui ;;
        4) do_ticket_api ;;
        5) do_ticket_ui ;;
        6) do_worker ;;
        7) do_apache ;;
        8) do_vpn ;;
        9) do_vnc ;;
        a|A) do_crd ;;
        b|B) do_desktop ;;
        0) echo "Bye."; exit 0 ;;
        *) echo -e "${YELLOW}  Invalid choice — try again.${RESET}" ;;
    esac
}

while true; do
    show_menu
    read -r CHOICE
    run_choice "$CHOICE"
    echo ""
    printf "  Press Enter to return to menu..."
    read -r
done
