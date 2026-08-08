#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_callflow_menu.py
------------------------
Menu-driven wrapper to:
    1) snapshot FreePBX data -> JSON (via freepbx_dump.py)
    2) render SVG call-flow(s) for selected or all DIDs (via freepbx_callflow_graph.py)
Python 3.6 safe. No external modules.

VARIABLE MAP (Key Script Variables)
-----------------------------------
Colors         : ANSI color codes for CLI output
ANSI_ESCAPE_RE : Regex for stripping ANSI codes
menu_options   : List of menu options for user selection
json_path      : Path to FreePBX data JSON snapshot
svg_dir        : Directory for SVG output
did_list       : List of DIDs available for rendering
selected_dids  : List of DIDs selected by user
args           : Parsed command-line arguments (if any)

Key Function Arguments:
-----------------------
text           : String to display or process
width          : Target width for padding
menu_options   : List of menu options
json_path      : Path to FreePBX data JSON
svg_dir        : Output directory for SVGs
did_list       : List of DIDs

See function docstrings for additional details on arguments and return values.

        FUNCTION MAP (Major Functions)
        -----------------------------
        visible_len              : Return printable length of ANSI-colored string
        pad_ansi                 : Pad ANSI-colored text to target width
        print_menu               : Print the interactive menu
        get_menu_choice          : Get user menu selection
        run_freepbx_dump         : Run freepbx_dump.py to snapshot data
        run_callflow_graph       : Run freepbx_callflow_graph.py to render SVGs
        list_dids_from_json      : Extract DID list from JSON snapshot
        main                     : Main menu loop and entry point
"""

import json, os, sys, subprocess, time, shutil, re, threading, smtplib, zipfile, socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    import termios, tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False  # e.g. Windows — fall back to plain prompt()

# ANSI Color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BG_BLUE = '\033[44m'
    BG_CYAN = '\033[46m'


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

_UNSAFE_TERMINAL_CHARS_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

def sanitize_for_terminal(s):
    """Strip control/escape bytes from untrusted log content before printing.

    Malformed or malicious traffic (garbled SIP packets, binary payloads)
    sometimes ends up logged verbatim. Printing that raw can include a stray
    ANSI/VT100 escape sequence — e.g. one that switches the terminal into
    DEC Special Graphics mode — which then silently remaps every character
    printed afterward for the rest of the session, well past this one line.
    """
    return _UNSAFE_TERMINAL_CHARS_RE.sub('', s)


def visible_len(text):
    """Return the printable length of a string that may contain ANSI codes."""
    if not text:
        return 0
    return len(ANSI_ESCAPE_RE.sub('', text))


def pad_ansi(text, width, align='left'):
    """Pad ANSI-colored text to a target width without breaking alignment."""
    if text is None:
        text = ''

    length = visible_len(text)
    if length >= width:
        return text

    pad = width - length
    if align == 'left':
        return text + ' ' * pad
    if align == 'right':
        return ' ' * pad + text
    if align == 'center':
        left = pad // 2
        right = pad - left
        return ' ' * left + text + ' ' * right
    raise ValueError(f"Unsupported alignment: {align}")


def print_progress_bar(current, total, label="", width=30):
    """Render a count-based progress bar in place via \\r. Only meaningful when
    the total is known ahead of time (a loop over a fixed list, e.g. per-DID
    rendering) — don't fake a percentage for a single opaque operation with an
    unknown duration; use run_with_spinner() for those instead."""
    total = max(total, 1)
    frac = min(current / total, 1.0)
    filled = int(width * frac)
    bar = "█" * filled + "-" * (width - filled)
    pct = int(frac * 100)
    sys.stdout.write(f"\r{Colors.CYAN}[{bar}] {current}/{total} ({pct}%){Colors.RESET} — {label}" + " " * 10)
    sys.stdout.flush()


def print_tip(text):
    """Print a contextual hint just above a prompt, matching the existing
    💡-prefixed convention (previously only used once, for SIP code lookup)."""
    print(f"{Colors.WHITE}💡 {text}{Colors.RESET}")


def load_smtp_config():
    """Read SMTP relay settings from SMTP_CONFIG_PATH. Returns None if the
    file is missing, unreadable, or has no host set, so callers can treat
    "email not configured yet" as a normal, non-error condition."""
    try:
        with open(SMTP_CONFIG_PATH) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    if not cfg.get("host"):
        return None
    return cfg


def send_email_with_attachment(to_addr, subject, body, attachment_path=None):
    """Send an email via the configured SMTP relay, optionally with one file
    attached. Returns (True, "") on success, (False, error_message) otherwise.
    Uses stdlib smtplib/email only — no new dependency, matches the rest of
    this codebase's "no external modules" convention."""
    cfg = load_smtp_config()
    if not cfg:
        return False, f"SMTP not configured (expected {SMTP_CONFIG_PATH})"

    msg = MIMEMultipart()
    # "@localhost" as a fallback sender is almost always rejected outright by
    # a real SASL-authenticated relay (envelope-sender/username mismatch) or
    # silently dropped by an upstream rewrite map that doesn't know about
    # it — confirmed in production. This box's own real hostname is at least
    # a real, resolvable domain a relay's rewrite rules have a chance of
    # already covering, and gives a saner address to debug a bounce from.
    msg["From"] = cfg.get("from_addr") or cfg.get("username") or f"freepbx-tools@{socket.getfqdn()}"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
        except OSError as e:
            return False, f"Could not read attachment {attachment_path}: {e}"
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(attachment_path)}"',
        )
        msg.attach(part)

    host = cfg["host"]
    port = int(cfg.get("port", 587))
    use_tls = cfg.get("use_tls", True)
    username = cfg.get("username")
    password = cfg.get("password")

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            if use_tls:
                server.starttls()
        try:
            if username:
                server.login(username, password or "")
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        finally:
            server.quit()
    except Exception as e:
        return False, str(e)
    return True, ""


def maybe_email_file(path, default_subject=None):
    """Offer to email a just-generated file to an address. Prints a one-line
    notice and skips (no prompt) if SMTP isn't configured yet, rather than
    erroring — every call site using this must work fine with email left
    unconfigured."""
    if not os.path.isfile(path):
        return
    cfg = load_smtp_config()
    if not cfg:
        print(f"{Colors.YELLOW}(Email not configured — see {SMTP_CONFIG_PATH} to enable this.){Colors.RESET}")
        return
    if not cfg.get("from_addr"):
        print_tip(f"No from_addr set in {SMTP_CONFIG_PATH} — if your relay requires "
                  f"authentication, the sender must match the authenticated username or "
                  f"it may be rejected. Set from_addr explicitly to avoid that.")
    to_addr = prompt(f"{Colors.YELLOW}Email this file to (blank to skip): {Colors.RESET}").strip()
    if not to_addr:
        return
    subject = default_subject or f"freepbx-tools: {os.path.basename(path)}"
    ok, err = send_email_with_attachment(
        to_addr, subject,
        f"Attached: {os.path.basename(path)}\nGenerated by freepbx-callflows.",
        path,
    )
    if ok:
        print(f"{Colors.GREEN}✅ Emailed {os.path.basename(path)} to {to_addr}{Colors.RESET}")
    else:
        print(f"{Colors.RED}❌ Failed to send email: {err}{Colors.RESET}")


def prompt(msg=""):
    """Drop-in replacement for prompt() with backspace/delete handling that doesn't
    depend on the remote pty's own stty erase-char setting.

    Some SSH clients/terminal proxies forward Backspace as 0x7F (DEL) or 0x08 (BS)
    inconsistently with what the pty's line discipline expects, which makes cooked-mode
    prompt() echo a literal ^H instead of erasing the character. This reads raw bytes and
    manually erases/re-echoes, so it behaves the same regardless of that mismatch.
    Also adds Ctrl-U (clear line). Falls back to plain prompt() when stdin isn't a real
    tty (piped/non-interactive use) or termios/tty aren't available (e.g. Windows).
    """
    if msg:
        sys.stdout.write(msg)
        sys.stdout.flush()

    if not _HAS_TERMIOS or not sys.stdin.isatty():
        return input()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buf = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                break
            elif ch in ("\x7f", "\x08"):  # DEL or BS — erase previous char
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x15":  # Ctrl-U — clear the whole line
                while buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                sys.stdout.flush()
            elif ch == "\x03":  # Ctrl-C
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise KeyboardInterrupt
            elif ch == "\x04" and not buf:  # Ctrl-D on empty line = EOF
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise EOFError
            elif ch >= " " or ch == "\t":  # printable — anything else (escape
                buf.append(ch)             # sequences, arrow keys, etc.) is ignored
                sys.stdout.write(ch)       # rather than corrupting the buffer
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return "".join(buf)


def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def _read_first_line(path):
    try:
        with open(path, 'r') as f:
            line = f.readline().strip()
            return line
    except Exception:
        return ""


def get_snapshot_age_seconds():
    try:
        if not os.path.isfile(DUMP_PATH):
            return None
        return max(0.0, time.time() - os.path.getmtime(DUMP_PATH))
    except Exception:
        return None


def format_age(age_seconds):
    if age_seconds is None:
        return "N/A"
    try:
        age_seconds = int(age_seconds)
    except Exception:
        return "N/A"
    if age_seconds < 60:
        return "{}s".format(age_seconds)
    if age_seconds < 3600:
        return "{}m".format(age_seconds // 60)
    return "{}h".format(age_seconds // 3600)


def get_freepbx_version_live():
    """Best-effort FreePBX version lookup (avoid heavy/slow commands)."""
    # Common FreePBX distro file
    v = _read_first_line("/etc/schmooze/pbx-version")
    if v:
        return v

    # Try fwconsole quickly (may emit noise on some systems)
    rc, out, _ = run(["fwconsole", "-V"], timeout=2)
    if rc == 0:
        line = (out.strip().splitlines() or [""])[0].strip()
        if line:
            return line
    return None


def get_asterisk_version_live():
    """Best-effort Asterisk version from CLI."""
    rc, out, _ = run(["asterisk", "-rx", "core show version"], timeout=2)
    if rc != 0:
        return None
    line = (out.strip().splitlines() or [""])[0].strip()
    if not line:
        return None
    # Usually: "Asterisk 16.16.0 built by ..."
    if line.lower().startswith("asterisk"):
        parts = line.split()
        if len(parts) >= 2:
            return parts[1]
    return line


def get_tool_version():
    """Read the VERSION file stamped at deploy time (see deploy_freepbx_tools.py's
    _generate_version_file()), so the dashboard can show at a glance whether this
    install is current. Returns e.g. "ffb4016 (2026-08-01)", or None if this
    install predates version stamping (older/manual installs — no VERSION file
    shipped) or the file can't be parsed, so the header just omits it rather
    than showing something broken."""
    version_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "VERSION")
    )
    try:
        info = {}
        with open(version_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k] = v
    except OSError:
        return None
    commit = info.get("COMMIT", "")
    if not commit:
        return None
    commit_date = info.get("COMMIT_DATE", "")
    date_short = commit_date[:10] if commit_date else ""
    return commit + (f" ({date_short})" if date_short else "")


DUMP_SCRIPT   = "/usr/local/bin/freepbx_dump.py"
GRAPH_SCRIPT  = "/usr/local/bin/freepbx_callflow_graph.py"
OUT_DIR       = "/home/123net/callflows"
DUMP_PATH     = os.path.join(OUT_DIR, "freepbx_dump.json")
DB_USER       = "root"
DEFAULT_SOCK  = "/var/lib/mysql/mysql.sock"
TC_STATUS_SCRIPT = "/usr/local/bin/freepbx_tc_status.py"
MODULE_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_module_analyzer.py"
PAGING_FAX_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_paging_fax_analyzer.py"
COMPREHENSIVE_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_comprehensive_analyzer.py"
ASCII_CALLFLOW_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py"
CALL_SIMULATOR_SCRIPT = "/usr/local/123net/freepbx-tools/bin/call_simulator.py"
CALLFLOW_VALIDATOR_SCRIPT = "/usr/local/123net/freepbx-tools/bin/callflow_validator.py"
SIMULATE_CALLS_SCRIPT = "/usr/local/123net/freepbx-tools/bin/simulate_calls.sh"
NETWORK_DIAGNOSTICS_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_network_diagnostics.py"
LOG_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_log_analyzer.py"
CDR_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_cdr_analyzer.py"
CALL_LEG_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_call_leg_analyzer.py"
OPS_SCRIPT         = "/usr/local/123net/freepbx-tools/bin/freepbx_ops.py"
CERT_CHECK_SCRIPT  = "/usr/local/123net/freepbx-tools/bin/freepbx_cert_check.py"
SMTP_CONFIG_PATH   = "/etc/123net-freepbx-tools/smtp.json"
SELF_TEST_DIR       = os.path.join(OUT_DIR, "self_test")


def run_ops_menu(sock):
    """Interactive submenu for freepbx_ops (trace, find, snapshot, validate, set-ivr)."""
    if not os.path.isfile(OPS_SCRIPT):
        print(Colors.RED + "\n❌ freepbx_ops.py not found at " + OPS_SCRIPT + Colors.RESET)
        print(Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
        prompt()
        return

    base_cmd = ["python3", OPS_SCRIPT, "--socket", sock]

    while True:
        print(f"\n{Colors.CYAN}Main Menu › Call-Flow Ops Tools{Colors.RESET}")
        print(Colors.CYAN + Colors.BOLD + "╔══════════════════════════════════════════╗" + Colors.RESET)
        print(Colors.CYAN + Colors.BOLD + "║   🔧  Call-Flow Ops Tools                ║" + Colors.RESET)
        print(Colors.CYAN + Colors.BOLD + "╠══════════════════════════════════════════╣" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  1) Trace DID  — full call-path tree     " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  2) Decode destination string            " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  3) Find  — search across all components " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  4) Snapshot  — save current call-flow   " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  5) Validate  — health/consistency check " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  6) Set IVR option (dry-run / apply)     " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  7) Print ticket note                    " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  8) Ring group analysis (timeouts/loops) " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠══════════════════════════════════════════╣" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.RESET + "  0) Back to main menu                    " + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + Colors.BOLD + "╚══════════════════════════════════════════╝" + Colors.RESET)
        ch = prompt("\n" + Colors.YELLOW + "Choose (0/b=back): " + Colors.RESET).strip()

        if ch == "0" or ch.lower() == "b":
            break

        elif ch == "1":
            did = prompt(Colors.YELLOW + "DID number: " + Colors.RESET).strip()
            if did:
                subprocess.call(base_cmd + ["trace", did])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "2":
            dest = prompt(Colors.YELLOW + "Destination string (e.g. ext-group,7004,1): " + Colors.RESET).strip()
            if dest:
                subprocess.call(base_cmd + ["decode", dest])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "3":
            print_tip("Matches against DIDs, labels, extensions, and destinations.")
            query = prompt(Colors.YELLOW + "Search term: " + Colors.RESET).strip()
            if query:
                subprocess.call(base_cmd + ["find", query])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "4":
            reason = prompt(Colors.YELLOW + "Reason (optional): " + Colors.RESET).strip()
            cmd = base_cmd + ["snapshot"]
            if reason:
                cmd += ["--reason", reason]
            subprocess.call(cmd)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "5":
            subprocess.call(base_cmd + ["validate"])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "6":
            print_tip("Numeric IVR ID as shown in the DID table (option 2's inventory).")
            ivr_id = prompt(Colors.YELLOW + "IVR ID: " + Colors.RESET).strip()
            option = prompt(Colors.YELLOW + "Option (1, 2, t, i, ...): " + Colors.RESET).strip()
            dest   = prompt(Colors.YELLOW + "New destination: " + Colors.RESET).strip()
            if ivr_id and option and dest:
                mode = prompt(Colors.YELLOW + "p=preview only  a=apply directly  Enter=preview then confirm: " + Colors.RESET).strip().lower()
                set_cmd = base_cmd + ["set-ivr", "--ivr", ivr_id, "--option", option, "--dest", dest]
                if mode == "a":
                    subprocess.call(set_cmd + ["--apply"])
                else:
                    subprocess.call(set_cmd)  # preview
                    if mode != "p":
                        apply = prompt(Colors.YELLOW + "\nApply change? (y/N): " + Colors.RESET).strip().lower()
                        if apply in ("y", "yes"):
                            subprocess.call(set_cmd + ["--apply"])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "7":
            subprocess.call(base_cmd + ["ticket"])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        elif ch == "8":
            subprocess.call(base_cmd + ["ringgroups"])
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            prompt()

        else:
            print(Colors.RED + "Invalid choice." + Colors.RESET)


def run_tc_status(sock):
    """Invoke the time-condition status tool."""
    if not os.path.isfile(TC_STATUS_SCRIPT):
        print("Time Condition status tool not found at", TC_STATUS_SCRIPT)
        return
    rc, out, err = run(["python3", TC_STATUS_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    prompt()


def run_tc_control(sock):
    """Show TC status then offer interactive force/clear control."""
    # Show existing status first
    run_tc_status(sock)

    # Query TC list from DB
    sql = ("SELECT timeconditions_id, "
           "COALESCE(displayname, COALESCE(name, CONCAT('TC ',timeconditions_id))), "
           "COALESCE(inuse_state,0) FROM timeconditions ORDER BY CAST(timeconditions_id AS UNSIGNED)")
    rc, out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql, "asterisk"])
    if rc != 0 or not out.strip():
        print(f"{Colors.YELLOW}Could not query time conditions from database.{Colors.RESET}")
        return

    tcs = []
    for line in out.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            try:
                tcs.append((int(parts[0]), parts[1], int(parts[2])))
            except ValueError:
                pass

    if not tcs:
        print(f"{Colors.YELLOW}No time conditions found.{Colors.RESET}")
        return

    STATE_LABELS = {0: f"{Colors.GREEN}Auto{Colors.RESET}",
                    1: f"{Colors.YELLOW}Forced TRUE{Colors.RESET}",
                    2: f"{Colors.RED}Forced FALSE{Colors.RESET}"}

    W = 70
    print(f"\n{Colors.CYAN}╔{'═' * W}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} ⏰ TC Force / Clear Control{' ' * (W - 27)}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * W}╣{Colors.RESET}")
    for tc_id, name, state in tcs:
        label = STATE_LABELS.get(state, str(state))
        raw_label = {0: "Auto", 1: "Forced TRUE", 2: "Forced FALSE"}.get(state, str(state))
        row = f"  {tc_id:>4}  {name[:38]:<38}  {raw_label}"
        # print with colour
        print(f"{Colors.CYAN}║{Colors.WHITE}{f'  {tc_id:>4}  {name[:38]:<38}  '}{label}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * W}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.GREEN}  Actions: {Colors.WHITE}1=Force TRUE   2=Force FALSE   3=Clear (Auto)   0=Done{' ' * 4}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * W}╝{Colors.RESET}")

    while True:
        tc_pick = prompt(f"\n{Colors.YELLOW}TC ID to control (or 0 to exit): {Colors.RESET}").strip()
        if tc_pick == "0" or tc_pick == "":
            break
        try:
            tc_id_int = int(tc_pick)
        except ValueError:
            print(f"{Colors.RED}Invalid ID.{Colors.RESET}")
            continue
        match = next((t for t in tcs if t[0] == tc_id_int), None)
        if not match:
            print(f"{Colors.RED}TC {tc_id_int} not found.{Colors.RESET}")
            continue

        action = prompt(f"{Colors.YELLOW}Action — 1=Force TRUE  2=Force FALSE  3=Clear: {Colors.RESET}").strip()
        if action not in ("1", "2", "3"):
            print(f"{Colors.RED}Invalid action.{Colors.RESET}")
            continue

        tc_name = match[1]
        if action == "3":
            print(f"{Colors.YELLOW}Clearing override for TC {tc_id_int} ({tc_name})...{Colors.RESET}")
            run(["asterisk", "-rx", f"database del TCTEMP {tc_id_int}"])
            run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", f"UPDATE timeconditions SET inuse_state=0 WHERE timeconditions_id={tc_id_int}", "asterisk"])
            print(f"{Colors.GREEN}✓ TC {tc_id_int} set to Auto (schedule).{Colors.RESET}")
        else:
            state_label = "TRUE" if action == "1" else "FALSE"
            print(f"{Colors.YELLOW}Forcing TC {tc_id_int} ({tc_name}) → {state_label}...{Colors.RESET}")
            run(["asterisk", "-rx", f"database put TCTEMP {tc_id_int} force {action}"])
            run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", f"UPDATE timeconditions SET inuse_state={action} WHERE timeconditions_id={tc_id_int}", "asterisk"])
            print(f"{Colors.GREEN}✓ TC {tc_id_int} forced {state_label}.{Colors.RESET}")

        _DASH_CACHE["ts"] = 0.0  # invalidate dashboard cache after TC change


def run_module_analyzer(sock):
    """Invoke the FreePBX module analyzer tool."""
    if not os.path.isfile(MODULE_ANALYZER_SCRIPT):
        print("Module analyzer tool not found at", MODULE_ANALYZER_SCRIPT)
        return
    # run_interactive (not run/spinner): the analyzer prints its own progress
    # as it works, so let that stream live instead of buffering it all until done.
    rc = run_interactive(["python3", MODULE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc != 0:
        print(f"{Colors.RED}Module analyzer exited with code {rc}.{Colors.RESET}")
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    prompt()


def run_paging_fax_analyzer(sock):
    """Invoke the FreePBX paging/fax analyzer tool."""
    if not os.path.isfile(PAGING_FAX_ANALYZER_SCRIPT):
        print("Paging/Fax analyzer tool not found at", PAGING_FAX_ANALYZER_SCRIPT)
        return
    rc, out, err = run_with_spinner(
        ["python3", PAGING_FAX_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER],
        "Analyzing paging & fax configuration",
    )
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    prompt()


def run_comprehensive_analyzer(sock):
    """Invoke the comprehensive FreePBX component analyzer."""
    if not os.path.isfile(COMPREHENSIVE_ANALYZER_SCRIPT):
        print("Comprehensive analyzer tool not found at", COMPREHENSIVE_ANALYZER_SCRIPT)
        return
    # run_interactive (not run/spinner): the analyzer prints "[i/16] ..." step
    # markers as it works, so let that stream live instead of buffering it all.
    rc = run_interactive(["python3", COMPREHENSIVE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc != 0:
        print(f"{Colors.RED}Comprehensive analyzer exited with code {rc}.{Colors.RESET}")
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    prompt()


def run_call_simulation_menu(sock, did_rows, data=None):
    """Interactive call simulation and validation menu."""
    # Pre-flight: check which tools are available
    simulator_ok   = os.path.isfile(CALL_SIMULATOR_SCRIPT)
    validator_ok   = os.path.isfile(CALLFLOW_VALIDATOR_SCRIPT)
    monitoring_ok  = os.path.isfile(SIMULATE_CALLS_SCRIPT)

    W = 78
    while True:
        print(f"\n{Colors.CYAN}Main Menu › Call Simulation & Validation{Colors.RESET}")
        print(f"{Colors.CYAN}╔{'═' * W}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 Call Simulation & Validation{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * W}╣{Colors.RESET}")

        # ── Safe section ──────────────────────────────────────────────────────
        safe_hdr = " ── Database Checks (safe — no live calls) ── "
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.GREEN}{safe_hdr:<{W}}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
        avail = Colors.GREEN if validator_ok else Colors.RED
        print(f"{Colors.CYAN}║{avail} 1){Colors.WHITE} Validate DID call-flow config  (database only){' ' * 22}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")

        # ── Live call section ─────────────────────────────────────────────────
        live_hdr = " ── ⚠  LIVE CALL TESTS — makes real calls on this system ── "
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.RED}{live_hdr:<{W}}{Colors.RESET}{Colors.CYAN}║{Colors.RESET}")
        avail = Colors.GREEN if simulator_ok else Colors.RED
        na    = "" if simulator_ok else "  [⚠ simulator not installed]"
        print(f"{Colors.CYAN}║{avail} 2){Colors.WHITE} Test specific DID{na}{' ' * max(0, 51 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 3){Colors.WHITE} Test extension-to-extension call{na}{' ' * max(0, 37 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 4){Colors.WHITE} Test voicemail access{na}{' ' * max(0, 48 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 5){Colors.WHITE} Test audio playback  (plays a sound file){na}{' ' * max(0, 28 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 6){Colors.WHITE} Test ring group{na}{' ' * max(0, 55 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 7){Colors.WHITE} Test queue{na}{' ' * max(0, 60 - len(na))}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{avail} 8){Colors.RED}{Colors.BOLD} ⚠ Comprehensive validation  (many real calls — use in test env){' ' * 7}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")

        # ── Monitoring ────────────────────────────────────────────────────────
        avail = Colors.GREEN if monitoring_ok else Colors.RED
        print(f"{Colors.CYAN}║{avail} 9){Colors.WHITE} Monitor active call simulations{' ' * 39}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")

        print(f"{Colors.CYAN}╠{'═' * W}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 0){Colors.WHITE} Return to main menu{' ' * 51}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * W}╝{Colors.RESET}")
        print()

        choice = prompt(f"{Colors.YELLOW}Choose option (0/b=back, 1-9): {Colors.RESET}").strip()

        if choice == "0" or choice.lower() == "b":
            break
        elif choice == "1":
            run_callflow_validation(did_rows)
        elif choice == "2":
            run_did_call_test(did_rows)
        elif choice == "3":
            run_extension_test()
        elif choice == "4":
            run_voicemail_test()
        elif choice == "5":
            run_playback_test()
        elif choice == "6":
            run_ring_group_test(data)
        elif choice == "7":
            run_queue_test(data)
        elif choice == "8":
            run_comprehensive_validation()
        elif choice == "9":
            run_call_monitoring()
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 0-9.{Colors.RESET}")


def run_did_call_test(did_rows):
    """Test a specific DID with call simulation."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print(f"{Colors.RED}❌ Call simulator not found. Please run deployment first.{Colors.RESET}")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    if not did_rows:
        print(f"{Colors.RED}❌ No DID data available. Please refresh the data cache first.{Colors.RESET}")
        return
    
    print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 DID Call Simulation Test{' ' * 49}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} This will create a real call file to test the DID routing.{' ' * 18}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    print()
    
    # Show available DIDs
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.WHITE}Available DIDs:{Colors.RESET}")
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    
    for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
        print(f"{Colors.GREEN}{i:>2}.{Colors.RESET} {Colors.CYAN}{did:<15}{Colors.WHITE} {label}{Colors.RESET}")
    
    if len(did_rows) > 20:
        print(f"{Colors.YELLOW}... and {len(did_rows) - 20} more DIDs{Colors.RESET}")
    
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    print()
    
    try:
        print_tip("List index, or the DID itself in any format (2485551212, (248) 555-1212, +12485551212).")
        raw_choice = prompt(f"{Colors.YELLOW}Enter DID number to test (or 0 to cancel): {Colors.RESET}").strip()
        if raw_choice == "0":
            return
        did_idx = _find_did_index(raw_choice, did_rows)
        choice = did_idx if did_idx is not None else int(raw_choice)
        if choice < 1 or choice > len(did_rows):
            print(f"{Colors.RED}❌ Invalid selection.{Colors.RESET}")
            return

        _, did, label, _, _ = did_rows[choice - 1]
        print_tip("A number here actually dials out to it (e.g. your own cell) — it "
                  "will really ring. Leave blank unless that's what you want to test.")
        destination = prompt(
            f"{Colors.YELLOW}Force ring to a specific number (optional — leave blank to follow "
            f"the DID's actual configured routing, e.g. its queue/IVR/ring group): {Colors.RESET}"
        ).strip()

        print(f"\n{Colors.GREEN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.YELLOW}{Colors.BOLD} 🚀 Testing DID {did} ({label[:40]}){' ' * (31 - len(label[:40]))}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}   Incoming call from: {Colors.CYAN}{Colors.BOLD}{did:<49}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        if destination:
            print(f"{Colors.GREEN}║{Colors.WHITE}   Forcing ring to: {Colors.MAGENTA}{Colors.BOLD}{destination:<53}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}║{Colors.WHITE}   Following the DID's actual configured routing{' ' * 25}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.YELLOW}   This will create a real call in the Asterisk system...{' ' * 17}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}╚{'═' * 78}╝{Colors.RESET}")
        print()

        confirm = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
        if confirm != 'y':
            print(f"{Colors.RED}❌ Test cancelled.{Colors.RESET}")
            return

        # Run the call simulation. Omitting --destination (blank input) makes
        # call_simulator.py enter through from-did-direct — the DID's real
        # inbound entry point — instead of forcing an artificial destination.
        cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--did", str(did), "--debug"]
        if destination:
            cmd += ["--destination", destination]
        print(f"{Colors.CYAN}Executing: {' '.join(cmd)}{Colors.RESET}\n")

        rc = run_interactive(cmd)
        if rc == 0:
            print(f"\n{Colors.GREEN}✅ Call simulation completed successfully!{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}❌ Call simulation failed (exit code {rc}).{Colors.RESET}")

    except ValueError:
        print(f"{Colors.RED}❌ Invalid input. Please enter a number.{Colors.RESET}")
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}❌ Test cancelled by user.{Colors.RESET}")


def run_callflow_validation(did_rows):
    """Validate call flow accuracy for a specific DID."""
    if not os.path.isfile(CALLFLOW_VALIDATOR_SCRIPT):
        print("❌ Call flow validator not found. Please run deployment first.")
        return
    
    if not did_rows:
        print("❌ No DID data available. Please refresh the data cache first.")
        return
    
    print("\n🔍 Call Flow Validation Test")
    print("This compares predicted call flows with actual call behavior.")
    print()
    
    # Show available DIDs
    for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
        print(f"{i:>2}. {did:<15} {label}")
    
    if len(did_rows) > 20:
        print(f"... and {len(did_rows) - 20} more DIDs")
    
    print()
    try:
        print_tip("List index, or the DID itself in any format (2485551212, (248) 555-1212, +12485551212).")
        raw_choice = prompt("Enter DID number to validate (or 0 to cancel): ").strip()
        if raw_choice == "0":
            return
        did_idx = _find_did_index(raw_choice, did_rows)
        choice = did_idx if did_idx is not None else int(raw_choice)
        if choice < 1 or choice > len(did_rows):
            print("❌ Invalid selection.")
            return

        _, did, label, _, _ = did_rows[choice - 1]
        
        print(f"\n🔍 Validating call flow for DID {did} ({label})")
        print("This will:")
        print("1. Generate predicted call flow")
        print("2. Simulate actual call")
        print("3. Compare prediction vs reality")
        print("4. Provide accuracy score")
        
        confirm = prompt("\nContinue with validation? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Validation cancelled.")
            return
        
        # Run the validation
        cmd = ["python3", CALLFLOW_VALIDATOR_SCRIPT, str(did)]

        rc, out, err = run_with_spinner(cmd, f"Validating call flow for DID {did}")
        if rc == 0:
            print("✅ Call flow validation completed!")
            print(out)
        else:
            print("❌ Call flow validation failed:")
            print(err or out)
            
    except ValueError:
        print("❌ Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\n❌ Validation cancelled by user.")


def run_extension_test():
    """Test calling a specific extension."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    print("\n📱 Extension-to-Extension Call Test")

    print_tip("3-5 digit internal extension, e.g. 963.")
    source_ext = prompt("Source extension (shown as caller ID): ").strip()
    if not source_ext:
        print("❌ Source extension required.")
        return

    dest_ext = prompt("Destination extension (who gets called): ").strip()
    if not dest_ext:
        print("❌ Destination extension required.")
        return

    extension = dest_ext
    caller_id = source_ext

    print(f"\n🚀 Testing {source_ext} -> {dest_ext}")
    
    confirm = prompt("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--extension", extension, "--caller-id", caller_id, "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Extension test completed!")
    else:
        print(f"❌ Extension test failed (exit code {rc}).")


def _pick_from_list(items, label_fn, prompt_label):
    """Generic 1-based picker: prints each item via label_fn, prompts for a
    choice (Enter defaults to #1), returns the picked item or None."""
    for i, item in enumerate(items, 1):
        print(f"  {i}) {label_fn(item)}")
    pick = prompt(f"{Colors.YELLOW}Pick a {prompt_label} (Enter for #1): {Colors.RESET}").strip()
    idx = 1
    if pick:
        try:
            idx = int(pick)
        except ValueError:
            print(f"{Colors.RED}Not a number — using #1.{Colors.RESET}")
            idx = 1
    if idx < 1 or idx > len(items):
        print(f"{Colors.RED}Invalid selection — using #1.{Colors.RESET}")
        idx = 1
    return items[idx - 1]


def _resolve_ext_names(ext_list, data):
    """Map raw extension numbers to 'ext (name)' labels using cached
    extension data, so a ring group/queue member list is actually useful
    for knowing which physical phone to watch, not just bare numbers."""
    ext_names = {str(e.get("extension")): e.get("name", "") for e in (data or {}).get("extensions") or []}
    labels = []
    for ext in ext_list:
        ext = ext.strip()
        if not ext:
            continue
        name = ext_names.get(ext, "")
        labels.append(f"{ext} ({name})" if name else ext)
    return labels


def run_ring_group_test(data):
    """Test calling a specific ring group."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    ring_groups = (data or {}).get("ringgroups") or []
    if not ring_groups:
        print(f"{Colors.RED}❌ No ring groups configured on this system.{Colors.RESET}")
        return

    print("\n🔔 Ring Group Call Test")
    print(f"\n{Colors.CYAN}Ring groups configured on this system:{Colors.RESET}")
    picked = _pick_from_list(
        ring_groups,
        lambda rg: f"{rg.get('grpnum')}  {rg.get('description', '')}",
        "ring group to test",
    )
    grpnum = str(picked.get("grpnum"))
    strategy = picked.get("strategy") or "ringall"
    ringtime = picked.get("ringtime") or "?"
    members = _resolve_ext_names((picked.get("grplist") or "").split("-"), data)

    print(f"\n{Colors.CYAN}Strategy: {strategy}  Ring time: {ringtime}s{Colors.RESET}")
    if members:
        print(f"{Colors.CYAN}Expected to ring — watch these phones:{Colors.RESET}")
        for m in members:
            print(f"  📱 {m}")
    else:
        print(f"{Colors.YELLOW}⚠ No members configured on this ring group.{Colors.RESET}")

    print_tip("3-5 digit internal extension, e.g. 963.")
    source_ext = prompt("Source extension (shown as caller ID): ").strip() or "8884400123"

    print(f"\n🚀 Testing ring group {grpnum} (caller ID: {source_ext})")
    confirm = prompt("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return

    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--ring-group", grpnum, "--caller-id", source_ext, "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Ring group test completed!")
    else:
        print(f"❌ Ring group test failed (exit code {rc}).")


def run_queue_test(data):
    """Test calling a specific queue."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    queues = (data or {}).get("queues") or []
    if not queues:
        print(f"{Colors.RED}❌ No queues configured on this system.{Colors.RESET}")
        return

    print("\n📞 Queue Call Test")
    print(f"\n{Colors.CYAN}Queues configured on this system:{Colors.RESET}")
    picked = _pick_from_list(
        queues,
        lambda q: f"{q.get('queue')}  {q.get('queue_name', '')}",
        "queue to test",
    )
    ext = str(picked.get("queue"))
    strategy = picked.get("strategy") or "?"
    timeout = picked.get("timeout") or "?"
    members = _resolve_ext_names((picked.get("members") or "").split(","), data)

    print(f"\n{Colors.CYAN}Strategy: {strategy}  Timeout: {timeout}s{Colors.RESET}")
    if members:
        print(f"{Colors.CYAN}Expected agent phones — watch these:{Colors.RESET}")
        for m in members:
            print(f"  📱 {m}")
    else:
        print(f"{Colors.YELLOW}⚠ No members configured on this queue.{Colors.RESET}")

    print_tip("3-5 digit internal extension, e.g. 963.")
    source_ext = prompt("Source extension (shown as caller ID): ").strip() or "8884400123"

    print(f"\n🚀 Testing queue {ext} (caller ID: {source_ext})")
    confirm = prompt("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return

    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--queue", ext, "--caller-id", source_ext, "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Queue test completed!")
    else:
        print(f"❌ Queue test failed (exit code {rc}).")


def run_voicemail_test():
    """Test calling voicemail."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    print("\n📧 Voicemail Call Test")

    print_tip("Mailbox number, usually the same as the extension, e.g. 963.")
    mailbox = prompt("Enter voicemail mailbox to test: ").strip()
    if not mailbox:
        print("❌ Mailbox number required.")
        return
    
    caller_id = prompt("Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
    
    print(f"\n🚀 Testing voicemail {mailbox} with caller ID {caller_id}")
    
    confirm = prompt("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--voicemail", mailbox, "--caller-id", caller_id, "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Voicemail test completed!")
    else:
        print(f"❌ Voicemail test failed (exit code {rc}).")


def run_playback_test():
    """Test audio playback via Asterisk (plays a sound file)."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}⚠  LIVE CALL TEST — this will make a real call on the production system.{Colors.RESET}")
    gate = prompt(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
    if gate != "y":
        print("Cancelled.")
        return

    print("\n🎵 Audio Playback Test")
    print("Common sound files: demo-congrats, demo-thanks, zombies, beep")
    
    sound_file = prompt("Enter sound file to play: ").strip()
    if not sound_file:
        print("❌ Sound file required.")
        return
    
    caller_id = prompt("Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
    
    print(f"\n🚀 Testing playback of '{sound_file}' with caller ID {caller_id}")
    
    confirm = prompt("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--playback", sound_file, "--caller-id", caller_id, "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Playback test completed!")
    else:
        print(f"❌ Playback test failed (exit code {rc}).")


def run_comprehensive_validation():
    """Run comprehensive call validation testing."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return

    print(f"\n{Colors.RED}{Colors.BOLD}{'═' * 70}")
    print(f"⚠  COMPREHENSIVE LIVE CALL TEST")
    print(f"   This will create MULTIPLE real calls across the production system:")
    print(f"   DID routing, extension, voicemail, application, ring group,")
    print(f"   and queue tests — ring groups/queues are discovered from this")
    print(f"   PBX's own config, so every configured group/queue will ring.")
    print(f"   DO NOT run this on a live customer system during business hours.")
    print(f"{'═' * 70}{Colors.RESET}")
    print()
    confirm = prompt(f"{Colors.YELLOW}Type CONFIRM to proceed, or press Enter to cancel: {Colors.RESET}").strip()
    if confirm != "CONFIRM":
        print("❌ Testing cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--comprehensive", "--debug"]
    rc = run_interactive(cmd)

    if rc == 0:
        print("✅ Comprehensive validation completed!")
    else:
        print(f"❌ Comprehensive validation failed (exit code {rc}).")


def run_call_monitoring():
    """Monitor active call simulations."""
    if not os.path.isfile(SIMULATE_CALLS_SCRIPT):
        print("❌ Call monitoring script not found. Please run deployment first.")
        return
    
    print("\n📊 Call Simulation Monitor")
    print("This will show active call files and recent Asterisk activity.")
    print("Press Ctrl+C to stop monitoring.")
    print()
    
    try:
        cmd = [SIMULATE_CALLS_SCRIPT, "monitor"]
        # Use subprocess.call for interactive monitoring
        import subprocess
        subprocess.call(cmd)
    except KeyboardInterrupt:
        print("\n✅ Monitoring stopped.")
    except Exception as e:
        print(f"❌ Monitoring failed: {str(e)}")


def run_ascii_callflow(sock, did_rows):
    """Generate ASCII art call flow for selected DIDs."""
    if not os.path.isfile(ASCII_CALLFLOW_SCRIPT):
        print("ASCII callflow tool not found at", ASCII_CALLFLOW_SCRIPT)
        return
    
    while True:
        print("\n=== ASCII Art Call Flow Generator ===")
        print("Choose an option:")
        print()
        print("1. Generate ASCII flow for specific DID(s)")
        print("2. Show comprehensive data collection summary")
        print("3. Show detailed configuration data")
        print("4. Export all data to JSON file")
        print("5. Generate flows for ALL DIDs")
        print("6. Return to main menu")
        print()
        
        choice = prompt("Enter choice (1-6): ").strip()
        
        if choice == "6":
            # Return to main menu
            print("Returning to main menu...")
            break
        
        elif choice == "1":
            # Original DID-specific flow generation
            if not did_rows:
                print("No DID data available. Please refresh the data cache first.")
                continue
            
            print("\nSelect DID(s) for ASCII flow chart generation:")
            print()
            
            # Show available DIDs
            for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
                print(f"{i:>2}. {did:<15} {label}")
            
            if len(did_rows) > 20:
                print(f"... and {len(did_rows) - 20} more DIDs")
            
            print()
            selection = prompt("Enter DID number(s) or 'all' (e.g., 1,3,5 or 1-5): ").strip()
            
            if not selection:
                continue
            
            # Parse selection
            if selection.lower() in ("all", "*"):
                selected_indices = list(range(1, min(len(did_rows) + 1, 11)))  # Limit to first 10 for ASCII
                print("Note: Limited to first 10 DIDs for ASCII output")
            else:
                selected_indices = parse_selection(selection, did_rows)
            
            if not selected_indices:
                print("No valid selection.")
                continue
            
            print(f"\n🎨 Generating ASCII call flows for {len(selected_indices)} DID(s)...")
            print("=" * 60)
            
            for i, idx in enumerate(selected_indices):
                if i >= 10:  # Limit ASCII output
                    print(f"\n... {len(selected_indices) - 10} more DIDs not shown (use individual analysis for more)")
                    break
                    
                _, did, label, _, _ = did_rows[idx - 1]
                print(f"\n[{i+1}/{min(len(selected_indices), 10)}] Generating flow for DID: {did}")
                print("-" * 60)
                
                cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--did", str(did)]
                rc, out, err = run(cmd)
                
                if rc == 0:
                    print(out)
                else:
                    print(f"❌ Error generating flow for {did}: {err or out}")
                
                if i < min(len(selected_indices), 10) - 1:
                    print("\n" + "=" * 60)
        
        elif choice == "2":
            # Show data collection summary
            print("\nRunning comprehensive data collection with summary...")
            cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--print-data"]
            rc, out, err = run(cmd)
            if rc == 0:
                print(out, end="")
            else:
                print(f"Error: {err or out}")
        
        elif choice == "3":
            # Show detailed configuration data
            print("\nRunning comprehensive data collection with detailed output...")
            cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--print-data", "--detailed"]
            rc, out, err = run(cmd)
            if rc == 0:
                print(out, end="")
            else:
                print(f"Error: {err or out}")
        
        elif choice == "4":
            # Export data to JSON
            timestamp = int(time.time())
            export_file = f"/tmp/freepbx_config_{timestamp}.json"
            print(f"\nExporting comprehensive FreePBX data to: {export_file}")
            cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--export", export_file]
            rc, out, err = run(cmd)
            if rc == 0:
                print(out, end="")
                print(f"\n✅ Data exported to: {export_file}")
                maybe_email_file(export_file, default_subject="freepbx-tools: FreePBX config export")
            else:
                print(f"Error: {err or out}")

        elif choice == "5":
            # Generate flows for all DIDs
            print("\nGenerating ASCII flows for ALL DIDs...")
            cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--generate-flow"]
            rc, out, err = run(cmd)
            if rc == 0:
                print(out, end="")
            else:
                print(f"Error: {err or out}")
        
        else:
            print("Invalid choice. Please enter 1-6.")
        
        # After completing any action (except return to main menu), loop back
        if choice != "6":
            prompt("\nPress Enter to continue...")



def show_error_map_quick_reference():
    """SIP/Q.850 code lookup — direct, no sub-menu."""
    show_sip_code_reference()


def show_sip_code_reference():
    """Display SIP/Q.850/Asterisk code mapping table"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*98}╗")
    print(f"║{' SIP / Q.850 / ASTERISK CAUSE CODE MAPPING':^98}║")
    print(f"╠{'═'*98}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'SIP':<6} │ {'Q.850':<6} │ {'Description':<25} │ {'What It Usually Means':<50}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*98}╣{Colors.RESET}")
    
    codes = [
        ("404", "1", "Not Found", "Extension not found or wrong dialed number"),
        ("408", "18", "Request Timeout", "No response – NAT, firewall, or transport issue"),
        ("480", "19", "Unavailable", "Rings then drops - user never answered"),
        ("486", "17", "Busy Here", "Phone in use or call limit reached"),
        ("487", "16", "Terminated", "Normal clearing from caller side"),
        ("503", "34", "Service Unavailable", "Trunk congestion / carrier unavailable"),
        ("500", "41", "Server Error", "Upstream gateway or media path failure"),
        ("401", "21", "Unauthorized", "Carrier rejecting call (auth issue)"),
        ("403", "21", "Forbidden", "Call rejected by policy"),
        ("603", "21", "Decline", "Call explicitly rejected"),
    ]
    
    for sip, q850, desc, meaning in codes:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{sip:<6}{Colors.RESET} │ {Colors.GREEN}{q850:<6}{Colors.RESET} │ {Colors.WHITE}{desc:<25}{Colors.RESET} │ {Colors.CYAN}{meaning:<50}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*98}╝{Colors.RESET}")
    
    # Interactive lookup
    print(f"\n{Colors.WHITE}💡 Enter a SIP code to see details (or press Enter to skip): {Colors.RESET}", end="")
    code = prompt().strip()
    if code:
        from freepbx_log_analyzer import lookup_cause_code, format_cause_code
        info = lookup_cause_code(code)
        if info:
            print(f"\n{Colors.GREEN}✓ SIP {info['sip']}:{Colors.RESET}")
            print(f"  Q.850 Cause: {Colors.YELLOW}{info['q850']}{Colors.RESET}")
            print(f"  Description: {Colors.CYAN}{info['description']}{Colors.RESET}")
            print(f"  Asterisk: {Colors.MAGENTA}{info['asterisk_cause']}{Colors.RESET}")
            print(f"  Meaning: {Colors.WHITE}{info['meaning']}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}Code not found in mapping table{Colors.RESET}")


def show_common_issues_matrix():
    """Display common issues quick reference matrix"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*118}╗")
    print(f"║{' COMMON ISSUES QUICK REFERENCE MATRIX':^118}║")
    print(f"╠{'═'*118}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'Category':<25} │ {'Log Signature':<40} │ {'Impact':<45}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*118}╣{Colors.RESET}")
    
    issues = [
        ("Database Failure", "Failed to connect to database", "FreePBX cannot read config; calls may fail"),
        ("Trunk Offline", "Registration.*failed", "External calling over trunk will fail"),
        ("Auth Storm/Attack", "failed to authenticate", "Brute-force attacks or blocked endpoints"),
        ("Queue Abandon Spike", "Multiple ABANDON events", "Customer hang-ups, SLA breach"),
        ("Codec Negotiation", "Unable to negotiate codec", "Calls fail with fast busy"),
        ("RTP/Media Failure", "RTP Timeout", "One-way or no audio; call teardown"),
        ("Voicemail Storage", "Failed to create voicemail", "New voicemail drops fail to record"),
        ("Channel Ceiling", "channels count near limit", "New calls may be rejected"),
    ]
    
    for category, signature, impact in issues:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{category:<25}{Colors.RESET} │ {Colors.WHITE}{signature:<40}{Colors.RESET} │ {Colors.RED}{impact:<45}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*118}╝{Colors.RESET}")


def show_diagnostic_symptoms():
    """Display diagnostic symptoms quick guide"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*98}╗")
    print(f"║{' DIAGNOSTIC SYMPTOMS GUIDE':^98}║")
    print(f"╠{'═'*98}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'Symptom':<35} │ {'Common Cause':<25} │ {'What It Means':<30}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*98}╣{Colors.RESET}")
    
    symptoms = [
        ("Immediate 'busy' tone", "486 / Q.850 17", "Phone in use or limit reached"),
        ("Rings then drops", "480 / Q.850 19", "User never answered"),
        ("Fails instantly", "404 / Q.850 1", "Wrong number / not found"),
        ("'Call failed' right away", "503 / Q.850 34", "Trunk congestion"),
        ("Long silence before drop", "408 / Q.850 18", "NAT/firewall/transport issue"),
        ("Works internally not outbound", "401/403 / Q.850 21", "Carrier rejecting call"),
        ("Audio dies mid-call", "500 / Q.850 41", "Gateway/media path failure"),
        ("Random inbound drops", "487 / Q.850 16", "Caller hung up normally"),
    ]
    
    for symptom, cause, meaning in symptoms:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{symptom:<35}{Colors.RESET} │ {Colors.GREEN}{cause:<25}{Colors.RESET} │ {Colors.CYAN}{meaning:<30}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*98}╝{Colors.RESET}")


def show_playbooks_summary():
    """Display response playbooks summary"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' RESPONSE PLAYBOOKS SUMMARY':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    playbooks = [
        ("1. Database Connectivity Failure", [
            "Run: grep -i \"database.*fail|mysql.*error\" /var/log/asterisk/full | tail -20",
            "Check automated log analyzer for structured details",
            "Escalate with log snippet and concurrent GUI errors"
        ]),
        ("2. Trunk Offline / Registration Loss", [
            "Run: grep -E \"Registration.*failed|qualify.*Unreachable\" /var/log/asterisk/full",
            "Identify affected trunks and timestamps",
            "Notify carrier/network team for recovery"
        ]),
        ("3. Authentication Storm / SIP Attack", [
            "Run: grep -i \"failed.*auth|SECURITY\" /var/log/asterisk/full | tail -50",
            "If >20 failures, collect IP list for blocklisting",
            "Coordinate with security ops to block upstream"
        ]),
        ("4. Queue Abandon Spike", [
            "Run: tail -100 /var/log/asterisk/queue_log | grep -c ABANDON",
            "Use queue analyzer for current metrics",
            "Alert supervisor with wait times and staffing needs"
        ]),
    ]
    
    for title, steps in playbooks:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.GREEN}{Colors.BOLD}{title}{Colors.RESET}")
        for i, step in enumerate(steps, 1):
            print(f"{Colors.CYAN}║{Colors.RESET}   {Colors.YELLOW}{i}.{Colors.RESET} {Colors.WHITE}{step[:70]}{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═'*78}╣{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}")


def run_full_diagnostic():
    """Run comprehensive Asterisk diagnostic with formatted table output"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}")
    print(f"  🔧 Full Asterisk & FreePBX Diagnostic")
    print(f"{'='*80}{Colors.RESET}\n")
    
    print(f"{Colors.YELLOW}Collecting system information...{Colors.RESET}\n")

    sock = detect_mysql_socket()

    # System Information Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' SYSTEM INFORMATION':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")

    # Hostname
    rc, hostname, _ = run(["hostname"])
    hostname = hostname.strip() or "Unknown"
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Hostname:{Colors.RESET} {Colors.GREEN}{hostname:<64}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Uptime
    rc, uptime_out, _ = run(["uptime", "-p"])
    uptime_str = uptime_out.strip() or "Unknown"
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Uptime:{Colors.RESET} {Colors.YELLOW}{uptime_str:<66}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Memory
    rc, mem_out, _ = run(["free", "-h"])
    mem_lines = mem_out.strip().split('\n')
    if len(mem_lines) > 1:
        mem_info = mem_lines[1].split()
        if len(mem_info) >= 3:
            total_mem = mem_info[1]
            used_mem = mem_info[2]
            mem_display = f"Used: {used_mem} / Total: {total_mem}"
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Memory:{Colors.RESET} {Colors.CYAN}{mem_display:<67}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Disk usage
    rc, disk_out, _ = run(["df", "-h", "/"])
    disk_lines = disk_out.strip().split('\n')
    if len(disk_lines) > 1:
        disk_info = disk_lines[1].split()
        if len(disk_info) >= 5:
            disk_display = f"Used: {disk_info[2]} / Total: {disk_info[1]} ({disk_info[4]})"
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Disk (/):{Colors.RESET} {Colors.CYAN}{disk_display:<65}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Asterisk Information Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' ASTERISK STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    # Asterisk version
    rc, version_out, _ = run(["asterisk", "-rx", "core show version"])
    if rc == 0:
        version_lines = version_out.strip().split('\n')
        if version_lines:
            version = version_lines[0].replace("Asterisk ", "").strip()[:60]
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Version:{Colors.RESET} {Colors.GREEN}{version:<66}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Active channels
    rc, channels_out, _ = run(["asterisk", "-rx", "core show channels count"])
    active_calls = "0"
    active_channels = "0"
    for line in channels_out.split('\n'):
        if 'active call' in line.lower():
            parts = line.split()
            if parts and parts[0].isdigit():
                active_calls = parts[0]
        elif 'active channel' in line.lower():
            parts = line.split()
            if parts and parts[0].isdigit():
                active_channels = parts[0]
    
    call_color = Colors.GREEN if active_calls == "0" else Colors.YELLOW
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Active Calls:{Colors.RESET} {call_color}{active_calls:<63}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Active Channels:{Colors.RESET} {call_color}{active_channels:<59}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # PJSIP Endpoints
    rc, endpoints_out, _ = run(["asterisk", "-rx", "pjsip show endpoints"])
    endpoint_count = 0
    online_count = 0
    for line in endpoints_out.split('\n'):
        if line.strip() and not line.startswith('Endpoint') and not line.startswith('===') and not line.startswith('Objects'):
            endpoint_count += 1
            if 'Avail' in line or 'online' in line.lower():
                online_count += 1
    
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}PJSIP Endpoints:{Colors.RESET} {Colors.CYAN}Total: {endpoint_count}  │  Online: {Colors.GREEN}{online_count}{Colors.RESET}{' '*40}{Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Services Status Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' SERVICES STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    services = [
        ("asterisk", "Asterisk PBX"),
        ("httpd", "Apache Web Server"),
        ("mariadb", "MariaDB Database"),
        ("php-fpm", "PHP-FPM"),
        ("crond", "Cron Daemon")
    ]
    
    for service_name, display_name in services:
        rc, _, _ = run(["systemctl", "is-active", service_name])
        status = "RUNNING" if rc == 0 else "STOPPED"
        status_color = Colors.GREEN if rc == 0 else Colors.RED
        status_icon = "●" if rc == 0 else "○"
        
        print(f"{Colors.CYAN}║{Colors.RESET} {status_color}{status_icon}{Colors.RESET} {Colors.WHITE}{display_name:<35}{Colors.RESET} {status_color}{status:<36}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Database Status
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' DATABASE STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    # Check database connectivity
    rc, db_out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='asterisk';"])
    if rc == 0:
        table_count = db_out.strip()
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Asterisk DB Status:{Colors.RESET} {Colors.GREEN}Connected{Colors.RESET}{' '*52}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Tables in asterisk DB:{Colors.RESET} {Colors.CYAN}{table_count:<54}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Asterisk DB Status:{Colors.RESET} {Colors.RED}Connection Failed{Colors.RESET}{' '*45}{Colors.CYAN}║{Colors.RESET}")
    
    # Recent CDRs
    rc, cdr_out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", "SELECT COUNT(*) FROM asteriskcdrdb.cdr WHERE calldate > DATE_SUB(NOW(), INTERVAL 24 HOUR);"])
    if rc == 0:
        recent_calls = cdr_out.strip()
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}CDRs (Last 24h):{Colors.RESET} {Colors.YELLOW}{recent_calls:<58}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Module Status
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' ASTERISK MODULES (Key Modules)':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    key_modules = [
        "chan_pjsip.so",
        "res_pjsip.so",
        "chan_dahdi.so",
        "app_voicemail.so",
        "app_queue.so",
        "cdr_mysql.so"
    ]
    
    rc, modules_out, _ = run(["asterisk", "-rx", "module show"])
    loaded_modules = set()
    for line in modules_out.split('\n'):
        for mod in key_modules:
            if mod in line:
                loaded_modules.add(mod)
    
    for mod in key_modules:
        if mod in loaded_modules:
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.GREEN}✓{Colors.RESET} {Colors.WHITE}{mod:<70}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
        else:
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.RED}✗{Colors.RESET} {Colors.WHITE}{mod:<70}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    print(f"{Colors.GREEN}{Colors.BOLD}✓ Diagnostic complete!{Colors.RESET}\n")


def run_full_diagnostic_legacy():
    """Run the original shell script diagnostic (legacy method)"""
    diag = "/usr/local/bin/asterisk-full-diagnostic.sh"
    if not os.path.isfile(diag):
        print("Diagnostic script not found at", diag)
    else:
        print("\nRunning full diagnostic (this may take ~10-30s)...\n")
        # run_interactive (not run): the script prints its own section-by-section
        # output as it works — previously captured silently via run() and never
        # actually printed anywhere, so this produced no visible output at all.
        rc = run_interactive([diag])
        if rc != 0:
            print(f"{Colors.RED}Diagnostic script exited with code {rc}.{Colors.RESET}")


# ---------------- helpers ----------------

def run(cmd, env=None, timeout=None):
    """subprocess.run wrapper (3.6-safe: universal_newlines instead of text=)."""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        # No e.process – only e.cmd, e.timeout, e.output, e.stderr
        print("[DEBUG] Timeout running:", e.cmd, "after", e.timeout, "seconds")
        return 1, "", "Timeout running {}".format(e.cmd)


def run_interactive(cmd, env=None):
    """Run command with output streaming directly to terminal. Returns the
    exit code (existing callers that ignore the return value are unaffected)."""
    return subprocess.run(cmd, env=env).returncode


def run_with_spinner(cmd, label, env=None, timeout=None):
    """Like run(), but shows a spinner + elapsed time while the subprocess runs.

    For opaque single blocking calls that produce no progress output of their
    own (e.g. a plain MySQL dump, or waiting on a live call to set up) — where
    run() would otherwise leave the terminal looking frozen for however long
    the call takes. Do NOT use this for subprocesses that already print their
    own progress (those should use run_interactive() instead so their real
    output streams live; layering a spinner on top would visually collide
    with it). Returns the same (rc, out, err) tuple as run().

    Implementation runs the actual subprocess via subprocess.run() (which
    handles stdout/stderr draining correctly via communicate()) on a
    background thread, and only polls thread-liveness from the main thread
    to animate the spinner — this avoids the classic PIPE-deadlock risk of
    polling Popen.poll() directly without also draining its pipes.
    """
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    result = {}

    def _target():
        try:
            p = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, env=env, timeout=timeout,
            )
            result['rc'] = p.returncode
            result['out'] = p.stdout or ""
            result['err'] = p.stderr or ""
        except subprocess.TimeoutExpired as e:
            result['rc'] = 1
            result['out'] = ""
            result['err'] = f"Timeout running {e.cmd} after {e.timeout} seconds"
        except Exception as e:
            result['rc'] = 1
            result['out'] = ""
            result['err'] = str(e)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    interactive = sys.stdout.isatty()
    start = time.time()
    i = 0
    while thread.is_alive():
        if interactive:
            elapsed = time.time() - start
            frame = frames[i % len(frames)]
            sys.stdout.write(f"\r{Colors.CYAN}{frame} {label}... ({elapsed:.0f}s){Colors.RESET}")
            sys.stdout.flush()
            i += 1
        thread.join(timeout=0.1)

    if interactive:
        sys.stdout.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stdout.flush()

    return result.get('rc', 1), result.get('out', ""), result.get('err', "")


def detect_mysql_socket():
    rc, out, _ = run(["bash", "-lc", "mysql -NBe 'SHOW VARIABLES LIKE \"socket\";' 2>/dev/null | awk '{print $2}'"])
    path = (out.strip().splitlines() or [""])[0]
    return path if path else DEFAULT_SOCK

def ensure_outdir():
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
    except Exception:
        pass

def load_dump():
    if not os.path.isfile(DUMP_PATH):
        return {}
    with open(DUMP_PATH, "r") as f:
        return json.load(f)

def refresh_dump(sock):
    ensure_outdir()
    cmd = ["python3", DUMP_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--out", DUMP_PATH]
    rc, out, err = run_with_spinner(cmd, "Refreshing FreePBX data cache (reads MySQL)")
    if rc == 0:
        print("    ✓ Snapshot written to", DUMP_PATH)
        return True
    print("    ✖ Snapshot failed:\n" + (err or out))
    return False

def summarize(data):
    def count(key, sub=None):
        if key not in data: return 0
        if sub:
            return len(data[key].get(sub, []))
        return len(data[key])
    
    # Dramatic inventory display
    print("\n" + Colors.CYAN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "║" + (" � " + Colors.YELLOW + "SYSTEM INVENTORY" + Colors.CYAN).center(88) + "║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "Host:            " + Colors.RESET + Colors.GREEN + Colors.BOLD + data.get("meta", {}).get("hostname", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "freePBX version: " + Colors.RESET + Colors.YELLOW + Colors.BOLD + data.get("meta", {}).get("freepbx_version", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "MySQL version:   " + Colors.RESET + Colors.YELLOW + Colors.BOLD + data.get("meta", {}).get("mysql_version", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "Generated:       " + Colors.RESET + Colors.MAGENTA + data.get("meta", {}).get("generated_at_utc", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Inbound routes (DIDs):     " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("inbound")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "IVRs (menus):              " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ivrs", "menus")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "IVR options:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ivrs", "options")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Queues:                    " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("queues")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Ring groups:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ringgroups")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Time conditions:           " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("timeconditions")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Time groups:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("timegroups")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Announcements:             " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("announcements")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Extensions:                " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("extensions")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Trunks:                    " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("trunks", {}).get("trunks", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Outbound routes:           " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("outbound", {}).get("routes", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Outbound patterns:         " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("outbound", {}).get("patterns", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.RESET)
    print("")

_SORT_CYCLE = ['index', 'did', 'label', 'dest']

# Session state — persists across menu visits within one run
_SESSION = {"last_filter": "", "last_sort": "index", "last_did": ""}

# Dashboard live-data cache — avoid re-querying Asterisk on every menu render
_DASH_CACHE: dict = {"ts": 0.0}
_DASH_CACHE_TTL = 30  # seconds


def get_did_rows(data):
    """Extract DID rows from snapshot data without any display."""
    dids = data.get("inbound", [])
    rows = []
    for i, r in enumerate(dids, 1):
        rows.append((i, r.get("did", ""), r.get("label") or "", r.get("cid") or "", r.get("destination") or ""))
    return rows


def _decode_dest_from_cache(dest, data):
    """Map a FreePBX destination string to a human label using cached data."""
    if not dest or not data:
        return dest or ""
    parts = dest.split(",")
    ctx  = parts[0].strip()
    arg1 = parts[1].strip() if len(parts) > 1 else ""
    ctx_lower = ctx.lower()

    if ctx_lower == "timeconditions":
        for tc in (data.get("timeconditions") or []):
            if str(tc.get("timeconditions_id", "")) == arg1:
                return f"TC: {tc.get('displayname', arg1)}"

    if ctx_lower == "ext-group":
        for rg in (data.get("ringgroups") or []):
            if str(rg.get("grpnum", "")) == arg1:
                return f"RG: {rg.get('description', arg1)}"

    if ctx_lower.startswith("ivr-"):
        ivr_id = ctx[4:]
        for m in (data.get("ivrs", {}).get("menus") or []):
            if str(m.get("ivr_id", "")) == ivr_id:
                return f"IVR: {m.get('name', ivr_id)}"

    if ctx_lower == "ivr":
        for m in (data.get("ivrs", {}).get("menus") or []):
            if str(m.get("ivr_id", "")) == arg1:
                return f"IVR: {m.get('name', arg1)}"

    if ctx_lower == "ext-queues":
        for q in (data.get("queues") or []):
            if isinstance(q, dict) and str(q.get("queue", "")) == arg1:
                return f"Queue: {q.get('queue_name', arg1)}"

    if ctx_lower in ("app-announce", "ext-announce", "app-recordings-custom"):
        for ann in (data.get("announcements") or []):
            if str(ann.get("announcement_id", "")) == arg1:
                return f"Ann: {ann.get('description', arg1)}"

    if ctx_lower == "from-did-direct":
        for ext in (data.get("extensions") or []):
            if str(ext.get("extension", "")) == arg1:
                return f"Ext {arg1}: {ext.get('name', '')}".strip()
        return f"Ext: {arg1}"

    if ctx.isdigit():
        for ext in (data.get("extensions") or []):
            if str(ext.get("extension", "")) == ctx:
                return f"Ext {ctx}: {ext.get('name', '')}".strip()

    return dest


def _filter_rows(rows, query):
    q = query.strip().lower()
    if not q:
        return list(rows)
    return [r for r in rows if q in r[1].lower() or q in r[2].lower() or q in r[3].lower() or q in r[4].lower()]


def _sort_rows(rows, key):
    col = {'index': 0, 'did': 1, 'label': 2, 'cid': 3, 'dest': 4}.get(key, 0)
    return sorted(rows, key=lambda r: str(r[col]).lower())


def _show_did_detail(row):
    idx, did, label, cid, dest = row
    W = 64
    print(Colors.CYAN + "╔" + "═" * W + "╗" + Colors.RESET)
    print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW +
          f" DID Detail — Index {idx} ".center(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * W + "╣" + Colors.RESET)
    for field, val in [("DID", did), ("Label", label), ("CID", cid), ("Destination", dest)]:
        line = f"  {field:<14}: {val}"
        print(Colors.CYAN + "║" + Colors.WHITE + line.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╚" + "═" * W + "╝" + Colors.RESET)


def list_dids(data, show_limit=50):
    rows = get_did_rows(data)
    if not rows:
        print(Colors.RED + "❌ No inbound routes found." + Colors.RESET)
        return []
    if show_limit == 0:
        return rows

    page_size = show_limit
    active_filter = _SESSION.get("last_filter", "")
    sort_key = _SESSION.get("last_sort", "index")

    snap_age = get_snapshot_age_seconds()
    age_tag = f"cache: {format_age(snap_age)}" if snap_age is not None else "cache: unknown"

    def _tbl_header(shown, total, sk, af):
        meta = []
        if af:
            meta.append(f"filter: {af}")
        if sk != "index":
            meta.append(f"sort: {sk}")
        meta.append(age_tag)
        suffix = ("[" + ", ".join(meta) + "] ") if meta else ""
        count = f"({shown}" + (f"/{total}" if af else "") + ")"
        title = f" 📞 DID ROUTING TABLE {suffix}{count} "
        print(Colors.CYAN + "╔" + "═" * 115 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + title.center(115) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 115 + "╣" + Colors.RESET)
        print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE +
              "Index │ DID           │ Label                         │ CID   │ Destination (decoded)          " +
              Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 115 + "╣" + Colors.RESET)

    def _tbl_row(idx, did, label, cid, dest):
        decoded = _decode_dest_from_cache(dest, data)
        print(Colors.CYAN + "║ " + Colors.RESET + "{:>5} │ {:<13} │ {:<29} │ {:<5} │ {:<32}".format(
            idx, Colors.GREEN + did + Colors.RESET, label[:29], cid[:5], decoded[:32]) + Colors.CYAN + " ║" + Colors.RESET)

    def _next_sort():
        i = _SORT_CYCLE.index(sort_key) if sort_key in _SORT_CYCLE else 0
        return _SORT_CYCLE[(i + 1) % len(_SORT_CYCLE)]

    def _prompt(remaining):
        if remaining > 0:
            h = (f"... {remaining} more │ ENTER=next │ a=all │ "
                 f"f <text>=filter │ s=sort({sort_key}) │ d<N>=detail │ q=quit: ")
        else:
            h = "End of list │ ENTER=done │ f <text>=filter │ s=sort │ d<N>=detail: "
        return prompt(Colors.YELLOW + h + Colors.RESET).strip().lower()

    def _handle_detail(ans, display):
        try:
            n = int(ans[1:].strip())
            match = next((r for r in display if r[0] == n), None)
            if match:
                _show_did_detail(match)
                prompt(Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            else:
                print(Colors.RED + f"Index {n} not found in current view." + Colors.RESET)
        except ValueError:
            pass

    while True:  # outer: redo on filter/sort change
        display = _sort_rows(_filter_rows(rows, active_filter), sort_key)

        if not display:
            print(Colors.YELLOW + f"No results for '{active_filter}'. Press ENTER to clear filter." + Colors.RESET)
            prompt()
            active_filter = ""
            continue

        redo = False
        offset = 0

        while offset < len(display):
            page = display[offset:offset + page_size]
            _tbl_header(len(display), len(rows), sort_key, active_filter)
            for row in page:
                _tbl_row(*row)
            print(Colors.CYAN + "╚" + "═" * 115 + "╝" + Colors.RESET)

            next_offset = offset + page_size
            remaining = len(display) - next_offset

            while True:  # inner prompt loop — re-prompts after detail view
                ans = _prompt(remaining)
                if ans == "q":
                    return rows
                elif ans == "a" and remaining > 0:
                    _tbl_header(len(display), len(rows), sort_key, active_filter)
                    for row in display[next_offset:]:
                        _tbl_row(*row)
                    print(Colors.CYAN + "╚" + "═" * 115 + "╝" + Colors.RESET)
                    next_offset = len(display)
                    remaining = 0
                    continue  # fall through to end-of-list prompt
                elif ans.startswith("f"):
                    active_filter = ans[1:].strip() or prompt(Colors.YELLOW + "Filter (DID/label/dest, blank=clear): " + Colors.RESET).strip()
                    redo = True
                    break
                elif ans == "s":
                    sort_key = _next_sort()
                    print(Colors.CYAN + f"  → sorted by: {sort_key}" + Colors.RESET)
                    redo = True
                    break
                elif ans.startswith("d") and len(ans) > 1:
                    _handle_detail(ans, display)
                    continue  # re-show same prompt without advancing
                else:  # ENTER
                    break

            if redo:
                break
            offset = next_offset

        if redo:
            continue
        break

    _SESSION["last_filter"] = active_filter
    _SESSION["last_sort"] = sort_key
    return rows

def _normalize_did_digits(raw):
    """Strip non-digits and drop a leading '1' from an 11-digit NANP number, so
    DID entry matches regardless of formatting — mirrors the normalization used
    by the call-leg analyzer's --number search."""
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def _find_did_index(part, did_rows):
    """Resolve a typed DID/phone number (any formatting) to its 1-based index in
    the currently displayed did_rows list. Returns None if no DID matches — short
    inputs that don't look like a real DID (e.g. a bare '5') essentially never
    collide with an actual DID value, so trying this before falling back to plain
    index parsing is safe in practice."""
    target = _normalize_did_digits(part)
    if not target:
        return None
    for i, row in enumerate(did_rows, 1):
        if _normalize_did_digits(row[1]) == target:
            return i
    return None


def parse_selection(sel, did_rows):
    """Accepts index numbers/ranges (e.g. '1,3,5-8') AND/OR literal DID/phone
    numbers in any formatting, mixed freely in the same comma-separated input —
    e.g. '3,2485551212,7-9'. DID matching is tried first for each comma-separated
    part; ranges ('N-M') are always treated as index ranges, since a range of
    phone numbers wouldn't be meaningful here."""
    sel = sel.strip()
    max_index = len(did_rows)
    if sel in ("*", "all", "ALL"):
        return list(range(1, max_index+1))
    chosen = set()
    for part in sel.split(","):
        part = part.strip()
        if not part: continue
        if "-" in part and re.fullmatch(r"\d+-\d+", part):
            a,b = part.split("-",1)
            try:
                a, b = int(a), int(b)
                # Clamp to [1, max_index] BEFORE iterating — a's/b's could be
                # arbitrarily large (a mistyped or dash-formatted phone number
                # looks exactly like "N-M" here), and iterating an unclamped
                # multi-billion-entry range while filtering each value pegs
                # the CPU for minutes instead of erroring.
                lo = max(min(a,b), 1)
                hi = min(max(a,b), max_index)
                for x in range(lo, hi+1):
                    chosen.add(x)
            except ValueError:
                pass
            continue
        did_idx = _find_did_index(part, did_rows)
        if did_idx is not None:
            chosen.add(did_idx)
            continue
        try:
            x = int(part)
            if 1 <= x <= max_index: chosen.add(x)
        except ValueError:
            pass
    return sorted(chosen)

def render_dids(did_rows, indexes, sock, skip_labels=None):
    ensure_outdir()
    ok = 0
    bad = 0
    ok_files = []
    total = len(indexes)
    for i, idx in enumerate(indexes, 1):
        _, did, label, _, _ = did_rows[idx-1]

        if skip_labels and label and label.strip().lower() in skip_labels:
            print(f"• Skipping DID {did} (label='{label}')")
            continue

        out_file = os.path.join(OUT_DIR, f"callflow_{did}.svg")

        print_progress_bar(i, total, f"Rendering DID {did}")

        cmd = [
            "python3",
            GRAPH_SCRIPT,
            "--socket", sock,
            "--db-user", DB_USER,
            "--did", str(did),
            "--out", out_file,
        ]

        # Put a per-DID timeout on the graph generator
        rc, out, err = run(cmd, timeout=120)

        if rc == 0 and os.path.isfile(out_file):
            print(f"\n✓ DID {did} -> {out_file}")
            ok += 1
            ok_files.append(out_file)
        else:
            print(f"\n✖ DID {did} FAILED: {(err or out).strip()}")
            bad += 1

    print(f"\nDone. Success: {ok}, Failed: {bad}")
    if len(ok_files) == 1:
        maybe_email_file(ok_files[0], default_subject="freepbx-tools: call-flow diagram")
    elif len(ok_files) > 1:
        zip_path = os.path.join(OUT_DIR, f"callflows_{int(time.time())}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in ok_files:
                zf.write(f, arcname=os.path.basename(f))
        maybe_email_file(zip_path, default_subject="freepbx-tools: call-flow diagrams")


def get_service_status(services):
    """Get status of system services"""
    status_list = []
    for service in services:
        variations = [service]
        if service == "asterisk":
            variations = ["asterisk", "asterisk16", "asterisk18", "asterisk20"]
        elif service == "php-fpm":
            variations = ["php-fpm", "php73-php-fpm", "php74-php-fpm", "php80-php-fpm", "rh-php73-php-fpm"]

        found = False
        for variant in variations:
            try:
                cmd = ["systemctl", "is-active", variant]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      universal_newlines=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip() == "active":
                    status_list.append((service, "running", Colors.GREEN))
                    found = True
                    break
            except Exception:
                pass

        if not found:
            try:
                for variant in variations:
                    cmd = ["service", variant, "status"]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          universal_newlines=True, timeout=2)
                    if result.returncode == 0:
                        status_list.append((service, "running", Colors.GREEN))
                        found = True
                        break
            except Exception:
                pass

        # Asterisk-specific fallback: CLI ping proves it's running even if systemd
        # unit name doesn't match any variant (e.g. custom build or init.d start)
        if not found and service == "asterisk":
            try:
                r = subprocess.run(["asterisk", "-rx", "core show uptime"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    status_list.append((service, "running", Colors.GREEN))
                    found = True
            except Exception:
                pass

        if not found:
            status_list.append((service, "stopped", Colors.RED))

    return status_list

def get_active_calls(sock):
    """Get count of active calls from Asterisk"""
    try:
        cmd = ["asterisk", "-rx", "core show channels count"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)
        if result.returncode != 0:
            return None
        output = result.stdout or ""
        # Parse output like "2 active channels" or "0 active calls"
        for line in output.split('\n'):
            if 'active call' in line.lower() or 'active channel' in line.lower():
                parts = line.split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
    except Exception:
        pass
    return None

def get_time_conditions_status(sock):
    """Get time conditions count using direct MySQL query - returns (total_count, forced_count, status_list)"""
    try:
        sql = "SELECT COUNT(*) FROM timeconditions"
        cmd = ["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql, "asterisk"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)

        if result.returncode != 0 or not result.stdout.strip():
            err_msg = result.stderr.strip()[:50] if result.stderr else "Query failed"
            return (0, 0, ["DB Error: " + err_msg])

        total_count = int(result.stdout.strip())

        # Now get forced count (schema varies; fail gracefully)
        forced_count = 0
        sql2 = "SELECT COUNT(*) FROM timeconditions WHERE inuse_state IN (1,2)"
        cmd2 = ["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql2, "asterisk"]
        result2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True, timeout=5)
        if result2.returncode == 0 and (result2.stdout or "").strip():
            try:
                forced_count = int(result2.stdout.strip())
            except Exception:
                forced_count = 0
        
        # Build status display
        status_display = []
        if total_count > 0:
            if forced_count > 0:
                status_display.append("{} Total | {} Override | {} Auto".format(total_count, forced_count, total_count - forced_count))
            else:
                status_display.append("{} Total | All running on schedule".format(total_count))
        else:
            status_display.append("No time conditions found")
        
        return (total_count, forced_count, status_display)
    except Exception as e:
        return (0, 0, ["Error: " + str(e)[:50]])

def get_recent_package_updates():
    """Get recent Asterisk/FreePBX package updates from system package manager"""
    import datetime
    updates = []
    
    try:
        # Try yum/dnf history first (RHEL/CentOS)
        cmd = ["yum", "history", "list", "asterisk*"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              universal_newlines=True, timeout=5)
        
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            # Parse yum history output
            for line in lines:
                if 'asterisk' in line.lower() and ('install' in line.lower() or 'update' in line.lower()):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        # Extract date and action
                        date_str = parts[1].strip() if len(parts) > 1 else ""
                        action = parts[2].strip() if len(parts) > 2 else ""
                        
                        # Parse date and calculate time ago
                        try:
                            # Date format: 2025-10-17 12:17
                            update_time = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            now = datetime.datetime.now()
                            delta = now - update_time
                            
                            if delta.days == 0:
                                time_ago = "today"
                            elif delta.days == 1:
                                time_ago = "yesterday"
                            elif delta.days < 7:
                                time_ago = "{}d ago".format(delta.days)
                            elif delta.days < 30:
                                time_ago = "{}w ago".format(delta.days // 7)
                            else:
                                time_ago = "{}mo ago".format(delta.days // 30)
                            
                            updates.append("Asterisk {} ({})".format(action.lower(), time_ago))
                            if len(updates) >= 5:
                                break
                        except Exception:
                            pass
        
        # If no yum history, try rpm query
        if not updates:
            cmd = ["rpm", "-qa", "--last", "asterisk*"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True, timeout=5)
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')[:5]  # Get first 5
                for line in lines:
                    if line:
                        # Format: package-name date
                        parts = line.split()
                        if parts:
                            pkg = parts[0]
                            # Extract version from package name
                            updates.append(pkg)
    
    except Exception:
        pass
    
    return updates if updates else ["No package history found"]

def get_endpoint_status(sock):
    """Get SIP endpoint registration status"""
    try:
        sql = "SELECT extension, name FROM users ORDER BY CAST(extension AS UNSIGNED)"
        cmd = ["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql, "asterisk"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)
        
        if result.returncode != 0 or not result.stdout.strip():
            return {"registered": 0, "unregistered": 0, "total": 0, "details": []}
        
        extensions = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 1:
                    ext = parts[0]
                    name = parts[1] if len(parts) > 1 else ""
                    extensions.append((ext, name))
        
        # Check registration status via Asterisk
        registered = []
        unregistered = []

        # PJSIP: try contacts first; "No such command" in output means chan_sip system
        contact_endpoints = set()
        pjsip_active = False
        rc, out, _ = run(["asterisk", "-rx", "pjsip show contacts"], timeout=5)
        if rc == 0 and out and "no such command" not in out.lower():
            pjsip_active = True
            for line in out.split('\n'):
                line = line.strip()
                if not line.startswith("Contact:"):
                    continue
                # "Contact: 100/sip:100@1.2.3.4:5060" -> endpoint "100"
                rest = line[len("Contact:"):].strip()
                endpoint = rest.split('/', 1)[0].strip()
                if endpoint:
                    contact_endpoints.add(endpoint)

        # chan_sip fallback — only on systems that don't have PJSIP at all
        sip_ok = set()
        if not pjsip_active:
            rc2, out2, _ = run(["asterisk", "-rx", "sip show peers"], timeout=5)
            if rc2 == 0 and out2 and "no such command" not in out2.lower():
                for line in out2.split('\n'):
                    if not line.strip() or line.lower().startswith("name/"):
                        continue
                    parts = line.split()
                    if not parts:
                        continue
                    name = parts[0].split('/', 1)[0].strip()
                    status = parts[-1].strip() if parts else ""
                    if name and ("ok" in status.lower() or "unknown" in status.lower()):
                        sip_ok.add(name)

        # Match extensions with registration status
        for ext, name in extensions:
            if contact_endpoints:
                if ext in contact_endpoints:
                    registered.append((ext, name, "Registered"))
                else:
                    unregistered.append((ext, name, "Unregistered"))
            elif sip_ok:
                if ext in sip_ok:
                    registered.append((ext, name, "OK"))
                else:
                    unregistered.append((ext, name, "Unregistered"))
            else:
                # Asterisk may be stopped / CLI not available
                unregistered.append((ext, name, "N/A"))
        
        return {
            "registered": len(registered),
            "unregistered": len(unregistered),
            "total": len(extensions),
            "details": registered + unregistered
        }
    
    except Exception:
        return {"registered": 0, "unregistered": 0, "total": 0, "details": []}

def get_trunk_status(sock):
    """Return (online, total) trunk registration counts."""
    try:
        rc, out, _ = run(["asterisk", "-rx", "pjsip show registrations"], timeout=5)
        if rc == 0 and out:
            online = sum(1 for l in out.split('\n') if 'Registered' in l)
            total = sum(1 for l in out.split('\n') if re.search(r'^\s*\S+.*sip', l, re.IGNORECASE))
            if total == 0:
                total = out.lower().count('sip')
            return online, max(online, total)
        # fallback: chan_sip
        rc2, out2, _ = run(["asterisk", "-rx", "sip show registry"], timeout=5)
        if rc2 == 0 and out2:
            online = sum(1 for l in out2.split('\n') if 'Registered' in l)
            total = sum(1 for l in out2.split('\n')
                        if l.strip() and not l.lower().startswith('host') and not l.startswith('-'))
            return online, max(online, total)
    except Exception:
        pass
    return None, None


def get_recent_error_count():
    """Return count of ERROR lines in last 200 lines of Asterisk full log, or None."""
    try:
        log = "/var/log/asterisk/full"
        if not os.path.isfile(log):
            return None
        result = subprocess.run(
            ["bash", "-c", f"tail -200 {log} | grep -c ERROR"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=5)
        if result.returncode in (0, 1):
            return int(result.stdout.strip() or 0)
    except Exception:
        pass
    return None


def display_system_dashboard(sock, data):
    """Display key system information in a professional tile-based dashboard layout"""
    import os
    import shutil
    
    # Detect terminal width dynamically
    try:
        term_width = shutil.get_terminal_size().columns
    except:
        term_width = 160  # Default fallback
    
    # Calculate optimal tile width based on terminal (3 tiles + borders + separators)
    # Formula: term_width = 3*TILE_WIDTH + 6 (borders) + 6 (separators)
    TILE_WIDTH = max(48, (term_width - 12) // 3)  # Minimum 48 chars per tile (increased from 36)
    BOX_TOTAL = (TILE_WIDTH * 3) + 12  # Total width for perfect alignment
    
    # Clear screen and display ASCII Art Logo
    print("\033[2J\033[H")  # Clear screen
    print(Colors.CYAN + Colors.BOLD)
    print("    ______              ____  ______  __  __      _____           __    ")
    print("   / ____/_______  ____/ __ \\/ __ ) \\/ / /      /_  __/___  ____/ /____")
    print("  / /_  / ___/ _ \\/ __  / / / / __  |\\  /_/      / / / __ \\/ __ / / ___/")
    print(" / __/ / /  /  __/ /_/ / /_/ / /_/ / / /__/     / / / /_/ / /_/ / (__  ) ")
    print("/_/   /_/   \\___/\\____/_____/_____/ /_/   /    /_/  \\____/\\____/_/____/  ")
    print(Colors.RESET)
    
    # Get meta info (prefer live versions; fall back to snapshot meta)
    meta = data.get("meta", {}) if data else {}
    hostname = meta.get("hostname", "Unknown")
    freepbx_ver = get_freepbx_version_live() or meta.get("freepbx_version", "N/A")
    asterisk_ver = get_asterisk_version_live() or meta.get("asterisk_version", "N/A")
    tool_ver = get_tool_version()

    # Dashboard Header with system info - full width, properly aligned
    header_text = f"📊 SYSTEM DASHBOARD  │  Host: {hostname[:25].ljust(25)}  │  FreePBX: {freepbx_ver[:15].ljust(15)}  │  Asterisk: {asterisk_ver[:30].ljust(30)}"
    if tool_ver:
        header_text += f"  │  Tools: {tool_ver}"
    # Pad to full terminal width
    header_padding = " " * max(0, BOX_TOTAL - len(header_text) - 2)
    header_line = (Colors.BG_CYAN + Colors.WHITE + Colors.BOLD + 
                   " " + header_text + header_padding + " " + Colors.RESET)
    print("\n" + header_line)
    print(Colors.CYAN + "─" * BOX_TOTAL + Colors.RESET)
    
    # Get all data — use cache if fresh, otherwise re-query
    _now = time.time()
    if _now - _DASH_CACHE.get("ts", 0) < _DASH_CACHE_TTL:
        active_calls   = _DASH_CACHE["active_calls"]
        tc_total       = _DASH_CACHE["tc_total"]
        forced_count   = _DASH_CACHE["forced_count"]
        tc_status_list = _DASH_CACHE["tc_status_list"]
        endpoint_status = _DASH_CACHE["endpoint_status"]
        service_status  = _DASH_CACHE["service_status"]
        trunk_online    = _DASH_CACHE["trunk_online"]
        trunk_total     = _DASH_CACHE["trunk_total"]
        recent_errors   = _DASH_CACHE["recent_errors"]
    else:
        active_calls = get_active_calls(sock)
        tc_total, forced_count, tc_status_list = get_time_conditions_status(sock)
        endpoint_status = get_endpoint_status(sock)
        services = ["asterisk", "httpd", "mariadb", "fail2ban", "php-fpm", "crond"]
        service_status = get_service_status(services)
        trunk_online, trunk_total = get_trunk_status(sock)
        recent_errors = get_recent_error_count()
        _DASH_CACHE.update({
            "ts": _now, "active_calls": active_calls,
            "tc_total": tc_total, "forced_count": forced_count, "tc_status_list": tc_status_list,
            "endpoint_status": endpoint_status, "service_status": service_status,
            "trunk_online": trunk_online, "trunk_total": trunk_total, "recent_errors": recent_errors,
        })
    
    # Calculate metrics
    ep_total = endpoint_status["total"]
    ep_registered = endpoint_status["registered"]
    ep_unreg = endpoint_status["unregistered"]
    ep_pct = int((ep_registered / ep_total) * 100) if ep_total > 0 else 0
    running_count = sum(1 for _, status, _ in service_status if status == "running")
    stopped_count = sum(1 for _, status, _ in service_status if status == "stopped")
    
    # Inventory counts
    dids_count = len(data.get("inbound", [])) if data else 0
    ext_count = len(data.get("extensions", [])) if data else 0
    rg_count = len(data.get("ringgroups", [])) if data else 0
    ivr_count = len(data.get("ivrs", {}).get("menus", [])) if data else 0
    queue_count = len(data.get("queues", [])) if data else 0
    trunks_count = len(data.get("trunks", {}).get("trunks", [])) if data else 0
    
    # ====================
    # ROW 1: 3 Tiles - Active Calls | Time Conditions | Endpoints
    # ====================
    print("\n" + Colors.CYAN + "╔" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╗" + Colors.RESET)
    
    # Tile headers
    h1 = "📞  ACTIVE CALLS"
    h2 = "⏰  TIME CONDITIONS"
    h3 = "📱  ENDPOINT REGISTRATIONS"
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.GREEN + h1.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + 
          " ║ " + Colors.BOLD + Colors.MAGENTA + h2.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.BLUE + h3.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╣" + Colors.RESET)
    
    # Color logic
    call_color = Colors.RED if active_calls and active_calls > 10 else Colors.GREEN if active_calls and active_calls > 0 else Colors.CYAN
    tc_color = Colors.YELLOW if forced_count > 0 else Colors.GREEN
    ep_color = Colors.GREEN if ep_pct > 80 else Colors.YELLOW if ep_pct > 50 else Colors.RED
    
    # Build simple, clean tiles - just numbers and labels
    # Row 1 - Big numbers centered
    call_num = str(active_calls if active_calls is not None else "N/A")
    tc_num = str(tc_total)
    ep_num = str(ep_total)
    
    r1_c1 = pad_ansi(f"{call_color}{Colors.BOLD}{call_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r1_c2 = pad_ansi(f"{tc_color}{Colors.BOLD}{tc_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r1_c3 = pad_ansi(f"{Colors.WHITE}{Colors.BOLD}{ep_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r1_c1 + Colors.CYAN + " ║ " + r1_c2 + Colors.CYAN + " ║ " + r1_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Row 2 - Status text
    call_status = "ACTIVE" if active_calls and active_calls > 0 else "IDLE"
    r2_c1 = pad_ansi(f"{call_color}{call_status}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r2_c2 = pad_ansi(f"{Colors.WHITE}Time Conditions{Colors.RESET}", TILE_WIDTH-2, align='center')
    r2_c3 = pad_ansi(f"{Colors.WHITE}Endpoints{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r2_c1 + Colors.CYAN + " ║ " + r2_c2 + Colors.CYAN + " ║ " + r2_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Separator
    sep = "─" * (TILE_WIDTH-2)
    print(Colors.CYAN + "║ " + sep + " ║ " + sep + " ║ " + sep + " ║" + Colors.RESET)
    
    # Row 3 - Details (centered under the title)
    forced_color = Colors.YELLOW if forced_count > 0 else Colors.GREEN
    r3_c1 = pad_ansi(f"Channels: {call_color}{Colors.BOLD}{call_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r3_c2 = pad_ansi(f"Forced: {forced_color}{Colors.BOLD}{forced_count}{Colors.RESET}  Auto: {Colors.GREEN}{Colors.BOLD}{tc_total - forced_count}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r3_c3 = pad_ansi(f"Online: {ep_color}{Colors.BOLD}{ep_registered}{Colors.RESET} ({ep_pct}%)", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r3_c1 + Colors.CYAN + " ║ " + r3_c2 + Colors.CYAN + " ║ " + r3_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Row 4
    r4_c1 = pad_ansi("", TILE_WIDTH-2)
    r4_c2 = pad_ansi("", TILE_WIDTH-2)
    r4_c3 = pad_ansi(f"Offline: {Colors.RED}{Colors.BOLD}{ep_unreg}{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r4_c1 + Colors.CYAN + " ║ " + r4_c2 + Colors.CYAN + " ║ " + r4_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    print(Colors.CYAN + "╚" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╝" + Colors.RESET)
    
    # ====================
    # ROW 2: 3 Tiles - Services | Inventory | Key Paths
    # ====================
    print(Colors.CYAN + "╔" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╗" + Colors.RESET)
    
    # Tile headers
    h1 = "⚙️  SYSTEM SERVICES"
    h2 = "📊  SYSTEM INVENTORY"
    h3 = "📁  KEY PATHS"
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.YELLOW + h1.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.CYAN + h2.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.GREEN + h3.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╣" + Colors.RESET)
    
    # File path checks
    snapshot_exists = os.path.exists(DUMP_PATH)
    snapshot_size = os.path.getsize(DUMP_PATH) / (1024 * 1024) if snapshot_exists else 0
    snapshot_age = get_snapshot_age_seconds()
    
    paths_to_check = [
        ("/etc/asterisk/", "Config", 16),
        ("/var/log/asterisk/full", "Full Log", 22),
        ("/var/spool/asterisk/monitor/", "Recordings", 27),
        ("/var/lib/mysql/asterisk/", "DB Directory", 23),
        (sock, "MySQL Socket", len(sock))
    ]
    
    # Data rows (6 rows - matching service count)
    inventory_items = [
        ("DIDs", dids_count),
        ("Extensions", ext_count),
        ("Ring Groups", rg_count),
        ("IVRs", ivr_count),
        ("Queues", queue_count),
        ("Trunks", trunks_count)
    ]
    
    for i in range(6):
        # Service column - cleaner format
        if i < len(service_status):
            svc_name, svc_stat, svc_color = service_status[i]
            status_icon = "●" if svc_stat == "running" else "○"
            stat_text = svc_stat[:7].upper()
            svc_line = pad_ansi(f"{svc_color}{status_icon} {Colors.WHITE}{svc_name.ljust(18)}{svc_color}{Colors.BOLD}{stat_text.rjust(12)}{Colors.RESET}", TILE_WIDTH-2)
        else:
            svc_line = pad_ansi("", TILE_WIDTH-2)
        
        # Inventory column - better spacing (label left, count right with reasonable gap)
        if i < len(inventory_items):
            inv_label, inv_count = inventory_items[i]
            inv_line = pad_ansi(f"{Colors.WHITE}{inv_label.ljust(18)}{Colors.CYAN}{Colors.BOLD}{str(inv_count).rjust(10)}{Colors.RESET}", TILE_WIDTH-2)
        else:
            inv_line = pad_ansi("", TILE_WIDTH-2)
        
        # Paths column - abbreviated paths
        if i == 0:
            snap_icon = Colors.GREEN + "✓" if snapshot_exists else Colors.RED + "✗"
            path_line = pad_ansi(
                f"{snap_icon}{Colors.WHITE} Snapshot {Colors.CYAN}({snapshot_size:.1f} MB, age {format_age(snapshot_age)}){Colors.RESET}",
                TILE_WIDTH-2,
            )
        elif i - 1 < len(paths_to_check):
            path, label, path_len = paths_to_check[i - 1]
            exists = os.path.exists(path)
            icon = Colors.GREEN + "✓" if exists else Colors.RED + "✗"
            # Shorten paths intelligently
            if "asterisk/full" in path:
                path_display = "...asterisk/full"
            elif "mysql.sock" in path:
                path_display = "mysql.sock"
            elif "monitor" in path:
                path_display = "...monitor/"
            elif "/etc/asterisk" in path:
                path_display = "/etc/asterisk/"
            elif "mysql/asterisk" in path:
                path_display = "...mysql/asterisk/"
            else:
                path_display = path[-28:] if len(path) > 28 else path
            path_line = pad_ansi(f"{icon}{Colors.WHITE} {label.ljust(14)}{Colors.CYAN}{path_display}{Colors.RESET}", TILE_WIDTH-2)
        else:
            path_line = pad_ansi("", TILE_WIDTH-2)
        
        print(Colors.CYAN + "║ " + svc_line + Colors.CYAN + " ║ " + inv_line + Colors.CYAN + " ║ " + path_line + Colors.CYAN + " ║" + Colors.RESET)
    
    print(Colors.CYAN + "╚" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╝" + Colors.RESET)
    
    # ====================
    # Status Summary Bar
    # ====================
    status_parts = []
    
    # System Health
    if running_count >= 5 and active_calls is not None and ep_pct > 70:
        health = Colors.GREEN + Colors.BOLD + "GOOD" + Colors.RESET
    elif running_count >= 4 and ep_pct > 50:
        health = Colors.YELLOW + Colors.BOLD + "WARNING" + Colors.RESET
    else:
        health = Colors.RED + Colors.BOLD + "CRITICAL" + Colors.RESET
    status_parts.append("✓ System Health: " + health)
    
    # Services
    svc_status = (Colors.GREEN + str(running_count) + " Running" + Colors.RESET + " | " +
                  Colors.RED + str(stopped_count) + " Stopped" + Colors.RESET)
    status_parts.append("⚙️  Services: " + svc_status)
    
    # Forced TCs
    if forced_count == 0:
        tc_display = Colors.GREEN + "None" + Colors.RESET
    elif forced_count < 3:
        tc_display = Colors.YELLOW + str(forced_count) + Colors.RESET
    else:
        tc_display = Colors.RED + Colors.BOLD + str(forced_count) + Colors.RESET
    status_parts.append("⏰ Forced TCs: " + tc_display)
    
    # Endpoint Health
    if ep_pct > 80:
        ep_display = Colors.GREEN + str(ep_pct) + "%" + Colors.RESET
    elif ep_pct > 50:
        ep_display = Colors.YELLOW + str(ep_pct) + "%" + Colors.RESET
    else:
        ep_display = Colors.RED + Colors.BOLD + str(ep_pct) + "%" + Colors.RESET
    status_parts.append("📱 Endpoint Health: " + ep_display)

    # Trunk status
    if trunk_online is not None and trunk_total is not None:
        if trunk_total == 0:
            trunk_display = Colors.YELLOW + "N/A" + Colors.RESET
        elif trunk_online == trunk_total:
            trunk_display = Colors.GREEN + f"{trunk_online}/{trunk_total}" + Colors.RESET
        elif trunk_online > 0:
            trunk_display = Colors.YELLOW + f"{trunk_online}/{trunk_total}" + Colors.RESET
        else:
            trunk_display = Colors.RED + Colors.BOLD + f"0/{trunk_total}" + Colors.RESET
        status_parts.append("📡 Trunks: " + trunk_display)

    # Recent errors badge
    if recent_errors is not None:
        if recent_errors == 0:
            err_display = Colors.GREEN + "0" + Colors.RESET
        elif recent_errors < 10:
            err_display = Colors.YELLOW + str(recent_errors) + Colors.RESET
        else:
            err_display = Colors.RED + Colors.BOLD + str(recent_errors) + Colors.RESET
        status_parts.append("⚠ Errors(200L): " + err_display)

    print("\n  " + "  │  ".join(status_parts))
    print("")


def run_stuck_channels_inline():
    """Show channels that have been up longer than STUCK_MINUTES."""
    STUCK_MINUTES = 30
    print(f"\n{Colors.CYAN}Querying active channels...{Colors.RESET}")
    rc, out, _ = run(["asterisk", "-rx", "core show channels verbose"], timeout=8)
    if rc != 0 or not out:
        print(f"{Colors.YELLOW}Could not query Asterisk channels.{Colors.RESET}")
        return

    stuck = []
    for line in out.split('\n'):
        # Skip headers and summary lines
        if not line.strip() or line.startswith('Channel') or line.startswith('--') or 'active call' in line.lower():
            continue
        parts = line.split()
        # verbose format: Channel App AppData Duration(hh:mm:ss) Accountcode BridgeID ...
        # Duration is usually in position 3 or 4
        for p in parts:
            m = re.match(r'^(\d{2,3}):(\d{2}):(\d{2})$', p)
            if m:
                hours, mins, secs = int(m.group(1)), int(m.group(2)), int(m.group(3))
                total_minutes = hours * 60 + mins + secs / 60
                if total_minutes >= STUCK_MINUTES:
                    stuck.append((line.strip(), total_minutes))
                break

    W = 90
    print(Colors.CYAN + "╔" + "═" * W + "╗" + Colors.RESET)
    title = f" 🔴 STUCK CHANNELS (>{STUCK_MINUTES}m) — {len(stuck)} found "
    print(Colors.CYAN + "║" + Colors.BOLD + Colors.RED + title.center(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * W + "╣" + Colors.RESET)
    if not stuck:
        print(Colors.CYAN + "║" + Colors.GREEN + "  ✓ No stuck channels detected.".ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    else:
        for raw, mins in sorted(stuck, key=lambda x: x[1], reverse=True):
            label = f"  {int(mins):>4}m  {raw[:W - 9]}"
            print(Colors.CYAN + "║" + Colors.YELLOW + label.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╚" + "═" * W + "╝" + Colors.RESET)


def run_fail2ban_status_inline():
    """Show fail2ban jail status for SIP-related jails."""
    jails_to_check = ["asterisk", "sip-auth", "freepbx"]

    print(f"\n{Colors.CYAN}Querying fail2ban...{Colors.RESET}")

    # Get list of active jails
    rc, out, _ = run(["fail2ban-client", "status"], timeout=5)
    if rc != 0:
        print(f"{Colors.YELLOW}fail2ban-client not available or not running.{Colors.RESET}")
        return

    active_jails = []
    for line in out.split('\n'):
        if 'Jail list:' in line:
            jails_str = line.split(':', 1)[-1].strip()
            active_jails = [j.strip() for j in jails_str.split(',') if j.strip()]
            break

    # Check configured jails, fallback to all active jails if none match
    targets = [j for j in jails_to_check if j in active_jails] or active_jails[:5]

    W = 72
    print(Colors.CYAN + "╔" + "═" * W + "╗" + Colors.RESET)
    print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW +
          " 🔒 FAIL2BAN STATUS ".center(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * W + "╣" + Colors.RESET)

    if not targets:
        print(Colors.CYAN + "║" + Colors.GREEN + "  ✓ No relevant jails found.".ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    else:
        for jail in targets:
            rc2, detail, _ = run(["fail2ban-client", "status", jail], timeout=5)
            if rc2 != 0:
                continue
            currently_banned = 0
            total_banned = 0
            banned_ips = []
            for ln in detail.split('\n'):
                if 'Currently banned:' in ln:
                    try: currently_banned = int(ln.split(':')[-1].strip())
                    except ValueError: pass
                elif 'Total banned:' in ln:
                    try: total_banned = int(ln.split(':')[-1].strip())
                    except ValueError: pass
                elif 'Banned IP list:' in ln:
                    ips_str = ln.split(':', 1)[-1].strip()
                    banned_ips = [ip for ip in ips_str.split() if ip]

            color = Colors.RED if currently_banned > 0 else Colors.GREEN
            header = f"  Jail: {jail:<20} Currently banned: {color}{currently_banned}{Colors.WHITE}  Total: {total_banned}"
            print(Colors.CYAN + "║" + Colors.WHITE + header.ljust(W + len(color) + len(Colors.WHITE)) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
            for ip in banned_ips[:8]:
                print(Colors.CYAN + "║" + Colors.YELLOW + f"    Banned: {ip}".ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)

    print(Colors.CYAN + "╚" + "═" * W + "╝" + Colors.RESET)


def run_inline_log_analysis_timed(hours=1):
    """Inline log analysis with configurable time window."""
    from collections import defaultdict

    full_log = "/var/log/asterisk/full"
    if not os.path.isfile(full_log):
        print(f"{Colors.RED}Log not found: {full_log}{Colors.RESET}")
        return

    tail_lines = min(max(hours * 5000, 1000), 50000)

    print(f"\n{Colors.CYAN}📊 Inline log analysis — last ~{hours}h (~{tail_lines} lines){Colors.RESET}\n")

    def _grep(pattern, lines=None):
        n = lines or tail_lines
        cmd = f"tail -{n} {full_log} | grep -iE '{pattern}'"
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        return r.stdout.strip().split('\n') if r.stdout.strip() else []

    # Errors
    errors = _grep(r'ERROR|CRITICAL')
    if errors:
        etype = defaultdict(int)
        for e in errors:
            m = re.search(r'(ERROR|CRITICAL)[^:]*:\s*(.+)', e)
            if m:
                etype[m.group(2)[:80]] += 1
        print(f"{Colors.RED}🔴 {len(errors)} error(s):{Colors.RESET}")
        for msg, cnt in sorted(etype.items(), key=lambda x: x[1], reverse=True)[:8]:
            print(f"   {cnt:>4}x {sanitize_for_terminal(msg)}")
    else:
        print(f"{Colors.GREEN}✅ No errors{Colors.RESET}")

    # Registration failures
    reg_fails = _grep(r'failed.*register|registration.*failed|401.*REGISTER|403.*REGISTER', lines=tail_lines)
    if reg_fails:
        print(f"\n{Colors.YELLOW}⚠  {len(reg_fails)} registration failure(s) — last 3:{Colors.RESET}")
        for l in reg_fails[-3:]:
            print(f"   {sanitize_for_terminal(l[:120])}")
    else:
        print(f"\n{Colors.GREEN}✅ No registration failures{Colors.RESET}")

    # Auth/security events
    sec = _grep(r'failed.*auth|SECURITY|auth.*failed|SecurityEvent')
    ips = defaultdict(int)
    for l in sec:
        m = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', l)
        if m:
            ips[m.group(1)] += 1
    if ips:
        top = sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"\n{Colors.RED}🔒 Auth failures by IP:{Colors.RESET}")
        for ip, cnt in top:
            print(f"   {ip:<20} {cnt} attempts")
    else:
        print(f"\n{Colors.GREEN}✅ No auth failures{Colors.RESET}")

    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}✅ Inline analysis complete{Colors.RESET}")


def run_log_analysis():
    """Run automated log analysis to detect issues"""
    analyzer_script = "/usr/local/123net/freepbx-tools/bin/freepbx_log_analyzer.py"
    
    if not os.path.isfile(analyzer_script):
        print(Colors.YELLOW + "\n⚠️  Log analyzer not found. Running inline analysis..." + Colors.RESET)
        run_inline_log_analysis()
        return
    
    print(f"\n{Colors.CYAN}🔍 Running automated log analysis...{Colors.RESET}")
    print("=" * 60)
    
    rc, out, err = run(["python3", analyzer_script])
    
    if rc == 0:
        print(out)
    else:
        print(f"{Colors.RED}Error running analysis:{Colors.RESET}")
        print(err or out)
    
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    prompt()


def run_inline_log_analysis():
    """Inline log analysis when standalone script not available"""
    from collections import defaultdict
    import re
    
    full_log = "/var/log/asterisk/full"
    
    print(f"\n{Colors.CYAN}📊 Analyzing Asterisk logs (last 1000 lines)...{Colors.RESET}\n")
    
    # Check errors
    cmd = f"tail -1000 {full_log} | grep -E 'ERROR|CRITICAL'"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
    
    if result.stdout.strip():
        errors = result.stdout.strip().split('\n')
        error_count = len([e for e in errors if e])
        
        if error_count > 0:
            print(f"{Colors.RED}🔴 Found {error_count} error(s) in last 1000 log lines:{Colors.RESET}")
            
            # Group by error type
            error_types = defaultdict(int)
            for line in errors[:20]:  # Show first 20
                if line:
                    # Extract error message
                    match = re.search(r'(ERROR|CRITICAL).*?:\s*(.+?)$', line)
                    if match:
                        error_msg = match.group(2)[:80]
                        error_types[error_msg] += 1
            
            for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {count:>4}x {msg}")
        else:
            print(f"{Colors.GREEN}✅ No errors found{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}✅ No errors found in recent logs{Colors.RESET}")
    
    # Check trunk status
    print(f"\n{Colors.CYAN}📡 Checking trunk status...{Colors.RESET}")
    cmd = f"tail -500 {full_log} | grep -E 'trunk.*Unreachable|Registration.*failed'"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
    
    if result.stdout.strip():
        trunk_issues = result.stdout.strip().split('\n')
        print(f"{Colors.YELLOW}⚠️  Trunk issues detected ({len(trunk_issues)} events):{Colors.RESET}")
        for issue in trunk_issues[-5:]:
            print(f"  {issue[:120]}")
    else:
        print(f"{Colors.GREEN}✅ No trunk issues detected{Colors.RESET}")
    
    # Check authentication failures
    print(f"\n{Colors.CYAN}🔒 Checking security events...{Colors.RESET}")
    cmd = f"tail -500 {full_log} | grep -i 'failed.*auth\\|SECURITY'"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
    
    if result.stdout.strip():
        security_events = result.stdout.strip().split('\n')
        
        # Extract IPs
        ips = defaultdict(int)
        for line in security_events:
            ip_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', line)
            if ip_match:
                ips[ip_match.group(0)] += 1
        
        if ips:
            print(f"{Colors.YELLOW}⚠️  Authentication failures detected:{Colors.RESET}")
            for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {ip}: {count} attempts")
        else:
            print(f"{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}━{Colors.RESET}" * 60)
    print(f"{Colors.GREEN}✅ Log analysis complete{Colors.RESET}")


def run_log_analysis_menu():
    """Unified log & system analysis menu."""
    has_script = os.path.isfile(LOG_ANALYZER_SCRIPT)

    while True:
        print(f"\n{Colors.CYAN}Main Menu › Log & System Analysis{Colors.RESET}")
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔍 Log & System Analysis{' ' * 52}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.CYAN}{'─' * 30} Live (no script needed) {'─' * 22}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Quick inline log scan (errors / auth / trunk){' ' * 27}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Show stuck channels (active >30 min){' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Fail2ban jail status{' ' * 52}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.CYAN}{'─' * 32} Script-based analysis {'─' * 23}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Standard Asterisk log analysis{' ' * 43}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Comprehensive (Asterisk + system + patterns){' ' * 29}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Kernel log (dmesg){' ' * 55}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} System journal (journalctl){' ' * 47}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Search Asterisk logs with regex{' ' * 43}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} Search common Asterisk issue patterns{' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Evaluate error codes (SIP/Q.850 mapping){' ' * 32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 11){Colors.WHITE} Look up specific SIP code{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 12){Colors.WHITE} Return to main menu{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()

        choice = prompt(f"{Colors.YELLOW}Choose option (1-12, 0/b=back): {Colors.RESET}").strip()

        if choice == "0" or choice.lower() == "b":
            break
        elif choice == "1":
            hours = prompt(f"{Colors.YELLOW}Time window in hours (default: 1): {Colors.RESET}").strip() or "1"
            try:
                h = int(hours)
            except ValueError:
                h = 1
            if has_script:
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--hours", str(h)])
            else:
                run_inline_log_analysis_timed(h)
        elif choice == "2":
            run_stuck_channels_inline()
        elif choice == "3":
            run_fail2ban_status_inline()
        elif choice == "4":
            if not has_script:
                print(f"{Colors.YELLOW}Script not found, running inline scan.{Colors.RESET}")
                run_inline_log_analysis_timed(1)
            else:
                hours = prompt(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--hours", hours])
        elif choice == "5":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                hours = prompt(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--comprehensive", "--hours", hours])
        elif choice == "6":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--dmesg"])
        elif choice == "7":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                hours = prompt(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--journal", "--hours", hours])
        elif choice == "8":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                print_tip("Standard Python regex, matched against each log line, e.g. ERROR|WARNING.")
                pattern = prompt(f"{Colors.YELLOW}Enter regex pattern to search: {Colors.RESET}").strip()
                if pattern:
                    log_file = prompt(f"{Colors.YELLOW}Log file (default: /var/log/asterisk/full): {Colors.RESET}").strip()
                    log_file = log_file or "/var/log/asterisk/full"
                    run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--grep", pattern, "--log-file", log_file])
        elif choice == "9":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--search-patterns"])
        elif choice == "10":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--codes-only"])
        elif choice == "11":
            if not has_script:
                print(f"{Colors.RED}Script not available.{Colors.RESET}")
            else:
                print_tip("3-digit SIP response code (not the Q.850 cause number), e.g. 404, 486, 503.")
                code = prompt(f"{Colors.YELLOW}Enter SIP code to lookup: {Colors.RESET}").strip()
                if code:
                    run_interactive(["python3", LOG_ANALYZER_SCRIPT, "--lookup", code])
        elif choice == "12":
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-12.{Colors.RESET}")

        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        prompt()


def run_cdr_analysis_menu(sock):
    """Interactive CDR/CEL call log analysis menu."""
    if not os.path.isfile(CDR_ANALYZER_SCRIPT):
        print(f"{Colors.RED}❌ CDR analyzer tool not found.{Colors.RESET}")
        return

    while True:
        print(f"\n{Colors.CYAN}Main Menu › CDR/CEL Call Log Analysis{Colors.RESET}")
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 CDR/CEL Call Log Analysis{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Find calls by number (src or dst){' ' * 40}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Comprehensive call analysis{' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Call statistics summary{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Top callers{' ' * 62}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Top destinations{' ' * 57}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Call distribution by hour{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} Disposition breakdown{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Failed/busy calls analysis{' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} Trunk usage analysis{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Call duration distribution{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 11){Colors.WHITE} Export calls to JSON{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 12){Colors.WHITE} Full call-leg trace (linkedid or number){' ' * 32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 13){Colors.WHITE} Return to main menu{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()

        choice = prompt(f"{Colors.YELLOW}Choose analysis option (1-13, 0/b=back): {Colors.RESET}").strip()

        if choice == "0" or choice.lower() == "b":
            break
        elif choice == "1":
            print_tip("Formatted numbers work too — dashes, parens, and a leading 1 are all fine.")
            number = prompt(f"{Colors.YELLOW}Enter number to search (partial ok, e.g. 5551234): {Colors.RESET}").strip()
            if number:
                hours = prompt(f"{Colors.YELLOW}Search last N hours (default: 72): {Colors.RESET}").strip() or "72"
                if not hours.isdigit():
                    hours = "72"
                if os.path.isfile(CDR_ANALYZER_SCRIPT):
                    run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--find-number", number, "--hours", hours])
                else:
                    # Inline fallback: direct MySQL query
                    digits = re.sub(r"\D", "", number)
                    sql = (f"SELECT calldate, src, dst, disposition, duration, billsec "
                           f"FROM cdr WHERE (src LIKE '%{digits}%' OR dst LIKE '%{digits}%') "
                           f"AND calldate >= DATE_SUB(NOW(), INTERVAL {hours} HOUR) "
                           f"ORDER BY calldate DESC LIMIT 50;")
                    rc, out, err = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql, "asteriskcdrdb"])
                    if rc == 0 and out.strip():
                        print(f"\n{Colors.CYAN}Calls matching '{number}' (last {hours}h):{Colors.RESET}")
                        for row in out.strip().split('\n'):
                            print(f"  {row}")
                    else:
                        alt_rc, alt_out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql.replace("asteriskcdrdb", "asterisk")])
                        if alt_rc == 0 and alt_out.strip():
                            print(f"\n{Colors.CYAN}Calls matching '{number}' (last {hours}h):{Colors.RESET}")
                            for row in alt_out.strip().split('\n'):
                                print(f"  {row}")
                        else:
                            print(f"{Colors.YELLOW}No results or CDR database not accessible.{Colors.RESET}")
        elif choice == "12":
            if not os.path.isfile(CALL_LEG_ANALYZER_SCRIPT):
                print(f"{Colors.RED}❌ Call-leg analyzer tool not found.{Colors.RESET}")
            else:
                print_tip("Linkedid format is epoch.sequence, e.g. 1690000000.123 — leave blank to search by number.")
                linkedid = prompt(f"{Colors.YELLOW}Linkedid (Enter to search by number instead): {Colors.RESET}").strip()
                cmd = ["python3", CALL_LEG_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER]
                if linkedid:
                    cmd += ["--linkedid", linkedid]
                else:
                    print_tip("Full DID, extension, or any formatted phone number all work.")
                    number = prompt(f"{Colors.YELLOW}Phone number to search: {Colors.RESET}").strip()
                    if not number:
                        print(f"{Colors.RED}A linkedid or number is required.{Colors.RESET}")
                        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
                        prompt()
                        continue
                    leg_hours = prompt(f"{Colors.YELLOW}Search last N hours (default: 72): {Colors.RESET}").strip() or "72"
                    cmd += ["--number", number, "--hours", leg_hours]
                fmt = prompt(f"{Colors.YELLOW}Format tree/summary/json (default: tree): {Colors.RESET}").strip() or "tree"
                cmd += ["--format", fmt]
                run_interactive(cmd)
        elif choice == "13":
            break
        else:
            hours = None
            if choice in ['2', '3', '4', '5', '6', '7', '8', '9', '10', '11']:
                hours = prompt(f"{Colors.YELLOW}Analyze last N hours (default: 24): {Colors.RESET}").strip() or "24"
            if choice == "2":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--comprehensive", "--hours", hours])
            elif choice == "3":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--statistics", "--hours", hours])
            elif choice == "4":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--top-callers", "--hours", hours])
            elif choice == "5":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--top-destinations", "--hours", hours])
            elif choice == "6":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--by-hour", "--hours", hours])
            elif choice == "7":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--dispositions", "--hours", hours])
            elif choice == "8":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--failed", "--hours", hours])
            elif choice == "9":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--trunk-usage", "--hours", hours])
            elif choice == "10":
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--duration-dist", "--hours", hours])
            elif choice == "11":
                filename = prompt(f"{Colors.YELLOW}Output filename (default: auto-generated): {Colors.RESET}").strip()
                filename = filename or "/tmp/cdr_export.json"
                run_interactive(["python3", CDR_ANALYZER_SCRIPT, "--export-json", filename, "--hours", hours])
                maybe_email_file(filename, default_subject="freepbx-tools: CDR export")
            else:
                print(f"{Colors.RED}❌ Invalid choice. Please select 1-13.{Colors.RESET}")
        
        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        prompt()


def run_network_diagnostics_menu():
    """Interactive network diagnostics menu."""
    if not os.path.isfile(NETWORK_DIAGNOSTICS_SCRIPT):
        print(f"{Colors.RED}❌ Network diagnostics tool not found.{Colors.RESET}")
        return
    
    while True:
        print(f"\n{Colors.CYAN}Main Menu › Network Diagnostics & Packet Capture{Colors.RESET}")
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🌐 Network Diagnostics & Packet Capture{' ' * 37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Launch sngrep (SIP packet analyzer){' ' * 37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Show Asterisk SIP peers{' ' * 49}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Show active Asterisk channels{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Analyze SIP traffic (port 5060){' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Monitor RTP traffic (audio streams){' ' * 38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Capture packets with tcpdump{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} Ping test (connectivity check){' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Traceroute (path analysis){' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} DNS lookup (dig / nslookup){' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Show network interfaces (ip addr / ifconfig){' ' * 28}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 11){Colors.WHITE} Show routing table (ip route / route){' ' * 35}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 12){Colors.WHITE} Show ARP table (address resolution){' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 13){Colors.WHITE} Show network statistics (netstat / ss){' ' * 33}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 14){Colors.WHITE} Run comprehensive network diagnostic{' ' * 38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 15){Colors.WHITE} Return to main menu{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()

        choice = prompt(f"{Colors.YELLOW}Choose diagnostic option (1-15, 0/b=back): {Colors.RESET}").strip()

        if choice == "0" or choice.lower() == "b":
            break
        elif choice == "1":
            print(f"{Colors.CYAN}Launching sngrep... (Press 'q' to quit){Colors.RESET}\n")
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sngrep"])
        elif choice == "2":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-peers"])
        elif choice == "3":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-channels"])
        elif choice == "4":
            duration = prompt(f"{Colors.YELLOW}Capture duration in seconds (default: 30): {Colors.RESET}").strip() or "30"
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sip-traffic", "--duration", duration])
        elif choice == "5":
            duration = prompt(f"{Colors.YELLOW}Monitor duration in seconds (default: 30): {Colors.RESET}").strip() or "30"
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--rtp-traffic", "--duration", duration])
        elif choice == "6":
            duration = prompt(f"{Colors.YELLOW}Capture duration in seconds (default: 60): {Colors.RESET}").strip() or "60"
            port = prompt(f"{Colors.YELLOW}Filter by port (optional, press Enter to skip): {Colors.RESET}").strip()
            host = prompt(f"{Colors.YELLOW}Filter by host (optional, press Enter to skip): {Colors.RESET}").strip()
            cmd = ["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--tcpdump", "--duration", duration]
            if port:
                cmd.extend(["--port", port])
            if host:
                cmd.extend(["--host", host])
            run_interactive(cmd)
        elif choice == "7":
            host = prompt(f"{Colors.YELLOW}Enter host to ping (default: 8.8.8.8): {Colors.RESET}").strip() or "8.8.8.8"
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--ping", host])
        elif choice == "8":
            host = prompt(f"{Colors.YELLOW}Enter host for traceroute: {Colors.RESET}").strip()
            if host:
                run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--traceroute", host])
        elif choice == "9":
            domain = prompt(f"{Colors.YELLOW}Enter domain for DNS lookup: {Colors.RESET}").strip()
            if domain:
                run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--dns", domain])
        elif choice == "10":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--interfaces"])
        elif choice == "11":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--routing"])
        elif choice == "12":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--arp"])
        elif choice == "13":
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--netstat"])
        elif choice == "14":
            print(f"{Colors.CYAN}Running comprehensive network diagnostic...{Colors.RESET}\n")
            run_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--comprehensive"])
        elif choice == "15":
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-15.{Colors.RESET}")
        
        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        prompt()


# ---------------- menu ----------------

def run_show_unregistered_phones(sock):
    """Show unregistered phones inline using live Asterisk data."""
    print(f"\n{Colors.CYAN}Querying endpoint registration status...{Colors.RESET}")
    ep = get_endpoint_status(sock)
    details = ep.get("details", [])
    unreg = [(ext, name, status) for ext, name, status in details
             if status.lower() not in ("registered", "ok")]
    reg = [(ext, name, status) for ext, name, status in details
           if status.lower() in ("registered", "ok")]

    W = 68
    print(Colors.CYAN + "╔" + "═" * W + "╗" + Colors.RESET)
    title = f" 📵 UNREGISTERED PHONES — {len(unreg)} of {ep['total']} offline "
    print(Colors.CYAN + "║" + Colors.BOLD + Colors.RED + title.center(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * W + "╣" + Colors.RESET)
    if not unreg:
        line = "  ✓ All extensions registered."
        print(Colors.CYAN + "║" + Colors.GREEN + line.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    else:
        hdr = f"  {'Ext':<8} {'Name':<28} Status"
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.WHITE + hdr.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "─" * W + "╣" + Colors.RESET)
        for ext, name, status in sorted(unreg, key=lambda r: r[0]):
            line = f"  {ext:<8} {name[:28]:<28} {status}"
            print(Colors.CYAN + "║" + Colors.YELLOW + line.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * W + "╣" + Colors.RESET)
    summary = f"  Registered: {len(reg)}  │  Unregistered: {len(unreg)}  │  Total: {ep['total']}"
    print(Colors.CYAN + "║" + Colors.WHITE + summary.ljust(W) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╚" + "═" * W + "╝" + Colors.RESET)


def run_phone_analysis_menu(sock):
    """Interactive phone/endpoint analysis menu."""
    PHONE_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_phone_analyzer.py"

    if not os.path.isfile(PHONE_ANALYZER_SCRIPT):
        print(f"{Colors.RED}❌ Phone analyzer tool not found.{Colors.RESET}")
        return

    while True:
        print(f"\n{Colors.CYAN}Main Menu › Phone & Endpoint Analysis{Colors.RESET}")
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📱 Phone & Endpoint Analysis{' ' * 47}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Show unregistered phones (live){' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Analyze SIP peer registrations{' ' * 43}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Analyze PJSIP endpoints{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Analyze extension configuration{' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Check provisioning status{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Check firmware versions{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} Check 123NET configuration standards{' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Analyze call quality metrics{' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} Generate comprehensive phone report{' ' * 38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Return to main menu{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")

        choice = prompt(f"\n{Colors.YELLOW}Choose phone analysis option (1-10, 0/b=back): {Colors.RESET}").strip()

        if choice in ('10', '0') or choice.lower() == 'b':
            break
        elif choice == '1':
            run_show_unregistered_phones(sock)
        elif choice == '2':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--sip-peers'])
        elif choice == '3':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--pjsip'])
        elif choice == '4':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--extensions'])
        elif choice == '5':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--provisioning'])
        elif choice == '6':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--firmware'])
        elif choice == '7':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--standards'])
        elif choice == '8':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--call-quality'])
        elif choice == '9':
            run_interactive([sys.executable, PHONE_ANALYZER_SCRIPT, '--comprehensive'])
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-10.{Colors.RESET}")

        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        prompt()


# ============================================================================
# SELF-TEST — exercises every menu option's underlying action (not the
# interactive menu wrappers themselves, which end in a blocking "Press ENTER"
# prompt) and writes a report. See merry-marinating-deer.md plan for the full
# design rationale, especially around the two MUTATING tests below.
# ============================================================================

SESSION_LOG_PATH = "/tmp/freepbx_ops_session.json"


def _self_test_defaults(did_rows, data=None, chosen_did=None):
    first_did = chosen_did or (str(did_rows[0][1]) if did_rows else "2485551212")
    # Pick a real extension from THIS box's own data rather than hardcoding
    # one from wherever this tool was originally developed — different PBXs
    # have entirely different extension numbering.
    extensions = (data or {}).get("extensions") or []
    first_extension = str(extensions[0].get("extension")) if extensions else "100"
    return {
        "did": first_did,
        "extension": first_extension,
        # Standard safe caller ID for test calls — a known 123.net number, not
        # a real person's phone. Decoupled from the DID under test (which the
        # user picks separately) now that call_simulator.py never dials
        # caller_id as a destination (see the earlier fix: it previously did,
        # and a real-but-unrelated number here caused an actual outbound call).
        "caller_id": "8884400123",
        "sip_code": "404",
        "ping_host": "8.8.8.8",
        "traceroute_host": "8.8.8.8",
        "dns_domain": "google.com",
        "regex": "ERROR|WARNING",
        "search_term": first_did[-4:] if len(first_did) >= 4 else "100",
        "playback_sound": "demo-congrats",
    }


def _st_run(cmd, timeout=60):
    """Run a subprocess for the self-test; returns (passed, detail)."""
    try:
        rc, out, err = run(cmd, timeout=timeout)
    except Exception as e:
        return False, f"exception: {e}"
    detail = (err.strip() or out.strip() or "(no output)").replace("\n", " ")[:300]
    return rc == 0, detail


def _st_call(fn, *args, **kwargs):
    """In-process call for the self-test; returns (passed, detail)."""
    try:
        fn(*args, **kwargs)
        return True, "completed"
    except Exception as e:
        return False, f"exception: {e}"


def _self_test_tc_roundtrip(sock):
    """Capture one Time Condition's current inuse_state, force it to a test
    value, verify, then restore the ORIGINAL captured value (not a blind
    clear — if it was already forced, blind-clearing would leave it wrong)
    and verify the restore. No dedicated read/set function exists for this
    in the codebase (confirmed during planning) — replicates run_tc_control's
    own SQL/AstDB command pairs directly. Returns (passed, detail, loud_failure).
    """
    sql = ("SELECT timeconditions_id, COALESCE(inuse_state,0) FROM timeconditions "
           "ORDER BY CAST(timeconditions_id AS UNSIGNED) LIMIT 1")
    rc, out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", sql, "asterisk"])
    if rc != 0 or not out.strip():
        return True, "SKIP: no time conditions configured to test", False

    parts = out.strip().split("\n")[0].split("\t")
    if len(parts) < 2:
        return False, f"unexpected TC query output: {out!r}", False
    tc_id, original_state = parts[0], parts[1]

    def _read_state():
        rc2, out2, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe",
                             f"SELECT COALESCE(inuse_state,0) FROM timeconditions WHERE timeconditions_id={tc_id}",
                             "asterisk"])
        return out2.strip() if rc2 == 0 else None

    def _apply(action):
        if action == "0":
            run(["asterisk", "-rx", f"database del TCTEMP {tc_id}"])
            run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", f"UPDATE timeconditions SET inuse_state=0 WHERE timeconditions_id={tc_id}", "asterisk"])
        else:
            run(["asterisk", "-rx", f"database put TCTEMP {tc_id} force {action}"])
            run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe", f"UPDATE timeconditions SET inuse_state={action} WHERE timeconditions_id={tc_id}", "asterisk"])

    test_value = "2" if original_state != "2" else "1"
    _apply(test_value)
    after_mutate = _read_state()
    if after_mutate != test_value:
        return False, f"TC {tc_id}: force to {test_value} did not verify (read back {after_mutate!r})", True

    _apply(original_state)
    after_restore = _read_state()
    if after_restore != original_state:
        return False, (f"TC {tc_id}: RESTORE FAILED — was {original_state}, forced to {test_value}, "
                        f"attempted restore but read back {after_restore!r}. Manual fix needed: "
                        f"option 6 (Time-Condition status + Force/Clear control)."), True

    return True, f"TC {tc_id}: {original_state} -> {test_value} -> restored to {original_state}, verified", False


def _self_test_ivr_roundtrip(sock):
    """Capture one IVR option's current destination, apply a distinctly
    different (safe, standard) test destination via `set-ivr --apply`,
    verify, restore the original via the same command, verify again, then
    strip the two SESSION_LOG entries this creates so a later `ticket`
    doesn't show fake test changes. Each --apply triggers a real fwconsole
    reload — this is the slowest single test in the suite by design.
    Returns (passed, detail, loud_failure).
    """
    rc, out, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe",
                       "SELECT ivr_id, selection, dest FROM ivr_entries LIMIT 1", "asterisk"])
    if rc != 0 or not out.strip():
        return True, "SKIP: no IVR options configured to test", False

    parts = out.strip().split("\n")[0].split("\t")
    if len(parts) < 3:
        return False, f"unexpected IVR query output: {out!r}", False
    ivr_id, option, old_dest = parts[0], parts[1], parts[2]

    def _read_dest():
        rc2, out2, _ = run(["mysql", "--user", DB_USER, "--socket", sock, "-NBe",
                             f"SELECT dest FROM ivr_entries WHERE ivr_id='{ivr_id}' AND selection='{option}'",
                             "asterisk"])
        return out2.strip() if rc2 == 0 else None

    test_dest = "app-blackhole,hangup,1" if old_dest != "app-blackhole,hangup,1" else "app-blackhole,congestion,1"

    rc_a, out_a, err_a = run(["python3", OPS_SCRIPT, "--socket", sock,
                               "set-ivr", "--ivr", ivr_id, "--option", option, "--dest", test_dest, "--apply"],
                              timeout=90)
    after_mutate = _read_dest()
    if rc_a != 0 or after_mutate != test_dest:
        return False, (f"IVR {ivr_id}/{option}: apply of test dest did not verify "
                        f"(rc={rc_a}, read back {after_mutate!r}): {(err_a or out_a)[:200]}"), True

    rc_b, out_b, err_b = run(["python3", OPS_SCRIPT, "--socket", sock,
                               "set-ivr", "--ivr", ivr_id, "--option", option, "--dest", old_dest, "--apply"],
                              timeout=90)
    after_restore = _read_dest()

    if rc_b != 0 or after_restore != old_dest:
        return False, (f"IVR {ivr_id}/{option}: RESTORE FAILED — was {old_dest!r}, changed to {test_dest!r}, "
                        f"attempted restore but read back {after_restore!r}. Manual fix needed: "
                        f"Ops Tools -> Set IVR option, dest={old_dest!r}."), True

    try:
        _self_test_scrub_session_log(ivr_id, option)
    except Exception:
        pass  # cosmetic cleanup only — restore already verified above, don't fail the test over this

    return True, f"IVR {ivr_id}/{option}: {old_dest} -> {test_dest} -> restored, verified, session log scrubbed", False


def _self_test_scrub_session_log(ivr_id, option):
    """Remove the set-ivr entries the round-trip test itself created, so
    `freepbx_ops.py ticket` doesn't later report fake test changes."""
    try:
        with open(SESSION_LOG_PATH) as f:
            session = json.load(f)
    except (OSError, ValueError):
        return
    entries = session.get("changes", []) if isinstance(session, dict) else session
    kept = [
        e for e in entries
        if not (e.get("type") == "set-ivr"
                and str(e.get("data", {}).get("ivr_id")) == str(ivr_id)
                and str(e.get("data", {}).get("option")) == str(option)
                and "app-blackhole" in str(e.get("data", {}).get("new_dest", "")) + str(e.get("data", {}).get("old_dest", "")))
    ]
    if isinstance(session, dict):
        session["changes"] = kept
    else:
        session = kept
    try:
        with open(SESSION_LOG_PATH, "w") as f:
            json.dump(session, f)
    except OSError:
        pass


def _st_probe_interactive(cmd, seconds=3):
    """Launch a normally-interactive/long-running command, let it run briefly,
    then terminate it — confirms it starts without immediately crashing. Not
    a full test; interactive behavior (e.g. sngrep's TUI) can't be verified
    headlessly, and the report says so explicitly for these."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 stdin=subprocess.DEVNULL, universal_newlines=True)
    except Exception as e:
        return False, f"failed to launch: {e}"
    time.sleep(seconds)
    still_running = proc.poll() is None
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    if still_running:
        return True, f"started and ran {seconds}s (interactive — not fully exercised, terminated for self-test)"
    return proc.returncode == 0, f"exited on its own after {seconds}s, rc={proc.returncode} (interactive — not fully exercised)"


def _build_self_test_cases(sock, data, did_rows, defaults, include_live_calls):
    """Data-driven table covering every menu option's underlying action.
    Deliberately calls the underlying subprocess/function directly rather
    than the interactive menu wrapper functions (which end in a blocking
    "Press ENTER" prompt()) — see plan doc for rationale. Each entry:
    (section, label, classification, run_callable) where run_callable
    returns (passed: bool, detail: str)."""
    did = defaults["did"]
    phone_analyzer_script = "/usr/local/123net/freepbx-tools/bin/freepbx_phone_analyzer.py"
    cases = []

    def add(section, label, cls, fn):
        cases.append((section, label, cls, fn))

    # ---- Main menu ----
    add("Main Menu", "Refresh data cache", "SAFE_READONLY", lambda: _st_call(refresh_dump, sock))
    add("Main Menu", "Show inventory summary", "SAFE_READONLY", lambda: _st_call(summarize, data))
    add("Main Menu", "Generate call-flow for one DID", "SAFE_READONLY",
        lambda: _st_call(render_dids, did_rows, [1], sock) if did_rows else (True, "SKIP: no cached DIDs"))
    add("Main Menu", "Time-Condition status report", "SAFE_READONLY",
        lambda: _st_run(["python3", TC_STATUS_SCRIPT, "--socket", sock, "--db-user", DB_USER]))
    add("Main Menu", "FreePBX module analysis", "SAFE_READONLY",
        lambda: _st_run(["python3", MODULE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER], timeout=120))
    add("Main Menu", "Paging/fax analysis", "SAFE_READONLY",
        lambda: _st_run(["python3", PAGING_FAX_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER], timeout=120))
    add("Main Menu", "Comprehensive component analysis", "SAFE_READONLY",
        lambda: _st_run(["python3", COMPREHENSIVE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER], timeout=180))
    add("Main Menu", "Full Asterisk diagnostic (legacy script)", "SAFE_READONLY",
        lambda: _st_run(["/usr/local/bin/asterisk-full-diagnostic.sh"], timeout=60))
    add("Main Menu", "SIP code lookup (in-process)", "SAFE_READONLY", lambda: _st_sip_lookup(defaults["sip_code"]))

    # ---- ASCII call-flow submenu ----
    if did_rows:
        add("ASCII Call-Flow", "Generate ASCII flow for one DID", "SAFE_READONLY",
            lambda: _st_run(["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--did", did]))
    add("ASCII Call-Flow", "Print data collection summary", "SAFE_READONLY",
        lambda: _st_run(["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--print-data"]))
    add("ASCII Call-Flow", "Export all data to JSON", "SAFE_READONLY",
        lambda: _st_run(["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER,
                          "--export", f"/tmp/self_test_ascii_export_{int(time.time())}.json"]))

    # ---- Call Simulation & Validation submenu ----
    if did_rows:
        add("Call Simulation", "Validate DID call-flow config (database only)", "SAFE_READONLY",
            lambda: _st_run(["python3", CALLFLOW_VALIDATOR_SCRIPT, did]))
    if include_live_calls:
        if did_rows:
            add("Call Simulation", "Test specific DID (live call, follows real routing)", "LIVE_CALL",
                lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--did", did, "--debug"], timeout=45))
        add("Call Simulation", "Test extension-to-extension call (live)", "LIVE_CALL",
            lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--extension", defaults["extension"],
                              "--caller-id", defaults["caller_id"], "--debug"], timeout=45))
        add("Call Simulation", "Test voicemail access (live)", "LIVE_CALL",
            lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--voicemail", defaults["extension"],
                              "--caller-id", defaults["caller_id"], "--debug"], timeout=45))
        add("Call Simulation", "Test audio playback (live)", "LIVE_CALL",
            lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--playback", defaults["playback_sound"],
                              "--caller-id", defaults["caller_id"], "--debug"], timeout=45))
        ring_groups = (data or {}).get("ringgroups") or []
        if ring_groups:
            first_grpnum = str(ring_groups[0].get("grpnum"))
            add("Call Simulation", "Test ring group (live)", "LIVE_CALL",
                lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--ring-group", first_grpnum,
                                  "--caller-id", defaults["caller_id"], "--debug"], timeout=45))
        queues = (data or {}).get("queues") or []
        if queues:
            first_queue_ext = str(queues[0].get("queue"))
            add("Call Simulation", "Test queue (live)", "LIVE_CALL",
                lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--queue", first_queue_ext,
                                  "--caller-id", defaults["caller_id"], "--debug"], timeout=45))
        add("Call Simulation", "Comprehensive validation (many live calls)", "DESTRUCTIVE_OR_SLOW",
            lambda: _st_run(["python3", CALL_SIMULATOR_SCRIPT, "--comprehensive", "--debug"], timeout=180))
        add("Call Simulation", "Monitor active call simulations", "INTERACTIVE_ONLY",
            lambda: _st_probe_interactive([SIMULATE_CALLS_SCRIPT, "monitor"], seconds=3))

    # ---- Log & System Analysis submenu ----
    add("Log Analysis", "Quick inline log scan (1h)", "SAFE_READONLY",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--hours", "1"]))
    add("Log Analysis", "Fail2ban jail status", "SAFE_READONLY", lambda: _st_call(run_fail2ban_status_inline))
    add("Log Analysis", "Stuck channels (>30 min)", "SAFE_READONLY", lambda: _st_call(run_stuck_channels_inline))
    add("Log Analysis", "Comprehensive log analysis (1h)", "SAFE_READONLY",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--comprehensive", "--hours", "1"], timeout=90))
    add("Log Analysis", "Kernel log (dmesg)", "SAFE_READONLY", lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--dmesg"]))
    add("Log Analysis", "System journal (1h)", "SAFE_READONLY",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--journal", "--hours", "1"]))
    add("Log Analysis", "Search logs with regex", "REQUIRES_INPUT",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--grep", defaults["regex"], "--log-file", "/var/log/asterisk/full"]))
    add("Log Analysis", "Search common issue patterns", "SAFE_READONLY",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--search-patterns"]))
    add("Log Analysis", "Evaluate error codes (SIP/Q.850 mapping)", "SAFE_READONLY",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--codes-only"]))
    add("Log Analysis", "Look up specific SIP code", "REQUIRES_INPUT",
        lambda: _st_run(["python3", LOG_ANALYZER_SCRIPT, "--lookup", defaults["sip_code"]]))

    # ---- Network Diagnostics submenu ----
    add("Network Diagnostics", "sngrep launch", "INTERACTIVE_ONLY",
        lambda: _st_probe_interactive(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sngrep"], seconds=3))
    add("Network Diagnostics", "Asterisk SIP peers", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-peers"]))
    add("Network Diagnostics", "Active Asterisk channels", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-channels"]))
    add("Network Diagnostics", "SIP traffic capture (short)", "DESTRUCTIVE_OR_SLOW",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sip-traffic", "--duration", "3"], timeout=20))
    add("Network Diagnostics", "RTP traffic capture (short)", "DESTRUCTIVE_OR_SLOW",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--rtp-traffic", "--duration", "3"], timeout=20))
    add("Network Diagnostics", "tcpdump capture (short)", "DESTRUCTIVE_OR_SLOW",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--tcpdump", "--duration", "3"], timeout=20))
    add("Network Diagnostics", "Ping test", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--ping", defaults["ping_host"]]))
    add("Network Diagnostics", "Traceroute", "REQUIRES_INPUT",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--traceroute", defaults["traceroute_host"]], timeout=30))
    add("Network Diagnostics", "DNS lookup", "REQUIRES_INPUT",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--dns", defaults["dns_domain"]]))
    add("Network Diagnostics", "Network interfaces", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--interfaces"]))
    add("Network Diagnostics", "Routing table", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--routing"]))
    add("Network Diagnostics", "ARP table", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--arp"]))
    add("Network Diagnostics", "Network statistics", "SAFE_READONLY",
        lambda: _st_run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--netstat"]))

    # ---- CDR/CEL Call Log Analysis submenu ----
    add("CDR/CEL Analysis", "Find calls by number", "REQUIRES_INPUT",
        lambda: _st_run(["python3", CDR_ANALYZER_SCRIPT, "--find-number", defaults["search_term"], "--hours", "72"]))
    for label, flag in [
        ("Comprehensive call analysis", "--comprehensive"), ("Call statistics summary", "--statistics"),
        ("Top callers", "--top-callers"), ("Top destinations", "--top-destinations"),
        ("Call distribution by hour", "--by-hour"), ("Disposition breakdown", "--dispositions"),
        ("Failed/busy calls analysis", "--failed"), ("Trunk usage analysis", "--trunk-usage"),
        ("Call duration distribution", "--duration-dist"),
    ]:
        add("CDR/CEL Analysis", label, "SAFE_READONLY",
            (lambda f: lambda: _st_run(["python3", CDR_ANALYZER_SCRIPT, f, "--hours", "24"]))(flag))
    add("CDR/CEL Analysis", "Export calls to JSON", "SAFE_READONLY",
        lambda: _st_run(["python3", CDR_ANALYZER_SCRIPT, "--export-json",
                          f"/tmp/self_test_cdr_export_{int(time.time())}.json", "--hours", "24"]))
    add("CDR/CEL Analysis", "Full call-leg trace (by number)", "REQUIRES_INPUT",
        lambda: _st_run(["python3", CALL_LEG_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER,
                          "--number", defaults["search_term"], "--hours", "72", "--format", "summary"]))

    # ---- Phone/Endpoint Analysis submenu ----
    add("Phone Analysis", "Show unregistered phones (live)", "SAFE_READONLY",
        lambda: _st_call(get_endpoint_status, sock))
    for label, flag in [
        ("Analyze SIP peer registrations", "--sip-peers"), ("Analyze PJSIP endpoints", "--pjsip"),
        ("Analyze extension configuration", "--extensions"), ("Check provisioning status", "--provisioning"),
        ("Check firmware versions", "--firmware"), ("Check 123NET configuration standards", "--standards"),
        ("Analyze call quality metrics", "--call-quality"),
    ]:
        add("Phone Analysis", label, "SAFE_READONLY",
            (lambda f: lambda: _st_run([sys.executable, phone_analyzer_script, f]))(flag))

    # ---- Ops Tools submenu ----
    if did_rows:
        add("Ops Tools", "Trace DID — full call-path tree", "SAFE_READONLY",
            lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "trace", did]))
    add("Ops Tools", "Decode destination string", "SAFE_READONLY",
        lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "decode", "ext-group,7004,1"]))
    add("Ops Tools", "Find — search across all components", "REQUIRES_INPUT",
        lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "find", defaults["search_term"]]))
    add("Ops Tools", "Snapshot — save current call-flow", "SAFE_READONLY",
        lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "snapshot", "--reason", "self-test"]))
    add("Ops Tools", "Validate — health/consistency check", "SAFE_READONLY",
        lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "validate"], timeout=90))
    add("Ops Tools", "Print ticket note", "SAFE_READONLY",
        lambda: _st_run(["python3", OPS_SCRIPT, "--socket", sock, "ticket"]))
    add("Main Menu", "Certificate status (web GUI + SIP TLS)", "SAFE_READONLY",
        lambda: _st_run(["python3", CERT_CHECK_SCRIPT]))

    # ---- MUTATING (only if include_live_calls, since these have live side effects too) ----
    if include_live_calls:
        add("Mutating (round-trip, restores original state)", "Time Condition force/clear round-trip", "MUTATING",
            lambda: _self_test_tc_roundtrip(sock))
        add("Mutating (round-trip, restores original state)", "Set IVR option apply/restore round-trip", "MUTATING",
            lambda: _self_test_ivr_roundtrip(sock))

    # ---- INTERACTIVE_ONLY (main menu) ----
    add("Main Menu", "Live dashboard monitor (probe only)", "INTERACTIVE_ONLY",
        lambda: _st_probe_interactive(["python3", os.path.abspath(__file__), "--watch", "--interval", "1"], seconds=3))

    return cases


def _st_sip_lookup(code):
    try:
        from freepbx_log_analyzer import lookup_cause_code, format_cause_code
        info = lookup_cause_code(code)
        return (info is not None), (format_cause_code(info) if info else f"no mapping for code {code}")
    except Exception as e:
        return False, f"exception: {e}"


def _write_self_test_report(results, loud_failures, include_live_calls, total_elapsed, data):
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(SELF_TEST_DIR, exist_ok=True)
    path = os.path.join(SELF_TEST_DIR, f"self_test_{ts}.txt")
    hostname = (data.get("meta", {}) if data else {}).get("hostname", "unknown")
    tool_ver = get_tool_version() or "unknown"

    pass_n = sum(1 for r in results if r["status"] == "PASS")
    fail_n = sum(1 for r in results if r["status"] == "FAIL")
    skip_n = sum(1 for r in results if r["status"] == "SKIP")

    lines = [
        "freePBX Tools — Self-Test Report",
        "=================================",
        f"Generated:        {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Host:             {hostname}",
        f"Tool version:     {tool_ver}",
        f"Live calls run:   {'yes' if include_live_calls else 'no (skipped)'}",
        f"Total runtime:    {total_elapsed:.0f}s",
        f"Results:          {pass_n} passed, {fail_n} failed, {skip_n} skipped (of {len(results)})",
        "",
    ]

    if loud_failures:
        lines.append("!" * 78)
        lines.append("MUTATING TEST(S) MAY HAVE LEFT LIVE STATE CHANGED — CHECK THESE FIRST")
        lines.append("!" * 78)
        for r in loud_failures:
            lines.append(f"  [{r['section']}] {r['label']}: {r['detail']}")
        lines.append("")

    by_section = {}
    for r in results:
        by_section.setdefault(r["section"], []).append(r)

    for section, entries in by_section.items():
        lines.append(f"--- {section} ---")
        for r in entries:
            lines.append(f"  [{r['status']:4s}] ({r['class']:18s}, {r['elapsed']:5.1f}s) {r['label']}")
            if r["status"] != "PASS":
                lines.append(f"           {r['detail']}")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def run_self_test(sock, data, did_rows):
    """Exercises every menu option's underlying action and writes a report.
    See the plan doc for full rationale — briefly: this actually places live
    test calls and round-trips two mutating operations (Time Condition
    force/clear, IVR set-ivr) with capture/verify/restore, per an explicit
    choice made when this was scoped, rather than only checking that the
    risky options are present and well-formed."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}=== Self-Test: Full Program Diagnostic ==={Colors.RESET}\n")
    print("Exercises every menu option's underlying action and writes a report.")

    # call_simulator.py now defaults to THIS box's own IP when no --server is
    # given (which the self-test never does), so live-call tests always
    # target the system the self-test is actually running on — no more
    # "wrong box" risk to gate on here.
    include_live_calls = True

    chosen_did = None
    if include_live_calls and did_rows:
        print(f"\n{Colors.CYAN}DIDs configured on this system:{Colors.RESET}")
        for row in did_rows:
            idx, did, label = row[0], row[1], row[2]
            print(f"  {idx}) {did}" + (f"  {label}" if label else ""))
        pick = prompt(
            f"{Colors.YELLOW}Pick a DID to use for live-call tests "
            f"(Enter for #{did_rows[0][0]}): {Colors.RESET}"
        ).strip()
        chosen_did = str(did_rows[0][1])
        if pick:
            try:
                idx = int(pick)
                match = next((r for r in did_rows if r[0] == idx), None)
                if match:
                    chosen_did = str(match[1])
                else:
                    print(f"{Colors.YELLOW}No DID at index {idx} — using #{did_rows[0][0]}.{Colors.RESET}")
            except ValueError:
                print(f"{Colors.YELLOW}Not a number — using #{did_rows[0][0]}.{Colors.RESET}")
        print(f"{Colors.GREEN}Using DID {chosen_did} for live-call tests (as both the target DID "
              f"and the caller ID presented on extension/voicemail/playback tests).{Colors.RESET}")

    print(f"\n{Colors.RED}{Colors.BOLD}This self-test will, for real:{Colors.RESET}")
    if include_live_calls:
        print("  - Place several real test calls (DID, extension, voicemail, playback, comprehensive)")
        print("  - Briefly force then restore one Time Condition")
        print("  - Briefly change then restore one IVR option destination (2x fwconsole reload)")
        print("  - Run several short (3-5s) packet captures")
    else:
        print("  - Read-only checks only — live-call and mutating tests are excluded")
    confirm = prompt(f"\n{Colors.YELLOW}Type CONFIRM to proceed, anything else to cancel: {Colors.RESET}").strip()
    if confirm != "CONFIRM":
        print(f"{Colors.RED}Self-test cancelled.{Colors.RESET}")
        return

    ensure_outdir()
    os.makedirs(SELF_TEST_DIR, exist_ok=True)

    if include_live_calls:
        print(f"\n{Colors.CYAN}Taking a full config snapshot first (safety net, independent of the "
              f"per-test capture/restore below)...{Colors.RESET}")
        snap_rc, snap_out, snap_err = run(
            ["python3", OPS_SCRIPT, "--socket", sock, "snapshot", "--reason", "before self-test"], timeout=60)
        if snap_rc != 0:
            print(f"{Colors.YELLOW}⚠ Pre-test snapshot failed — proceeding anyway: {(snap_err or snap_out)[:200]}{Colors.RESET}")

    defaults = _self_test_defaults(did_rows, data=data, chosen_did=chosen_did)
    cases = _build_self_test_cases(sock, data, did_rows, defaults, include_live_calls)

    results = []
    loud_failures = []
    total = len(cases)
    start_time = time.time()
    for i, (section, label, cls, fn) in enumerate(cases, 1):
        print_progress_bar(i, total, f"{section}: {label}")
        t0 = time.time()
        try:
            outcome = fn()
        except Exception as e:
            outcome = (False, f"unhandled exception: {e}")
        elapsed = time.time() - t0
        loud = outcome[2] if len(outcome) == 3 else False
        passed, detail = outcome[0], outcome[1]
        status = "SKIP" if str(detail).startswith("SKIP") else ("PASS" if passed else "FAIL")
        results.append({"section": section, "label": label, "class": cls, "status": status,
                         "detail": str(detail), "elapsed": round(elapsed, 1)})
        if loud:
            loud_failures.append(results[-1])

    total_elapsed = time.time() - start_time
    print()

    pass_n = sum(1 for r in results if r["status"] == "PASS")
    fail_n = sum(1 for r in results if r["status"] == "FAIL")
    skip_n = sum(1 for r in results if r["status"] == "SKIP")
    print(f"\n{Colors.BOLD}Self-test complete in {total_elapsed:.0f}s: {Colors.GREEN}{pass_n} passed{Colors.RESET}, "
          f"{Colors.RED}{fail_n} failed{Colors.RESET}, {Colors.YELLOW}{skip_n} skipped{Colors.RESET} (of {total}).{Colors.RESET}")

    if loud_failures:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠⚠⚠  {len(loud_failures)} mutating test(s) may have left live state "
              f"changed — see the report for exact manual-fix steps ⚠⚠⚠{Colors.RESET}")

    report_path = _write_self_test_report(results, loud_failures, include_live_calls, total_elapsed, data)
    print(f"\nReport written to: {report_path}")
    maybe_email_file(report_path, default_subject="freepbx-tools: self-test report")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="freePBX call-flow menu + dashboard")
    parser.add_argument("--watch", action="store_true", help="Run live dashboard monitor (auto-refresh).")
    parser.add_argument("--interval", default="2", help="Refresh interval seconds for --watch (default: 2).")
    parser.add_argument(
        "--watch-refresh-snapshot",
        action="store_true",
        help="When using --watch, refresh the data cache every cycle (can be heavy).",
    )
    args = parser.parse_args()

    # Check if running as root (required for MySQL access)
    try:
        euid = os.geteuid()  # type: ignore
        if euid != 0:
            print(Colors.YELLOW + "\n⚠️  This tool requires root access to query the FreePBX database." + Colors.RESET)
            print(Colors.CYAN + "Please run: " + Colors.BOLD + "sudo freepbx-callflows" + Colors.RESET)
            print(Colors.CYAN + "Or switch to root first: " + Colors.BOLD + "su root" + Colors.RESET + "\n")
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have geteuid, skip check
        pass

    if not os.path.isfile(DUMP_SCRIPT):
        print("ERROR: {} not found.".format(DUMP_SCRIPT)); sys.exit(1)
    if not os.path.isfile(GRAPH_SCRIPT):
        print("ERROR: {} not found.".format(GRAPH_SCRIPT)); sys.exit(1)

    sock = detect_mysql_socket()
    data = load_dump()
    if not data:
        # first run: force data cache so menu has content
        if not refresh_dump(sock):
            sys.exit(1)
        data = load_dump()

    def run_live_monitor(initial_data):
        interval = max(0.5, _safe_float(args.interval, 2.0))
        data_local = initial_data
        print(Colors.YELLOW + "\nLive dashboard monitor running. Press Ctrl+C to return." + Colors.RESET)
        try:
            while True:
                if args.watch_refresh_snapshot:
                    if refresh_dump(sock):
                        data_local = load_dump() or data_local
                display_system_dashboard(sock, data_local)
                time.sleep(interval)
        except KeyboardInterrupt:
            return data_local

    if args.watch:
        run_live_monitor(data)
        return

    while True:
        try:
            # Display system dashboard at top
            display_system_dashboard(sock, data)

            # Get terminal width for menu
            try:
                menu_width = shutil.get_terminal_size().columns - 4  # Leave margin
            except:
                menu_width = 78  # Default fallback

            # Menu with full width alignment
            print("\n" + Colors.CYAN + "╔" + "═" * menu_width + "╗" + Colors.RESET)
            print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 📞 freePBX Call-Flow Menu ".center(menu_width) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
            print(Colors.CYAN + "╠" + "═" * menu_width + "╣" + Colors.RESET)

            # Helper function to format menu line with proper alignment (ANSI-safe)
            def menu_line(num, text):
                num_part = f" {num:>2})"
                inner = num_part + " " + text
                padding_needed = menu_width - visible_len(inner) - 2
                padding = " " * max(0, padding_needed)
                return (Colors.CYAN + "║" + Colors.BOLD + num_part + Colors.RESET +
                        " " + text + padding + Colors.CYAN + " ║" + Colors.RESET)

            def menu_section(title):
                inner = f" {title} "
                dashes = "─" * ((menu_width - len(inner)) // 2)
                line = (dashes + inner + dashes).ljust(menu_width)
                return Colors.CYAN + "║" + Colors.BOLD + Colors.CYAN + line + Colors.RESET + Colors.CYAN + "║" + Colors.RESET

            _cache_age_s = get_snapshot_age_seconds()
            _cache_tag = (f"  {Colors.CYAN}[cache: {format_age(_cache_age_s)}]{Colors.RESET}"
                          if _cache_age_s is not None else "")
            print(menu_section("Snapshot & Inventory"))
            print(menu_line("0", "Live dashboard monitor (auto-refresh)"))
            print(menu_line("1", "Refresh data cache" + _cache_tag))
            print(menu_line("2", "Show inventory (counts) + list DIDs"))
            print(menu_section("Render Call Flows"))
            print(menu_line("3", "Generate call-flow for selected DID(s)"))
            print(menu_line("4", "Generate call-flows for ALL DIDs"))
            print(menu_line("5", "Generate call-flows for ALL DIDs (skip labels: OPEN)"))
            print(menu_line("10", "Generate ASCII art call-flows"))
            print(menu_section("PBX Analysis"))
            print(menu_line("6", "Time-Condition status + Force/Clear control"))
            print(menu_line("7", "Run FreePBX module analysis"))
            print(menu_line("8", "Run paging, overhead & fax analysis"))
            print(menu_line("9", "Run comprehensive component analysis"))
            print(menu_section("Diagnostics"))
            print(menu_line("11", "Call Simulation & Validation"))
            print(menu_line("12", "Run full Asterisk diagnostic"))
            print(menu_line("13", "Log & System Analysis (errors / stuck channels / fail2ban / journal)"))
            print(menu_line("14", "SIP / Q.850 code lookup"))
            print(menu_line("15", "Network Diagnostics & Packet Capture"))
            print(menu_line("16", "Run full self-test (exercises every menu option, writes a report)"))
            print(menu_line("17", "CDR/CEL Call Log Analysis (find by number)"))
            print(menu_line("18", "Phone/Endpoint Analysis"))
            print(menu_line("21", "Certificate Status (web GUI + SIP TLS)"))
            print(menu_section("Ops Tools"))
            print(menu_line("20", "Call-Flow Ops (trace / decode / find / snapshot / validate / set-IVR / ticket)"))
            print(Colors.CYAN + "╠" + "═" * menu_width + "╣" + Colors.RESET)
            print(menu_line("19", "Quit"))
            print(Colors.CYAN + "╠" + "═" * menu_width + "╣" + Colors.RESET)
            _hint = "Shortcuts: d=DIDs  r=refresh  t=TC  l=log  n=net  c=CDR  p=phones  o=ops  q=quit  Ctrl+C=back"
            _hpad = " " * max(0, menu_width - len(_hint) - 2)
            print(Colors.CYAN + "║ " + Colors.BOLD + Colors.CYAN + _hint + _hpad + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
            print(Colors.CYAN + "╚" + "═" * menu_width + "╝" + Colors.RESET)
            choice = prompt("\n" + Colors.YELLOW + "Choose (or d=DIDs r=refresh t=TC l=log n=net c=CDR p=phones o=ops): " + Colors.RESET).strip()
            # Single-letter shortcuts
            _shortcuts = {"d": "2", "r": "1", "t": "6", "l": "13", "n": "15", "c": "17", "p": "18", "o": "20", "q": "19"}
            choice = _shortcuts.get(choice.lower(), choice)

            if choice == "0":
                # local monitor mode (does not exit the menu)
                try:
                    interval = prompt(Colors.YELLOW + "Refresh interval seconds (default 2): " + Colors.RESET).strip() or "2"
                    args.interval = interval
                    refresh_each = prompt(Colors.YELLOW + "Refresh data cache each cycle? (y/N): " + Colors.RESET).strip().lower()
                    args.watch_refresh_snapshot = refresh_each in ("y", "yes")
                except Exception:
                    args.interval = "2"
                    args.watch_refresh_snapshot = False
                data = run_live_monitor(data)
                continue

            if choice == "1":
                if refresh_dump(sock):
                    data = load_dump()
                _DASH_CACHE["ts"] = 0.0  # invalidate dashboard cache after refresh
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "2":
                summarize(data)
                list_dids(data)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "3":
                did_rows = list_dids(data)
                if not did_rows: 
                    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                    prompt()
                    continue
                sel = prompt("\nEnter indexes (e.g. 1,3,5-8), DID number(s), or * for all: ")
                idxs = parse_selection(sel, did_rows)
                if not idxs:
                    print("No valid selection.")
                    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                    prompt()
                    continue
                render_dids(did_rows, idxs, sock)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "4":
                did_rows = get_did_rows(data)
                if not did_rows:
                    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                    prompt()
                    continue
                render_dids(did_rows, list(range(1, len(did_rows)+1)), sock)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "5":
                did_rows = get_did_rows(data)
                if not did_rows: 
                    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                    prompt()
                    continue
                # lowercase match set; you can add more labels here if you want to exclude them
                render_dids(did_rows, list(range(1, len(did_rows)+1)), sock,
                            skip_labels=set(["open"]))
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "6":
                run_tc_control(sock)

            elif choice == "7":
                run_module_analyzer(sock)

            elif choice == "8":
                run_paging_fax_analyzer(sock)

            elif choice == "9":
                run_comprehensive_analyzer(sock)

            elif choice == "10":
                did_rows = list_dids(data)
                if did_rows:
                    run_ascii_callflow(sock, did_rows)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "11":
                did_rows = list_dids(data)
                run_call_simulation_menu(sock, did_rows, data)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "12":
                run_full_diagnostic()
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "13":
                run_log_analysis_menu()

            elif choice == "14":
                show_error_map_quick_reference()

            elif choice == "15":
                run_network_diagnostics_menu()

            elif choice == "16":
                run_self_test(sock, data, get_did_rows(data))

            elif choice == "17":
                run_cdr_analysis_menu(sock)

            elif choice == "18":
                run_phone_analysis_menu(sock)

            elif choice == "21":
                if os.path.isfile(CERT_CHECK_SCRIPT):
                    run_interactive(["python3", CERT_CHECK_SCRIPT])
                else:
                    print(f"{Colors.RED}Certificate check tool not found.{Colors.RESET}")
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()

            elif choice == "20":
                run_ops_menu(sock)

            elif choice == "19":
                print("Bye.")
                break
            else:
                print(Colors.RED + "Invalid choice." + Colors.RESET)
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                prompt()
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}↩  Cancelled — returning to main menu.{Colors.RESET}")
            continue

if __name__ == "__main__":
    main()
