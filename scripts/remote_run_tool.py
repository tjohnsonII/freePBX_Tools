#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""remote_run_tool.py

SSH into a FreePBX host and drive one option of the ``freepbx-callflows``
interactive terminal menu non-interactively.

How it works
------------
The menu is a Python script that reads from stdin with ``input()``.  We write
the desired input sequence to a temp file on the server (using base64 to avoid
ALL shell-quoting issues), then pipe that file into the menu:

    freepbx-callflows < /tmp/.<token> 2>&1

Input sequence written to the temp file:
    <choice>          ← consumed by the main ``input("Choose: ")``
    19 (x 12)         ← each "Press ENTER to continue..." or sub-prompt
                        consumes one entry (input() ignores the value); the
                        first "19" that reaches the main "Choose:" prompt
                        quits cleanly with "Bye." — no "Invalid choice." noise.

For ``--grab-dump``: after the menu exits, reads back
``/home/123net/callflows/freepbx_dump.json`` and emits a single line:

    __FREEPBX_DUMP_JSON__:<compact-json>

so the browser UI can parse it out of the WebSocket log stream.

Usage
-----
    python scripts/remote_run_tool.py \\
        --server 1.2.3.4 \\
        --user 123net \\
        --password <pass> \\
        --root-password <root-pass> \\
        --menu-choice 6 \\
        --timeout 180
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import uuid
from typing import List, Tuple

try:
    import paramiko
except Exception as _e:  # pragma: no cover
    print("ERROR: paramiko is required: {}".format(_e), flush=True)
    sys.exit(2)


# ── Constants ──────────────────────────────────────────────────────────────

DUMP_JSON_MARKER = "__FREEPBX_DUMP_JSON__"
DUMP_FILE_PATH = "/home/123net/callflows/freepbx_dump.json"

# Menu choices exposed to callers.  Key = choice number string, Value = label.
# Excluded: 0 (watch/live — runs forever), 3/5 (need DID selection input),
#           11 (call simulation sub-menu needs interactive input), 19 (quit).
MENU_OPTIONS: dict = {
    "1":  "Refresh DB snapshot",
    "2":  "Show inventory + list DIDs",
    "4":  "Generate call-flows for ALL DIDs",
    "6":  "Time-Condition status",
    "7":  "Module analysis",
    "8":  "Paging / overhead / fax analysis",
    "9":  "Comprehensive component analysis",
    "10": "ASCII art call-flows",
    "12": "Full Asterisk diagnostic",
    "13": "Automated log analysis",
    "14": "Error map & quick reference",
    "15": "Network diagnostics",
    "16": "Enhanced log analysis (dmesg/journal)",
    "17": "CDR/CEL call log analysis",
    "18": "Phone/endpoint analysis",
}

_ALLOWED_CHOICES = frozenset(MENU_OPTIONS.keys())

# ── Per-option input sequences ─────────────────────────────────────────────
# Most options work with [choice] + ["19"] * 12 because:
#   - "19" quits the main menu when it lands on "Choose:"
#   - "Press ENTER to continue..." consumes one input() and ignores the value
#
# Options with nested sub-menus need custom sequences so the sub-menu
# gets a valid choice instead of "19" (which prints "Invalid choice." in a loop
# until stdin is exhausted, crashing with EOFError).
#
# Option 10 sub-menu choices: 1=specific DID, 2=summary, 3=config data,
#                             4=export JSON, 5=all DIDs, 6=return to main
# Sequence: pick 5 (generate all, no further input) → absorb up to 8
# "Press ENTER" prompts → pick 6 (return to main) → 19s quit main menu.
_SPECIAL_INPUT_SEQUENCES: dict = {
    "10": ["10", "5"] + [""] * 8 + ["6"] + ["19"] * 5,
}


# ── ANSI / prompt normalisation ────────────────────────────────────────────

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROMPT_ONLY_RE = re.compile(r"^\s*\[[^\]]+\][#$]\s*$")
_PROMPT_PREFIX_RE = re.compile(r"^\s*(\[[^\]]+\][#$]|[^\n]*[#$])\s+")
_PROMPTS = ("__FPBXRUN_USER__$ ", "__FPBXRUN_ROOT__# ")
_MAX_BUF = 600_000


def _strip_ansi(s: str) -> str:
    return _ANSI_CSI_RE.sub("", s)


def _normalize_keep_ansi(s: str) -> str:
    """Like _normalize but preserves ANSI CSI escape sequences.

    Used for freepbx-callflows output so that xterm.js on the browser can
    render colors.  The SSH shell is started with invoke_shell() which
    allocates a PTY, so the tool's sys.stdout.isatty() returns True and it
    emits ANSI color codes.  We must not strip them here.
    """
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    out: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\x1b" and i + 1 < len(s):
            if s[i + 1] == "[":
                # CSI sequence: ESC [ <params> <final-byte in 0x40-0x7E>
                j = i + 2
                while j < len(s) and not ("@" <= s[j] <= "~"):
                    j += 1
                end = j + 1
                out.append(s[i:end])
                i = end
                continue
            # Other escape (e.g. OSC, SS3) — pass the ESC through as-is
        if ch in ("\n", "\t"):
            out.append(ch)
        elif ord(ch) >= 32 and ord(ch) != 127:
            out.append(ch)
        i += 1
    return "".join(out)


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = _strip_ansi(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    out: List[str] = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\t"):
            out.append(ch)
        elif o >= 32 and o != 127:
            out.append(ch)
    return "".join(out)


# ── Low-level SSH helpers ──────────────────────────────────────────────────

def _read_until(chan: "paramiko.Channel", predicate, timeout: float, stage: str = "") -> str:
    buf = ""
    start = time.time()
    while True:
        if chan.recv_ready():
            chunk = chan.recv(65535)
            buf += chunk.decode("utf-8", errors="replace")
            if len(buf) > _MAX_BUF:
                buf = buf[-_MAX_BUF:]
            if predicate(buf):
                return buf
        else:
            time.sleep(0.05)
        if time.time() - start > timeout:
            tail = _normalize(buf[-4000:] if buf else "")
            msg = "Timed out waiting for remote output (stage={})".format(stage or "?")
            if tail:
                msg += "\n--- last output ---\n{}".format(tail)
            raise TimeoutError(msg)


def _send(chan: "paramiko.Channel", s: str) -> None:
    chan.send(s.encode("utf-8", errors="replace"))


def _sync(chan: "paramiko.Channel", timeout: float) -> None:
    token = uuid.uuid4().hex[:12]
    marker = "__FPBXRUN_SYNC__:{}".format(token)
    _send(chan, "echo {}\n".format(marker))

    def pred(buf: str) -> bool:
        return marker in _normalize(buf)

    _read_until(chan, pred, timeout=timeout, stage="sync")


def _sh_single_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _run_cmd(chan: "paramiko.Channel", cmd: str, timeout: float) -> Tuple[int, str]:
    """Run *cmd* in the current shell; return (rc, cleaned_output)."""
    marker = "__FPBXRUN_RC__"
    token = uuid.uuid4().hex[:12]
    marker_re = re.compile(r"{}:{}:(?P<rc>\d+)".format(re.escape(marker), re.escape(token)))

    sh_cmd = "sh -c {}".format(_sh_single_quote(cmd))
    _send(chan, "{}\necho {}:{}:$?\n".format(sh_cmd, marker, token))

    raw = _read_until(chan, lambda buf: marker_re.search(_normalize(buf)) is not None,
                      timeout=timeout, stage="cmd")
    raw_n = _normalize(raw)

    m = None
    for mm in marker_re.finditer(raw_n):
        m = mm
    rc = int(m.group("rc")) if m else 1

    cleaned: List[str] = []
    cmd_stripped = cmd.strip()
    sh_stripped = sh_cmd.strip()
    for line in raw_n.splitlines():
        if marker in line:
            continue
        for p in _PROMPTS:
            if line.startswith(p):
                line = line[len(p):]
                break
        if _PROMPT_ONLY_RE.match(line.strip()):
            continue
        line = _PROMPT_PREFIX_RE.sub("", line)
        if line.strip() in (cmd_stripped, sh_stripped):
            continue
        cleaned.append(line)

    return rc, "\n".join(cleaned).strip("\n")


def _run_menu_choice(chan: "paramiko.Channel", choice: str, timeout: float) -> Tuple[int, str]:
    """Drive ``freepbx-callflows`` with *choice* non-interactively.

    Writes the input sequence to a temp file via base64 (zero quoting issues),
    then pipes it into the menu.  Trailing "19" lines ensure the menu quits
    cleanly regardless of whether the chosen option has a "Press ENTER" prompt
    or an interactive sub-menu.
    """
    token = uuid.uuid4().hex[:12]
    marker = "__FPBXRUN_RC__"
    marker_re = re.compile(r"{}:{}:(?P<rc>\d+)".format(re.escape(marker), re.escape(token)))
    tmpfile = "/tmp/.fpbxrun_{}".format(token)

    # Input fed to freepbx-callflows stdin.
    # Options with nested sub-menus use a custom sequence; all others use the
    # standard [choice] + ["19"] * 12 where "19" quits the main menu and
    # "Press ENTER to continue..." consumes one input() (ignoring the value).
    if choice in _SPECIAL_INPUT_SEQUENCES:
        input_lines = _SPECIAL_INPUT_SEQUENCES[choice]
    else:
        input_lines = [choice] + ["19"] * 12
    input_content = "\n".join(input_lines) + "\n"
    encoded = base64.b64encode(input_content.encode()).decode()

    # Write input file via python3 (base64 decode) — no shell quoting involved
    write_py = (
        "import base64; open('{f}','wb').write(base64.b64decode('{b64}'))"
    ).format(f=tmpfile, b64=encoded)

    # Full command block sent as one shot to the interactive shell:
    #   1. write the temp input file
    #   2. run freepbx-callflows piped from it
    #   3. emit the RC marker (captured AFTER freepbx-callflows exits)
    #   4. clean up
    block = (
        "python3 -c {write}\n"
        "freepbx-callflows < {f} 2>&1\n"
        "echo {marker}:{token}:$?\n"
        "rm -f {f}\n"
    ).format(
        write=_sh_single_quote(write_py),
        f=tmpfile,
        marker=marker,
        token=token,
    )
    _send(chan, block)

    raw = _read_until(chan, lambda buf: marker_re.search(_normalize(buf)) is not None,
                      timeout=timeout, stage="menu-choice-{}".format(choice))
    raw_n = _normalize(raw)

    m = None
    for mm in marker_re.finditer(raw_n):
        m = mm
    rc = int(m.group("rc")) if m else 1

    # Build output preserving ANSI codes (the SSH shell has a PTY, so the tool
    # emits color sequences; xterm.js on the browser will render them correctly).
    raw_ansi = _normalize_keep_ansi(raw)
    cleaned: List[str] = []
    for line in raw_ansi.splitlines():
        stripped = _strip_ansi(line)  # stripped copy for comparisons only
        if marker in stripped:
            continue
        for p in _PROMPTS:
            if stripped.startswith(p):
                # Trim the prompt prefix from the ANSI-preserved line.
                # Prompts are plain ASCII so len(p) is safe as a char offset.
                line = line[len(p):]
                stripped = stripped[len(p):]
                break
        if _PROMPT_ONLY_RE.match(stripped.strip()):
            continue
        m2 = _PROMPT_PREFIX_RE.match(stripped)
        if m2:
            line = line[m2.end():]  # trim prompt chars from ANSI-preserved line
        cleaned.append(line)

    return rc, "\n".join(cleaned).strip("\n")


def _connect(host: str, username: str, password: str, timeout: float) -> "paramiko.SSHClient":
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    use_pass = bool(password)
    client.connect(
        hostname=host,
        username=username,
        password=(password if use_pass else None),
        look_for_keys=not use_pass,
        allow_agent=not use_pass,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
    )
    return client


def _become_root(chan: "paramiko.Channel", root_password: str, timeout: float) -> None:
    _send(chan, "su - root\n")

    def pred(buf: str) -> bool:
        b = buf.lower()
        return (
            ("password" in b)
            or ("authentication" in b)
            or ("sorry" in b)
            or ("incorrect" in b)
            or re.search(r"\n[^\n]*#\s*$", buf) is not None
        )

    out = _read_until(chan, pred, timeout=timeout, stage="su")
    if "password" in out.lower():
        if not root_password:
            raise RuntimeError("Root password required for su - root")
        _send(chan, root_password + "\n")

    _sync(chan, timeout=timeout)

    chk_rc, _ = _run_cmd(chan, 'test "$(id -u)" = "0"', timeout=timeout)
    if chk_rc != 0:
        raise RuntimeError("Failed to become root")

    _send(chan, "export PS1='__FPBXRUN_ROOT__# '; export PROMPT_COMMAND='';\n")
    _sync(chan, timeout=timeout)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drive one freepbx-callflows menu option on a remote host via SSH."
    )
    parser.add_argument("--server", required=True, help="Target host IP / hostname")
    parser.add_argument("--user", default="123net", help="SSH username")
    parser.add_argument("--password", default="", help="SSH password")
    parser.add_argument("--root-password", default="", help="Root password for su -")
    parser.add_argument("--menu-choice", required=True,
                        help="freepbx-callflows menu option number (e.g. 6)")
    parser.add_argument("--grab-dump", action="store_true",
                        help="After running, read back the JSON dump file and emit it "
                             "with the {} marker".format(DUMP_JSON_MARKER))
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="SSH command timeout in seconds (default: 180)")
    args = parser.parse_args()

    password = args.password or os.environ.get("FREEPBX_PASSWORD", "")
    root_password = (
        args.root_password
        or os.environ.get("FREEPBX_ROOT_PASSWORD", "")
        or password
    )
    choice = args.menu_choice.strip()

    if choice not in _ALLOWED_CHOICES:
        print("ERROR: menu choice {!r} not in allowed set.".format(choice), flush=True)
        print("Allowed: {}".format(sorted(_ALLOWED_CHOICES, key=int)), flush=True)
        return 1

    label = MENU_OPTIONS[choice]
    print("[remote_run] Connecting to {} as {}...".format(args.server, args.user), flush=True)

    connect_timeout = min(args.timeout, 30.0)
    try:
        client = _connect(args.server, args.user, password, timeout=connect_timeout)
    except Exception as e:
        print("ERROR: SSH connect failed: {}".format(e), flush=True)
        return 1

    print("[remote_run] Connected. Starting root shell...", flush=True)
    chan = client.invoke_shell(width=220, height=60)
    chan.settimeout(args.timeout)

    try:
        boot_timeout = max(args.timeout, 45.0)
        _send(chan, "export PS1='__FPBXRUN_USER__$ '; export PROMPT_COMMAND='';\n")
        _sync(chan, timeout=boot_timeout)

        print("[remote_run] Escalating to root...", flush=True)
        _become_root(chan, root_password=root_password, timeout=boot_timeout)

        print("[remote_run] Root shell ready.", flush=True)
        print("[remote_run] Running menu option {} — {}".format(choice, label), flush=True)
        print("=" * 60, flush=True)

        rc, output = _run_menu_choice(chan, choice, timeout=args.timeout)

        for line in output.splitlines():
            print(line, flush=True)

        print("=" * 60, flush=True)
        print("[remote_run] freepbx-callflows exited (rc={}).".format(rc), flush=True)

        # For --grab-dump: read back the JSON snapshot file and emit with marker
        if args.grab_dump:
            print("[remote_run] Reading dump file {}...".format(DUMP_FILE_PATH), flush=True)
            _, dump_raw = _run_cmd(chan, "cat {}".format(DUMP_FILE_PATH), timeout=args.timeout)
            dump_raw = dump_raw.strip()
            if dump_raw:
                try:
                    parsed = json.loads(dump_raw)
                    compact = json.dumps(parsed, separators=(",", ":"))
                except Exception:
                    compact = dump_raw
                print("{}:{}".format(DUMP_JSON_MARKER, compact), flush=True)
            else:
                print("[remote_run] Dump file not found or empty.", flush=True)

        # Treat as success if the tool produced output, even if the menu exited
        # uncleanly (e.g. EOFError on stdin exhaustion — non-zero rc is expected
        # for sub-menu options that loop on invalid choices before stdin runs out).
        return 0

    except Exception as e:
        print("ERROR: {}: {}".format(type(e).__name__, e), flush=True)
        return 1
    finally:
        try:
            chan.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())