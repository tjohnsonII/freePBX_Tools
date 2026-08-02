#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_call_leg_analyzer.py
-----------------------------
Correlates a single call's full path from CDR (and CEL, when available) into
one chronological, multi-leg trace — inbound route through transfers, ring
groups, queues, and hangup — instead of the flat, single-row-at-a-time
reporting the other CDR tools do. Answers "what actually happened to this
call" and "who hung up" for ticket troubleshooting.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).

CEL (Channel Event Logging) may not be enabled on every customer's Asterisk.
This tool self-detects CEL availability and gracefully degrades to CDR-only
correlation (which still works, since cdr.linkedid exists independent of
CEL) — it never hard-fails just because CEL is missing.

VARIABLE MAP (Key Script Variables)
-----------------------------------
Colors           : ANSI color codes for CLI output
ASTERISK_CDR_DB  : Primary database name for cdr/cel tables
ASTERISK_FALLBACK_DB : Fallback database name on older/nonstandard installs
DEFAULT_SOCK     : Default MySQL socket path
CACHE_DIR        : Where per-call trace JSON results are cached (permanent)
CDR_COLUMNS      : Ordered column list used for the CDR leg query
CAUSE_CODE_MAP   : Imported from freepbx_log_analyzer (SIP-code keyed)
Q850_TO_INFO     : Reverse index of CAUSE_CODE_MAP keyed by Q.850 cause,
                   since CEL's hangupcause is a raw Q.850 int, not a SIP code
args             : Parsed command-line arguments

    FUNCTION MAP (Major Functions)
    -----------------------------
    run_mysql                  : Run a SQL statement via the mysql CLI
    has_table / get_columns_ordered : Schema discovery helpers
    detect_cdr_db               : Pick asteriskcdrdb vs asterisk fallback
    normalize_number / build_number_candidates : Phone number normalization
    find_linkedids_for_number  : Search CDR for candidate linkedids
    get_cdr_legs                : Fetch all CDR rows for one linkedid
    cel_available / get_cel_events : CEL detection + fetch
    build_call_tree             : Nest CEL events into CDR legs by time window
    classify_leg_outcome        : Per-leg outcome (answered/no-answer/transfer/...)
    determine_hangup_initiator  : "Who hung up" heuristic
    render_tree / render_summary / render_verdict : Output formatting
    cache_path / load_cached_trace / save_cached_trace : Permanent per-call cache
    main                        : CLI entry point
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

try:
    import termios, tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False  # e.g. Windows — fall back to plain input()

# Make sibling-module imports work regardless of invocation cwd (matches how
# freepbx_callflow_menu.py already imports from freepbx_log_analyzer).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from freepbx_log_analyzer import CAUSE_CODE_MAP, format_cause_code
except ImportError:
    CAUSE_CODE_MAP = {}

    def format_cause_code(code_info):
        return ""


class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'


def prompt(msg=""):
    """Drop-in replacement for input() with backspace/delete handling that doesn't
    depend on the remote pty's own stty erase-char setting (mirrors the same helper
    in freepbx_callflow_menu.py — kept duplicated here since this script is meant to
    run standalone). Falls back to plain input() when stdin isn't a real tty."""
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
            elif ch in ("\x7f", "\x08"):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x15":
                while buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                sys.stdout.flush()
            elif ch == "\x03":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise KeyboardInterrupt
            elif ch == "\x04" and not buf:
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise EOFError
            elif ch >= " " or ch == "\t":
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return "".join(buf)


ASTERISK_CDR_DB = "asteriskcdrdb"
ASTERISK_FALLBACK_DB = "asterisk"
DEFAULT_SOCK = "/var/lib/mysql/mysql.sock"
CACHE_DIR = "/home/123net/callflows/call_leg_traces"

CDR_COLUMNS = [
    "calldate", "clid", "src", "dst", "dcontext", "channel", "dstchannel",
    "lastapp", "lastdata", "duration", "billsec", "disposition", "amaflags",
    "accountcode", "uniqueid", "userfield", "did", "recordingfile", "linkedid",
    "sequence", "peeraccount",
]

# CAUSE_CODE_MAP is keyed by SIP status code: {'480': (q850, desc, ast_cause, meaning), ...}
# CEL's hangupcause is a raw Q.850 int, so build a reverse index on the Q.850 field —
# calling lookup_cause_code() (SIP-keyed) directly on a Q.850 value would silently miss
# most real entries (e.g. 17, 18, 21, 34, 41 all collide/miss under SIP-code lookup).
Q850_TO_INFO = {}
for _sip, _tup in CAUSE_CODE_MAP.items():
    _q850, _desc, _ast, _meaning = _tup
    _key = str(_q850)
    _existing = Q850_TO_INFO.get(_key)
    # Prefer final-response SIP codes (4xx/5xx/6xx) over provisional 1xx ones
    # (e.g. 180 Ringing) when multiple SIP codes collide on the same Q.850
    # cause — a HANGUP event's cause is never "ringing", so that collision
    # would otherwise win purely on dict-iteration order and mislead the verdict.
    if _existing is None or _existing['sip'].startswith('1'):
        Q850_TO_INFO[_key] = {
            'sip': _sip, 'q850': _q850, 'description': _desc,
            'asterisk_cause': _ast, 'meaning': _meaning,
        }


def lookup_hangup_cause(q850_code):
    if q850_code in (None, ''):
        return None
    return Q850_TO_INFO.get(str(q850_code))


# ---------------------------
# mysql helpers (3.6 friendly) — mirrors freepbx_paging_fax_analyzer.py's convention
# ---------------------------

def run_mysql(sql, socket=None, user="root", password=None, db=ASTERISK_CDR_DB):
    """Run a SQL statement via mysql CLI and return stdout as text."""
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = ["mysql", "-BN"]
    if user:
        cmd += ["--user", str(user)]
    if socket:
        cmd += ["--socket", str(socket)]
    if db:
        cmd += [str(db)]
    cmd += ["-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True, env=env)
    if p.returncode != 0:
        return ""
    return p.stdout


def rows_as_dicts(sql, cols, **kw):
    """Run a SELECT that returns exactly len(cols) columns -> list[dict]."""
    out = run_mysql(sql, **kw).rstrip("\n")
    if not out:
        return []
    dicts = []
    for line in out.split("\n"):
        parts = line.split("\t")
        parts = (parts + [""] * len(cols))[:len(cols)]
        dicts.append(dict(zip(cols, parts)))
    return dicts


def get_tables(**kw):
    return set(run_mysql("SHOW TABLES;", **kw).split())


def has_table(t, **kw):
    return t in get_tables(**kw)


def get_columns_ordered(table, **kw):
    """DESCRIBE table -> ordered column-name list (needed to zip SELECT * rows;
    unlike a set, this preserves the order mysql returns the columns in)."""
    lines = run_mysql("DESCRIBE `%s`;" % table, **kw).splitlines()
    return [ln.split("\t", 1)[0] for ln in lines if ln.strip()]


def detect_cdr_db(**kw):
    """Most installs use asteriskcdrdb for cdr/cel; some route it into asterisk.
    Detect once rather than assuming."""
    if has_table('cdr', db=ASTERISK_CDR_DB, **kw):
        return ASTERISK_CDR_DB
    return ASTERISK_FALLBACK_DB


# ---------------------------
# Phone number normalization — no existing helper anywhere in the codebase to reuse
# ---------------------------

def normalize_number(raw):
    """Return NANP-normalized digit string; short inputs pass through as extensions."""
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def build_number_candidates(raw):
    """Return the literal strings to match against cdr.src/cdr.dst."""
    digits = normalize_number(raw)
    if not digits:
        return []
    if len(digits) <= 5:
        return [digits]  # extension-shaped input, match verbatim only
    if len(digits) != 10:
        return [digits]  # unrecognized shape; fall back to literal digit match
    return [digits, '1' + digits, '+1' + digits]


def sanitize_linkedid(raw):
    """linkedid values are always epoch.sequence-style (digits, dots, dashes);
    strip anything else before it ever reaches SQL interpolation or a filename."""
    return re.sub(r'[^A-Za-z0-9._-]', '', raw or '')


# ---------------------------
# CDR / CEL data access
# ---------------------------

def resolve_time_window(args):
    if args.start and args.end:
        return args.start, args.end
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=args.hours)
    return start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")


def find_linkedids_for_number(number, start, end, limit, **kw):
    candidates = build_number_candidates(number)
    if not candidates:
        return []
    clauses = " OR ".join("(src='%s' OR dst='%s')" % (c, c) for c in candidates)
    sql = (
        "SELECT linkedid, MIN(calldate) AS first_seen, MIN(src) AS src, MIN(dst) AS dst, "
        "MIN(disposition) AS disposition, SUM(duration) AS duration "
        "FROM cdr WHERE calldate BETWEEN '%s' AND '%s' AND (%s) "
        "GROUP BY linkedid ORDER BY first_seen DESC LIMIT %d;"
        % (start, end, clauses, int(limit))
    )
    cols = ["linkedid", "first_seen", "src", "dst", "disposition", "duration"]
    return rows_as_dicts(sql, cols, **kw)


def get_cdr_legs(linkedid, **kw):
    lid = sanitize_linkedid(linkedid)
    sql = (
        "SELECT " + ", ".join(CDR_COLUMNS) + " FROM cdr WHERE linkedid = '" + lid + "' "
        "ORDER BY calldate ASC, sequence ASC, uniqueid ASC;"
    )
    return rows_as_dicts(sql, CDR_COLUMNS, **kw)


def cel_available(**kw):
    if not has_table('cel', **kw):
        return False
    return bool(run_mysql("SELECT 1 FROM cel LIMIT 1;", **kw).strip())


def get_cel_events(linkedid, **kw):
    lid = sanitize_linkedid(linkedid)
    cols = get_columns_ordered('cel', **kw)
    if not cols:
        return []
    sql = "SELECT * FROM cel WHERE linkedid = '" + lid + "' ORDER BY id ASC;"
    return rows_as_dicts(sql, cols, **kw)


def parse_cel_extra(row):
    """Best-effort parse of a CEL row's JSON extra-data blob, wherever it lives —
    CEL's JSON column name/shape varies across Asterisk versions/backends, so
    scan every column for something JSON-object-shaped rather than assuming a
    fixed column name. Falls back to directly-named columns if present."""
    parsed = {}
    for _key, val in row.items():
        if not val:
            continue
        v = val.strip()
        if v.startswith('{') and v.endswith('}'):
            try:
                obj = json.loads(v)
                if isinstance(obj, dict):
                    parsed.update(obj)
            except (ValueError, TypeError):
                continue
    for key in ('hangupcause', 'hangupsource'):
        if row.get(key) and key not in parsed:
            parsed[key] = row[key]
    return parsed


def parse_dt(value):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.min


# ---------------------------
# Call tree construction
# ---------------------------

def classify_leg_outcome(cdr, leg_cel_events):
    eventtypes = set(e.get('eventtype') for e in leg_cel_events)
    if 'BLINDTRANSFER' in eventtypes:
        return 'TRANSFERRED_OUT (blind)'
    if 'ATTENDEDTRANSFER' in eventtypes:
        return 'TRANSFERRED_OUT (attended)'
    disposition = (cdr.get('disposition') or '').upper()
    if disposition == 'ANSWERED':
        return 'ANSWERED_HANGUP'
    if disposition == 'NO ANSWER':
        return 'RING_NO_ANSWER'
    if disposition == 'BUSY':
        return 'BUSY'
    if disposition == 'FAILED':
        return 'FAILED'
    return disposition or 'UNKNOWN'


def build_call_tree(cdr_legs, cel_events, cel_status):
    legs = []
    n = len(cdr_legs)
    for i, cdr in enumerate(cdr_legs):
        leg_start = parse_dt(cdr.get('calldate', ''))
        is_last = (i + 1 >= n)
        if not is_last:
            leg_end = parse_dt(cdr_legs[i + 1].get('calldate', ''))
        else:
            try:
                dur = int(cdr.get('duration') or 0)
            except ValueError:
                dur = 0
            leg_end = leg_start + timedelta(seconds=dur if dur > 0 else 300)
        leg_cel = []
        if cel_events:
            # Asterisk defines duration as (hangup time - start time), so the last
            # leg's HANGUP event lands exactly ON leg_end — an exclusive upper bound
            # would silently drop it from the displayed evidence. Only intermediate
            # legs use an exclusive bound (next leg's start belongs to that leg, not this one).
            if is_last:
                leg_cel = [e for e in cel_events
                           if leg_start <= parse_dt(e.get('eventtime', '')) <= leg_end]
            else:
                leg_cel = [e for e in cel_events
                           if leg_start <= parse_dt(e.get('eventtime', '')) < leg_end]
        outcome = classify_leg_outcome(cdr, leg_cel)
        legs.append({
            'leg_index': i + 1,
            'cdr': cdr,
            'outcome': outcome,
            'cel_events': leg_cel,
        })
    return {
        'linkedid': cdr_legs[0]['linkedid'] if cdr_legs else None,
        'legs': legs,
        'cel_status': cel_status,
    }


def determine_hangup_initiator(cdr_legs, cel_events, cel_status):
    if cel_status != 'ok':
        final_disp = (cdr_legs[-1].get('disposition') or '').upper() if cdr_legs else ''
        if final_disp == 'NO ANSWER':
            explanation = ("Call was not answered before the leg ended; cannot determine "
                            "whether the caller abandoned or the ring timer expired without CEL data.")
        elif final_disp == 'ANSWERED':
            explanation = ("Call connected and ended; CDR alone cannot show which party "
                            "disconnected first.")
        else:
            explanation = "Insufficient evidence to determine hangup initiator without CEL data."
        return {'initiator': 'unknown', 'confidence': 'LOW', 'cause': None, 'explanation': explanation}

    hangups = [e for e in cel_events if e.get('eventtype') == 'HANGUP']
    if not hangups:
        return {'initiator': 'unknown', 'confidence': 'LOW', 'cause': None,
                'explanation': 'No HANGUP events found in CEL data for this call.'}

    first_leg_channel = cdr_legs[0].get('channel') if cdr_legs else None
    last_leg_dst_channel = cdr_legs[-1].get('dstchannel') if cdr_legs else None

    # Primary: explicit hangupsource field (authoritative when populated)
    for h in hangups:
        extra = parse_cel_extra(h)
        source = extra.get('hangupsource')
        if source:
            if first_leg_channel and source == first_leg_channel:
                who = 'caller'
            elif last_leg_dst_channel and source == last_leg_dst_channel:
                who = 'called party / agent'
            else:
                who = 'system/other channel (%s)' % source
            return {
                'initiator': who, 'channel': source, 'cause': extra.get('hangupcause'),
                'confidence': 'HIGH',
                'explanation': 'hangupsource field on the HANGUP event identifies %s as the initiator.' % source,
            }

    # Fallback: earliest HANGUP eventtime among the legs
    hangups_sorted = sorted(hangups, key=lambda e: parse_dt(e.get('eventtime', '')))
    earliest = hangups_sorted[0]
    channel = earliest.get('channame')
    if first_leg_channel and channel == first_leg_channel:
        who = 'caller'
    elif last_leg_dst_channel and channel == last_leg_dst_channel:
        who = 'called party / agent'
    else:
        who = 'channel %s' % channel
    extra = parse_cel_extra(earliest)
    return {
        'initiator': who, 'channel': channel, 'cause': extra.get('hangupcause'),
        'confidence': 'MEDIUM',
        'explanation': ('Inferred from earliest HANGUP event timing (channel %s); hangupsource '
                         'was not populated, so this is an inference, not an explicit field.') % channel,
    }


# ---------------------------
# Rendering
# ---------------------------

def print_cel_notice(cel_status):
    if cel_status == 'missing':
        print(f"\n{Colors.YELLOW}⚠  CEL is not enabled on this system (no `cel` table found).{Colors.RESET}")
        print(f"{Colors.YELLOW}   Falling back to CDR-only correlation — multi-leg grouping still works{Colors.RESET}")
        print(f"{Colors.YELLOW}   via linkedid, but per-channel ring/answer/transfer/hangup detail and{Colors.RESET}")
        print(f"{Colors.YELLOW}   hangup-initiator detection will be unavailable (confidence will be LOW).{Colors.RESET}")
        print(f"{Colors.YELLOW}   To enable CEL for future calls: set enable=yes in /etc/asterisk/cel.conf{Colors.RESET}")
        print(f"{Colors.YELLOW}   and configure a CEL backend (e.g. cel_odbc.conf) pointing at this DB.{Colors.RESET}")
    elif cel_status == 'present_no_data':
        print(f"\n{Colors.YELLOW}ℹ  CEL table exists but has no events for this call (may predate when{Colors.RESET}")
        print(f"{Colors.YELLOW}   CEL was enabled). Falling back to CDR-only correlation for this trace.{Colors.RESET}")


def render_tree(call_tree):
    legs = call_tree['legs']
    print(f"\n{Colors.CYAN}{Colors.BOLD}Call Leg Trace — linkedid {call_tree['linkedid']}{Colors.RESET}\n")
    for leg in legs:
        cdr = leg['cdr']
        indent = "  " * (leg['leg_index'] - 1)
        arrow = "└─ " if leg['leg_index'] > 1 else ""
        print(f"{indent}{arrow}{Colors.GREEN}Leg {leg['leg_index']}{Colors.RESET}  "
              f"{cdr.get('calldate', '?')}  {cdr.get('src', '?')} -> {cdr.get('dst', '?')}  "
              f"[{cdr.get('dcontext', '?')}]  app={cdr.get('lastapp', '?')}({cdr.get('lastdata', '')})")
        print(f"{indent}   disposition={cdr.get('disposition', '?')}  duration={cdr.get('duration', '0')}s  "
              f"billsec={cdr.get('billsec', '0')}s  outcome={Colors.CYAN}{leg['outcome']}{Colors.RESET}")
        for ev in leg['cel_events']:
            print(f"{indent}   {Colors.MAGENTA}CEL{Colors.RESET} {ev.get('eventtime', '?')}  "
                  f"{ev.get('eventtype', '?'):<18} {ev.get('channame', '')}")


def render_summary(call_tree, hangup_info):
    legs = call_tree['legs']
    if not legs:
        print(f"{Colors.YELLOW}No legs found.{Colors.RESET}")
        return
    first = legs[0]['cdr']
    print(f"\n{Colors.CYAN}{Colors.BOLD}Call summary — linkedid {call_tree['linkedid']}{Colors.RESET}")
    print(f"  Inbound caller: {first.get('src')}")
    print(f"  Called number:  {first.get('dst')}")
    print(f"  Start:          {first.get('calldate')}")
    print(f"  Legs:           {len(legs)}")
    print(f"  Final outcome:  {legs[-1]['outcome']}")
    print(f"  Hangup:         {hangup_info.get('initiator', 'unknown')} "
          f"({hangup_info.get('confidence', 'LOW')} confidence)")


def _generic_cause_text(cdr):
    disp = (cdr.get('disposition') or '').upper()
    if disp == 'NO ANSWER':
        return "No answer before timeout (no Q.850 detail available without CEL)."
    if disp == 'BUSY':
        return "Destination busy."
    if disp == 'FAILED':
        return "Call failed — check trunk/route configuration."
    if disp == 'ANSWERED':
        return "Normal call completion."
    return "Unknown — insufficient evidence."


def _verdict_sentence(call_tree, hangup_info):
    last = call_tree['legs'][-1]
    outcome = last['outcome']
    cdr = last['cdr']
    who = hangup_info.get('initiator', 'unknown') if hangup_info else 'unknown'
    if outcome == 'RING_NO_ANSWER':
        return (f"Caller disconnected after {cdr.get('duration', '0')}s while "
                f"{cdr.get('dst', 'the destination')} was ringing; no one answered.")
    if outcome == 'ANSWERED_HANGUP':
        return (f"Call was answered and lasted {cdr.get('billsec', cdr.get('duration', '0'))}s; "
                f"{who} ended the call.")
    if outcome.startswith('TRANSFERRED_OUT'):
        return f"Call was transferred during this session ({outcome})."
    if outcome == 'BUSY':
        return f"Call reached {cdr.get('dst', 'the destination')} and received a busy signal."
    if outcome == 'FAILED':
        return f"Call failed to complete to {cdr.get('dst', 'the destination')}."
    return f"Call ended with disposition {cdr.get('disposition', 'UNKNOWN')}."


def _recommended_action(call_tree):
    if call_tree.get('cel_status') != 'ok':
        return ("Enable CEL logging (cel.conf + a CEL backend) for definitive hangup-initiator "
                "detection on future calls.")
    outcome = call_tree['legs'][-1]['outcome']
    if outcome == 'RING_NO_ANSWER':
        return "Confirm the destination extension/device was actually ringing (not DND/unregistered) during this window."
    if outcome == 'ANSWERED_HANGUP':
        return "No PBX correction indicated; this looks like normal call completion."
    return "Review the evidence lines above for the specific failure point."


def render_verdict(call_tree, hangup_info):
    legs = call_tree['legs']
    if not legs:
        return

    print(f"\n{Colors.CYAN}{Colors.BOLD}Verdict:{Colors.RESET} {_verdict_sentence(call_tree, hangup_info)}")

    print(f"{Colors.CYAN}{Colors.BOLD}Evidence:{Colors.RESET}")
    for leg in legs:
        cdr = leg['cdr']
        print(f"  - CDR leg {leg['leg_index']}  {cdr.get('calldate')}  "
              f"src={cdr.get('src')} dst={cdr.get('dst')} dcontext={cdr.get('dcontext')} "
              f"lastapp={cdr.get('lastapp')} disposition={cdr.get('disposition')} "
              f"billsec={cdr.get('billsec')}")
        for ev in leg['cel_events']:
            if ev.get('eventtype') in ('HANGUP', 'BLINDTRANSFER', 'ATTENDEDTRANSFER', 'ANSWER'):
                extra = parse_cel_extra(ev)
                extra_str = (" extra=" + json.dumps(extra)) if extra else ""
                print(f"  - CEL  {ev.get('eventtime')}  {ev.get('eventtype')}  "
                      f"{ev.get('channame')}{extra_str}")

    cause_info = lookup_hangup_cause(hangup_info.get('cause')) if hangup_info else None
    likely_cause = format_cause_code(cause_info) if cause_info else _generic_cause_text(legs[-1]['cdr'])
    print(f"{Colors.CYAN}{Colors.BOLD}Likely cause:{Colors.RESET} {likely_cause}")
    print(f"{Colors.CYAN}{Colors.BOLD}Confidence:{Colors.RESET} {hangup_info.get('confidence', 'LOW')}")
    print(f"{Colors.CYAN}{Colors.BOLD}Recommended next action:{Colors.RESET} {_recommended_action(call_tree)}")


# ---------------------------
# Cache — permanent (a finished call's rows never change), unlike freepbx_dump.py's
# staleness-tracked config snapshot
# ---------------------------

def cache_path(linkedid):
    return os.path.join(CACHE_DIR, sanitize_linkedid(linkedid) + ".json")


def load_cached_trace(linkedid):
    path = cache_path(linkedid)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def save_cached_trace(linkedid, data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path(linkedid), "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except OSError:
        pass


# ---------------------------
# CLI
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
        description="FreePBX full call-leg analysis (CDR + CEL correlation, one call, start to finish)")
    parser.add_argument("--linkedid", help="Trace this exact linkedid")
    parser.add_argument("--number", help="Phone number to search for candidate linkedids (any format)")
    parser.add_argument("--hours", type=int, default=72, help="Search window in hours for --number (default: 72)")
    parser.add_argument("--start", help="Explicit search start 'YYYY-MM-DD HH:MM:SS' (overrides --hours)")
    parser.add_argument("--end", help="Explicit search end 'YYYY-MM-DD HH:MM:SS' (overrides --hours)")
    parser.add_argument("--limit", type=int, default=15, help="Max candidate linkedids to list (default: 15)")
    parser.add_argument("--pick", type=int, help="Non-interactively select candidate #N from the list")
    parser.add_argument("--format", choices=["tree", "summary", "json"], default="tree",
                         help="Output format (default: tree)")
    parser.add_argument("--no-cache", action="store_true", help="Force re-query even if a cached trace exists")
    parser.add_argument("--out", help="Also write the JSON result to this file")
    parser.add_argument("--db-user", default="root", help="MySQL username")
    parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
    args = parser.parse_args()

    try:
        if os.geteuid() != 0:  # type: ignore
            print(f"{Colors.YELLOW}⚠️  This tool requires root access to query the database{Colors.RESET}")
            sys.exit(1)
    except AttributeError:
        pass  # Windows doesn't have geteuid

    if not args.linkedid and not args.number:
        parser.error("either --linkedid or --number is required")

    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 78}")
    print(f"  \U0001F4DE FREEPBX CALL-LEG ANALYZER")
    print(f"{'=' * 78}{Colors.RESET}")

    kw = {"socket": args.socket, "user": args.db_user}
    kw["db"] = detect_cdr_db(**kw)

    linkedid = args.linkedid
    if not linkedid:
        start, end = resolve_time_window(args)
        candidates = find_linkedids_for_number(args.number, start, end, args.limit, **kw)
        if not candidates:
            print(f"{Colors.YELLOW}No calls found matching '{args.number}' in the given window.{Colors.RESET}")
            sys.exit(0)
        if len(candidates) == 1:
            linkedid = candidates[0]['linkedid']
        elif args.pick is not None:
            idx = args.pick - 1
            if idx < 0 or idx >= len(candidates):
                print(f"{Colors.RED}--pick out of range (1-{len(candidates)}){Colors.RESET}")
                sys.exit(1)
            linkedid = candidates[idx]['linkedid']
        else:
            print(f"\n{Colors.CYAN}{Colors.BOLD}Candidate calls matching '{args.number}':{Colors.RESET}")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}) {c['first_seen']}  {c['src']} -> {c['dst']}  "
                      f"{c['disposition']}  {c['duration']}s  linkedid={c['linkedid']}")
            sel = prompt(f"\n{Colors.YELLOW}Select a call (1-{len(candidates)}): {Colors.RESET}").strip()
            try:
                linkedid = candidates[int(sel) - 1]['linkedid']
            except (ValueError, IndexError):
                print(f"{Colors.RED}Invalid selection.{Colors.RESET}")
                sys.exit(1)

    cached = None if args.no_cache else load_cached_trace(linkedid)
    if cached is not None:
        call_tree, hangup_info = cached['call_tree'], cached['hangup_info']
    else:
        cdr_legs = get_cdr_legs(linkedid, **kw)
        if not cdr_legs:
            print(f"{Colors.RED}No CDR rows found for linkedid {linkedid}{Colors.RESET}")
            sys.exit(1)
        cel_status = 'missing'
        cel_events = []
        if cel_available(**kw):
            cel_events = get_cel_events(linkedid, **kw)
            cel_status = 'ok' if cel_events else 'present_no_data'
        call_tree = build_call_tree(cdr_legs, cel_events, cel_status)
        hangup_info = determine_hangup_initiator(cdr_legs, cel_events, cel_status)
        save_cached_trace(linkedid, {'call_tree': call_tree, 'hangup_info': hangup_info})

    if args.out:
        try:
            with open(args.out, 'w') as f:
                json.dump({'call_tree': call_tree, 'hangup_info': hangup_info}, f, indent=2, sort_keys=True)
            print(f"{Colors.GREEN}✅ Wrote {args.out}{Colors.RESET}")
        except OSError as e:
            print(f"{Colors.RED}Failed to write {args.out}: {e}{Colors.RESET}")

    if call_tree.get('cel_status') != 'ok':
        print_cel_notice(call_tree['cel_status'])

    if args.format == 'tree':
        render_tree(call_tree)
        render_verdict(call_tree, hangup_info)
    elif args.format == 'summary':
        render_summary(call_tree, hangup_info)
    else:
        print(json.dumps({'call_tree': call_tree, 'hangup_info': hangup_info}, indent=2, sort_keys=True))

    print(f"\n{Colors.GREEN}✅ Analysis complete{Colors.RESET}\n")


if __name__ == "__main__":
    main()
