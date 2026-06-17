#!/bin/bash
# Apache Monitor — real-time status, log streaming, and controls.
# Usage:  sudo ./scripts/apache_monitor.sh

RED='\033[0;31m';    GREEN='\033[0;32m';  YELLOW='\033[1;33m'
CYAN='\033[0;36m';   BOLD='\033[1m';      DIM='\033[2m';  RESET='\033[0m'
BLUE='\033[0;34m';   WHITE='\033[1;37m'

ERROR_LOG="/var/log/apache2/error.log"
ACCESS_LOG="/var/log/apache2/access.log"
TAIL_LINES=18

# ── Helpers ───────────────────────────────────────────────────────────────────

apache_state()    { systemctl is-active apache2 2>/dev/null || echo "inactive"; }
apache_pid()      { systemctl show apache2 -p MainPID --value 2>/dev/null | grep -v '^0$' || echo "—"; }
apache_since()    { systemctl show apache2 -p ActiveEnterTimestamp --value 2>/dev/null | awk '{print $2,$3}'; }
active_conns()    { ss -tn 'sport = :80 or sport = :443' 2>/dev/null | tail -n +2 | wc -l; }
vhost_count()     { apachectl -S 2>/dev/null | grep -c "namevhost" 2>/dev/null || echo "?"; }
error_log_size()  { wc -l < "$ERROR_LOG" 2>/dev/null || echo "?"; }

colorize_log_line() {
    local line="$1"
    if   echo "$line" | grep -qiE "SIGTERM|shutting down|caught SIG"; then echo -e "${RED}${BOLD}${line}${RESET}"
    elif echo "$line" | grep -qiE "\[error\]|\[crit\]|\[alert\]|\[emerg\]";  then echo -e "${RED}${line}${RESET}"
    elif echo "$line" | grep -qiE "\[warn\]";                                  then echo -e "${YELLOW}${line}${RESET}"
    elif echo "$line" | grep -qiE "resuming normal|configured -- resuming";    then echo -e "${GREEN}${line}${RESET}"
    elif echo "$line" | grep -qiE "\[notice\]";                                then echo -e "${CYAN}${line}${RESET}"
    else echo -e "${DIM}${line}${RESET}"
    fi
}

# ── Status header ─────────────────────────────────────────────────────────────

print_header() {
    local state pid since conns vhosts w
    state=$(apache_state)
    pid=$(apache_pid)
    since=$(apache_since)
    conns=$(active_conns)
    vhosts=$(vhost_count)
    w=66

    printf "\033[H\033[2J"   # clear screen, cursor home
    echo -e "${CYAN}${BOLD}╔$(printf '═%.0s' $(seq 1 $w))╗${RESET}"
    printf "${CYAN}${BOLD}║${RESET}  %-${w}s${CYAN}${BOLD}║${RESET}\n" \
        "Apache Monitor — $(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "${CYAN}${BOLD}╠$(printf '═%.0s' $(seq 1 $w))╣${RESET}"

    if [[ "$state" == "active" ]]; then
        printf "${CYAN}║${RESET}  Status   ${GREEN}${BOLD}● RUNNING${RESET}%-$((w-18))s${CYAN}║${RESET}\n" ""
    else
        printf "${CYAN}║${RESET}  Status   ${RED}${BOLD}● DOWN (%-8s)${RESET}%-$((w-26))s${CYAN}║${RESET}\n" "$state" ""
    fi

    printf "${CYAN}║${RESET}  PID      %-${w}s${CYAN}║${RESET}\n" "${pid}"
    printf "${CYAN}║${RESET}  Up since  %-${w}s${CYAN}║${RESET}\n" "${since:-—}"
    printf "${CYAN}║${RESET}  Conns     %-${w}s${CYAN}║${RESET}\n" "${conns} active"
    printf "${CYAN}║${RESET}  VHosts    %-${w}s${CYAN}║${RESET}\n" "${vhosts} configured"
    printf "${CYAN}║${RESET}  Error log %-${w}s${CYAN}║${RESET}\n" "${ERROR_LOG} ($(error_log_size) lines)"

    echo -e "${CYAN}╠$(printf '═%.0s' $(seq 1 $w))╣${RESET}"
    printf "${CYAN}║${RESET}  ${BOLD}%-${w}s${CYAN}║${RESET}\n" \
        "s=start  r=restart  R=reload  x=stop  c=configtest"
    printf "${CYAN}║${RESET}  ${BOLD}%-${w}s${CYAN}║${RESET}\n" \
        "l=live logs  a=access log  v=vhosts  w=who's killing apache  q=quit"
    echo -e "${CYAN}╚$(printf '═%.0s' $(seq 1 $w))╝${RESET}"
    echo ""
}

print_recent_log() {
    echo -e "${YELLOW}${BOLD}── Last ${TAIL_LINES} error log lines ──────────────────────────────────────${RESET}"
    tail -n "$TAIL_LINES" "$ERROR_LOG" 2>/dev/null | while IFS= read -r line; do
        colorize_log_line "$line"
    done
    echo ""
}

# ── Controls ──────────────────────────────────────────────────────────────────

do_start() {
    echo -e "${CYAN}Starting Apache...${RESET}"
    sudo systemctl start apache2 \
        && echo -e "${GREEN}Started.${RESET}" \
        || echo -e "${RED}Failed — check: sudo journalctl -u apache2 -n 20${RESET}"
    sleep 2
}

do_stop() {
    echo -e "${YELLOW}Stopping Apache...${RESET}"
    read -rp "  Confirm stop? (y/N): " yn
    [[ "${yn,,}" == "y" ]] || { echo "Aborted."; sleep 1; return; }
    sudo systemctl stop apache2 \
        && echo -e "${YELLOW}Stopped.${RESET}" \
        || echo -e "${RED}Failed.${RESET}"
    sleep 2
}

do_restart() {
    echo -e "${CYAN}Restarting Apache...${RESET}"
    sudo systemctl restart apache2 \
        && echo -e "${GREEN}Restarted.${RESET}" \
        || echo -e "${RED}Failed — check: sudo journalctl -u apache2 -n 20${RESET}"
    sleep 2
}

do_reload() {
    echo -e "${CYAN}Reloading Apache config...${RESET}"
    sudo systemctl reload apache2 \
        && echo -e "${GREEN}Reloaded.${RESET}" \
        || { echo -e "${RED}Reload failed — running configtest:${RESET}"; sudo apachectl configtest 2>&1; }
    sleep 2
}

do_configtest() {
    echo -e "${CYAN}${BOLD}── Config Test ───────────────────────────────────────────────────${RESET}"
    sudo apachectl configtest 2>&1
    echo -e "\n${DIM}Press ENTER to continue...${RESET}"; read -r
}

do_live_logs() {
    echo -e "${CYAN}Streaming error log — Ctrl+C to return${RESET}\n"
    sudo tail -f "$ERROR_LOG" 2>/dev/null | while IFS= read -r line; do
        colorize_log_line "$line"
    done
}

do_access_log() {
    echo -e "${CYAN}Streaming access log — Ctrl+C to return${RESET}\n"
    sudo tail -f "$ACCESS_LOG" 2>/dev/null
}

do_vhosts() {
    echo -e "${CYAN}${BOLD}── Active VHosts ─────────────────────────────────────────────────${RESET}"
    sudo apachectl -S 2>&1
    echo -e "\n${DIM}Press ENTER to continue...${RESET}"; read -r
}

do_who_kills_apache() {
    echo -e "${CYAN}${BOLD}── Hunting what sends SIGTERM to Apache ──────────────────────────${RESET}"
    echo -e "${DIM}Watching for SIGTERM in error log for 30s...${RESET}\n"

    # Check systemd timers that might trigger restarts
    echo -e "${YELLOW}Systemd timers active:${RESET}"
    systemctl list-timers --no-pager 2>/dev/null | grep -E "freepbx|watchdog|apache|restart" || echo "  (none matching)"
    echo ""

    # Check anything that sends SIGTERM to apache pid
    local pid
    pid=$(apache_pid)
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
        echo -e "${YELLOW}Watching kill/signal calls to Apache PID ${pid} for 30s...${RESET}"
        echo -e "${DIM}(requires strace — may not be available)${RESET}"
        timeout 30 sudo strace -e trace=kill -p "$pid" 2>&1 | head -20 || \
            echo "  strace not available or no signals captured"
    fi

    echo ""
    echo -e "${YELLOW}Recent freepbx-tools service events:${RESET}"
    sudo journalctl -u freepbx-tools.service --no-pager -n 15 2>/dev/null
    echo ""
    echo -e "${YELLOW}Recent watchdog timer events:${RESET}"
    sudo journalctl -u freepbx-tools-watchdog.timer --no-pager -n 10 2>/dev/null || \
        sudo journalctl -u "*watchdog*" --no-pager -n 10 2>/dev/null || \
        echo "  (no watchdog timer logs found)"

    echo -e "\n${DIM}Press ENTER to continue...${RESET}"; read -r
}

# ── Main loop ─────────────────────────────────────────────────────────────────

trap 'echo -e "\n${DIM}Exiting.${RESET}"; exit 0' INT TERM

if [[ "$(id -u)" -ne 0 ]] && ! sudo -n true 2>/dev/null; then
    echo -e "${YELLOW}Warning: some actions require sudo. You may be prompted for a password.${RESET}"
    sleep 1
fi

while true; do
    print_header
    print_recent_log

    echo -ne "${CYAN}Command (auto-refresh 10s): ${RESET}"
    if read -t 10 -r cmd 2>/dev/null; then
        case "$cmd" in
            s|S) do_start ;;
            x|X) do_stop ;;
            r)   do_restart ;;
            R)   do_reload ;;
            c|C) do_configtest ;;
            l|L) do_live_logs ;;
            a|A) do_access_log ;;
            v|V) do_vhosts ;;
            w|W) do_who_kills_apache ;;
            q|Q) echo -e "${DIM}Bye.${RESET}"; exit 0 ;;
        esac
    fi
done
