#!/usr/bin/env python3
"""
Apache2 Terminal Monitor
Pure curses — no external dependencies.
Run with: sudo python3 scripts/apache_monitor.py
Keys: [S]tart  [X]Stop  [R]estart  [K]ill  [C]onfig test  [Q]uit  [Tab] cycle log (Error/Access/Auth Failures)
"""

import curses
import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

PID_FILE        = Path("/var/run/apache2/apache2.pid")
ERROR_LOG       = Path("/var/log/apache2/error.log")
ACCESS_LOG      = Path("/var/log/apache2/other_vhosts_access.log")
TICKET_API_LOG  = Path("/var/log/apache2/ticket-api-access.log")
REFRESH_S  = 2
LOG_LINES  = 30

# ── colour pair IDs ────────────────────────────────────────────────────────────
C_NORMAL  = 0
C_GREEN   = 1
C_RED     = 2
C_YELLOW  = 3
C_CYAN    = 4
C_HEADER  = 5
C_KEY     = 6
C_DIM     = 7


# ── status probe ───────────────────────────────────────────────────────────────

def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)


def get_status():
    """Return dict with all live Apache info."""
    code, out, _ = _run(["systemctl", "is-active", "apache2"])
    systemd_active = out.strip()                          # "active" / "inactive" / "failed"

    pid = None
    pid_alive = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            pid_alive = Path(f"/proc/{pid}").exists()
        except Exception:
            pass

    # Determine state
    if systemd_active == "active" and pid_alive:
        state = "UP"
    elif systemd_active == "active" and not pid_alive:
        state = "STALE"                                   # systemd thinks up, process gone
    elif PID_FILE.exists() and not pid_alive:
        state = "STALE"                                   # leftover pid file
    elif systemd_active == "failed":
        state = "FAILED"
    else:
        state = "DOWN"

    # Uptime from systemctl
    uptime_str = "—"
    _, sc_out, _ = _run(["systemctl", "show", "apache2",
                          "--property=ActiveEnterTimestamp"])
    for line in sc_out.splitlines():
        if line.startswith("ActiveEnterTimestamp=") and "=" in line:
            ts_str = line.split("=", 1)[1].strip()
            if ts_str:
                try:
                    fmt = "%a %Y-%m-%d %H:%M:%S %Z"
                    ts = datetime.strptime(ts_str, fmt)
                    secs = int((datetime.utcnow() - ts).total_seconds())
                    if secs >= 3600:
                        uptime_str = f"{secs//3600}h {(secs%3600)//60}m"
                    elif secs >= 60:
                        uptime_str = f"{secs//60}m {secs%60}s"
                    else:
                        uptime_str = f"{secs}s"
                except Exception:
                    pass

    # Active HTTPS connections
    conns = 0
    _, ss_out, _ = _run(["ss", "-tn", "state", "established"])
    for line in ss_out.splitlines():
        if ":443" in line or ":80" in line:
            conns += 1

    # Config test
    cfg_ok = None
    _, _, cfg_err = _run(["apachectl", "configtest"])
    if "Syntax OK" in cfg_err:
        cfg_ok = True
    elif cfg_err.strip():
        cfg_ok = False

    return {
        "state":        state,
        "pid":          pid,
        "pid_alive":    pid_alive,
        "uptime":       uptime_str,
        "conns":        conns,
        "cfg_ok":       cfg_ok,
        "auth_failures": count_recent_auth_failures(),
        "ts":           datetime.now().strftime("%H:%M:%S"),
    }


def tail_log(path: Path, n: int):
    if not path.exists():
        return [f"(log not found: {path})"]
    try:
        _, out, _ = _run(["tail", f"-n{n}", str(path)])
        lines = out.splitlines()
        return lines if lines else ["(empty log)"]
    except Exception as e:
        return [f"(error reading log: {e})"]


def get_auth_failures(n: int = 200):
    """Return recent lines from ticket-api-access.log that are 403 on /api/ingest/."""
    if not TICKET_API_LOG.exists():
        return [f"(log not found: {TICKET_API_LOG})"]
    try:
        _, out, _ = _run(["tail", f"-n{n}", str(TICKET_API_LOG)])
        hits = [l for l in out.splitlines() if '" 403 ' in l and "/api/ingest/" in l]
        if not hits:
            return ["(no auth failures in last 200 requests)"]
        return hits
    except Exception as e:
        return [f"(error: {e})"]


def count_recent_auth_failures(window: int = 500) -> int:
    """Count 403s on /api/ingest/ in the last `window` lines of the ticket-api log."""
    if not TICKET_API_LOG.exists():
        return 0
    try:
        _, out, _ = _run(["tail", f"-n{window}", str(TICKET_API_LOG)])
        return sum(1 for l in out.splitlines() if '" 403 ' in l and "/api/ingest/" in l)
    except Exception:
        return 0


# ── sudo commands ──────────────────────────────────────────────────────────────

def sudo_cmd(args, status_cb):
    """Run a sudo command in a background thread; call status_cb(msg) with updates."""
    def _run_it():
        status_cb(f"Running: sudo {' '.join(args)} …")
        code, out, err = _run(["sudo"] + args, timeout=30)
        if code == 0:
            status_cb(f"OK: {' '.join(args)}")
        else:
            msg = (err or out).strip().replace("\n", " ")[:120]
            status_cb(f"ERROR ({code}): {msg}")
    threading.Thread(target=_run_it, daemon=True).start()


def kill_apache(status_cb):
    """SIGKILL the main apache2 process."""
    def _run_it():
        if not PID_FILE.exists():
            status_cb("No PID file found.")
            return
        try:
            pid = int(PID_FILE.read_text().strip())
        except Exception:
            status_cb("Could not read PID file.")
            return
        status_cb(f"Sending SIGKILL to PID {pid} …")
        code, _, err = _run(["sudo", "kill", "-9", str(pid)], timeout=10)
        if code == 0:
            status_cb(f"SIGKILL sent to {pid}.")
        else:
            status_cb(f"kill failed: {err.strip()[:80]}")
    threading.Thread(target=_run_it, daemon=True).start()


# ── drawing helpers ────────────────────────────────────────────────────────────

def safe_addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    max_len = w - x - 1
    if max_len <= 0:
        return
    try:
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def draw_hline(win, y, attr=0):
    h, w = win.getmaxyx()
    if 0 <= y < h:
        try:
            win.hline(y, 0, curses.ACS_HLINE, w - 1, attr)
        except curses.error:
            pass


def state_colour(state):
    return {
        "UP":     curses.color_pair(C_GREEN)  | curses.A_BOLD,
        "DOWN":   curses.color_pair(C_RED)    | curses.A_BOLD,
        "STALE":  curses.color_pair(C_YELLOW) | curses.A_BOLD,
        "FAILED": curses.color_pair(C_RED)    | curses.A_BOLD,
    }.get(state, curses.A_BOLD)


LOG_SOURCES = [
    ("Error Log",        ERROR_LOG),
    ("Access Log",       ACCESS_LOG),
    ("Auth Failures",    None),       # synthetic — filtered from ticket-api-access.log
]


# ── main TUI ──────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_GREEN,  curses.COLOR_GREEN,   -1)
    curses.init_pair(C_RED,    curses.COLOR_RED,     -1)
    curses.init_pair(C_YELLOW, curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_CYAN,   curses.COLOR_CYAN,    -1)
    curses.init_pair(C_HEADER, curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(C_KEY,    curses.COLOR_CYAN,    -1)
    curses.init_pair(C_DIM,    curses.COLOR_WHITE,   -1)

    status    = get_status()
    cmd_msg   = ""
    log_idx   = 0                        # which log source is shown
    last_refresh = time.monotonic()

    while True:
        now = time.monotonic()
        if now - last_refresh >= REFRESH_S:
            status = get_status()
            last_refresh = now

        h, w = stdscr.getmaxyx()
        stdscr.erase()

        # ── Row 0: title bar ──────────────────────────────────────────────────
        title = " APACHE2 MONITOR "
        stdscr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
        stdscr.hline(0, 0, " ", w)
        safe_addstr(stdscr, 0, 0, title, curses.color_pair(C_HEADER) | curses.A_BOLD)
        ts_str = f" {status['ts']} "
        safe_addstr(stdscr, 0, w - len(ts_str) - 1, ts_str,
                    curses.color_pair(C_HEADER))
        stdscr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

        # ── Row 1: blank ──────────────────────────────────────────────────────

        # ── Row 2: status line ────────────────────────────────────────────────
        state = status["state"]
        icon  = {"UP": "●", "DOWN": "○", "STALE": "◑", "FAILED": "✗"}.get(state, "?")
        safe_addstr(stdscr, 2, 2, "Status: ", curses.color_pair(C_DIM))
        safe_addstr(stdscr, 2, 10, f"{icon} {state}",  state_colour(state))

        pid_str = f"PID: {status['pid'] or '—'}"
        safe_addstr(stdscr, 2, 22, pid_str, curses.A_NORMAL)

        uptime_str = f"Uptime: {status['uptime']}"
        safe_addstr(stdscr, 2, 36, uptime_str, curses.A_NORMAL)

        conns_str = f"Connections: {status['conns']}"
        safe_addstr(stdscr, 2, 56, conns_str, curses.A_NORMAL)

        # auth failures on same row
        af = status["auth_failures"]
        af_attr = (curses.color_pair(C_RED) | curses.A_BOLD) if af > 0 else curses.color_pair(C_DIM)
        af_str = f"Bad API Key (403): {af}"
        safe_addstr(stdscr, 2, 76, af_str, af_attr)

        # ── Row 3: config test ────────────────────────────────────────────────
        cfg = status["cfg_ok"]
        cfg_label = "Config: "
        safe_addstr(stdscr, 3, 2, cfg_label, curses.color_pair(C_DIM))
        if cfg is True:
            safe_addstr(stdscr, 3, 10, "✓ Syntax OK",
                        curses.color_pair(C_GREEN))
        elif cfg is False:
            safe_addstr(stdscr, 3, 10, "✗ Syntax Error",
                        curses.color_pair(C_RED) | curses.A_BOLD)
        else:
            safe_addstr(stdscr, 3, 10, "— not checked", curses.color_pair(C_DIM))

        refresh_str = f"Auto-refresh: {REFRESH_S}s"
        safe_addstr(stdscr, 3, 36, refresh_str, curses.color_pair(C_DIM))

        # ── Row 4: separator ──────────────────────────────────────────────────
        draw_hline(stdscr, 4)

        # ── Row 5: key bar ────────────────────────────────────────────────────
        keys = [
            ("[S]", "tart"),
            ("[X]", "Stop"),
            ("[R]", "estart"),
            ("[K]", "ill"),
            ("[C]", "onfig test"),
            ("[Tab]", "cycle log"),
            ("[Q]", "uit"),
        ]
        col = 2
        for k, label in keys:
            safe_addstr(stdscr, 5, col, k,
                        curses.color_pair(C_KEY) | curses.A_BOLD)
            col += len(k)
            safe_addstr(stdscr, 5, col, label + "  ", curses.A_DIM)
            col += len(label) + 2

        # ── Row 6: command feedback ───────────────────────────────────────────
        if cmd_msg:
            attr = curses.color_pair(C_RED) if "ERROR" in cmd_msg else curses.color_pair(C_GREEN)
            safe_addstr(stdscr, 6, 2, cmd_msg[:w - 4], attr)

        # ── Row 7: separator ──────────────────────────────────────────────────
        draw_hline(stdscr, 7)

        # ── Row 8: log header ─────────────────────────────────────────────────
        log_name, log_path = LOG_SOURCES[log_idx % len(LOG_SOURCES)]
        if log_path is None:
            header = f" {log_name}: {TICKET_API_LOG} (403 /api/ingest/* only) "
        else:
            header = f" {log_name}: {log_path} "
        safe_addstr(stdscr, 8, 2, header,
                    curses.color_pair(C_CYAN) | curses.A_BOLD)

        # ── Rows 9…h-1: log lines ─────────────────────────────────────────────
        log_area = max(1, h - 9)
        if log_path is None:
            lines = get_auth_failures(max(log_area * 4, 200))
        else:
            lines = tail_log(log_path, log_area)

        for i, line in enumerate(lines[-(log_area):]):
            row = 9 + i
            if row >= h - 1:
                break
            if log_path is None:
                # auth failure tab — always red, extract IP + path for clarity
                safe_addstr(stdscr, row, 0, line,
                            curses.color_pair(C_RED) | curses.A_BOLD)
            elif "error" in line.lower() or "crit" in line.lower():
                attr = curses.color_pair(C_RED)
                safe_addstr(stdscr, row, 0, line, attr)
            elif "warn" in line.lower():
                attr = curses.color_pair(C_YELLOW)
                safe_addstr(stdscr, row, 0, line, attr)
            else:
                safe_addstr(stdscr, row, 0, line,
                            curses.color_pair(C_DIM) | curses.A_DIM)

        stdscr.refresh()

        # ── Input ─────────────────────────────────────────────────────────────
        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1

        if ch in (ord("q"), ord("Q")):
            break
        elif ch in (ord("s"), ord("S")):
            sudo_cmd(["systemctl", "start", "apache2"],
                     lambda m: _set_msg(m))
        elif ch in (ord("x"), ord("X")):
            sudo_cmd(["systemctl", "stop", "apache2"],
                     lambda m: _set_msg(m))
        elif ch in (ord("r"), ord("R")):
            sudo_cmd(["systemctl", "restart", "apache2"],
                     lambda m: _set_msg(m))
        elif ch in (ord("k"), ord("K")):
            kill_apache(lambda m: _set_msg(m))
        elif ch in (ord("c"), ord("C")):
            def _cfg_check(m):
                _set_msg(m)
            sudo_cmd(["apachectl", "configtest"], _cfg_check)
        elif ch == 9:                                    # Tab
            log_idx += 1

        def _set_msg(m):
            nonlocal cmd_msg
            cmd_msg = m

    curses.curs_set(1)


def check_root():
    if os.geteuid() != 0:
        print("Apache monitor needs sudo to run service commands.")
        print("Run with:  sudo python3 scripts/apache_monitor.py")
        raise SystemExit(1)


if __name__ == "__main__":
    check_root()
    curses.wrapper(main)
