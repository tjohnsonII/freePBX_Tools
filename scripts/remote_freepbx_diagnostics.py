#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remote FreePBX diagnostics collector.

Runs on the operator machine (Windows/macOS/Linux) and gathers live PBX health data
from a remote FreePBX host over SSH.

Design goals:
- No Python DB drivers; use remote CLI tools (mysql, asterisk, systemctl)
- Works with root escalation via `su - root` (root password provided)
- Emits JSON only (safe for web/API consumption)

Expected use:
    python scripts/remote_freepbx_diagnostics.py --server 1.2.3.4 --user 123net --password ... --root-password ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


try:
    import paramiko
except Exception as e:  # pragma: no cover
    sys.stderr.write("ERROR: paramiko is required to run this tool: {}\n".format(e))
    sys.exit(2)


_PROMPTS = ("__FREEPBXTOOLS_USER__$ ", "__FREEPBXTOOLS_ROOT__# ")

# Generic prompt patterns (best-effort). We avoid relying on these for control flow,
# but use them to clean output when remote shells don't honor our PS1.
_PROMPT_ONLY_RE = re.compile(r"^\s*\[[^\]]+\][#$]\s*$")
_PROMPT_PREFIX_RE = re.compile(r"^\s*(\[[^\]]+\][#$]|[^\n]*[#$])\s+")

# Match ANSI CSI escape sequences (color, cursor movement, etc.).
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# Cap interactive-shell captured output to avoid unbounded memory growth while
# still being large enough that a marker cannot be pushed out by a single burst
# of banner/MOTD output.
_MAX_SHELL_BUF_CHARS = 600_000


def _strip_ansi(s: str) -> str:
    return _ANSI_CSI_RE.sub("", s)


def _normalize_text(s: str) -> str:
    """Normalize interactive shell output for reliable matching.

    - Strip ANSI CSI escape sequences (colors)
    - Normalize CRLF/CR to LF
    - Drop other control characters that can split tokens
    """

    if not s:
        return ""
    s = _strip_ansi(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    out_chars: List[str] = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\t"):
            out_chars.append(ch)
            continue
        # Keep printable ASCII/Unicode, drop control chars.
        if o >= 32 and o != 127:
            out_chars.append(ch)
    return "".join(out_chars)


@dataclass
class CmdResult:
    rc: int
    out: str


def _now_utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_until(chan: "paramiko.Channel", predicate, timeout: float, stage: str = "") -> str:
    buf = ""
    start = time.time()
    while True:
        if chan.recv_ready():
            chunk = chan.recv(65535)
            try:
                text = chunk.decode("utf-8", errors="replace")
            except Exception:
                text = str(chunk)
            buf += text

            # Keep a rolling window to avoid pathological MOTDs filling memory.
            if len(buf) > _MAX_SHELL_BUF_CHARS:
                buf = buf[-_MAX_SHELL_BUF_CHARS:]

            if predicate(buf):
                return buf
        else:
            time.sleep(0.05)

        if time.time() - start > timeout:
            tail = _normalize_text(buf[-8000:] if buf else "")
            msg = "Timed out waiting for remote output"
            if stage:
                msg += " (stage={})".format(stage)
            if tail:
                msg += "\n--- last output ---\n{}".format(tail)
            raise TimeoutError(msg)


def _shell_send(chan: "paramiko.Channel", s: str) -> None:
    # Paramiko stubs type Channel.send() as bytes-like; encode for consistency.
    chan.send(s.encode("utf-8", errors="replace"))


def _sync_shell(chan: "paramiko.Channel", timeout: float) -> None:
    """Synchronize with an interactive shell without relying on prompts.

    Prompts differ across shells (bash/sh/csh) and across OSes (Linux vs FreeBSD).
    We only need a reliable way to know the remote has processed our input.
    """

    token = uuid.uuid4().hex[:12]
    marker = "__FREEPBXTOOLS_SYNC__:{}".format(token)
    _shell_send(chan, "echo {}\n".format(marker))

    def _pred(buf: str) -> bool:
        # Search the rolling buffer. Looking only at a small tail can miss the
        # marker if a large banner arrives after it in the same recv burst.
        return marker in _normalize_text(buf)

    _read_until(chan, _pred, timeout=timeout, stage="sync")


def _sh_single_quote(s: str) -> str:
    # Wrap in single-quotes and escape embedded single-quotes.
    # Example: abc'def -> 'abc'"'"'def'
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _run_shell_cmd(chan: "paramiko.Channel", cmd: str, timeout: float) -> CmdResult:
    # Run via `sh -c` so we get consistent POSIX semantics regardless of the
    # user's/root's login shell (bash/sh/csh).
    marker = "__FREEPBX_DIAG_MARKER__"
    token = uuid.uuid4().hex[:12]
    marker_re = re.compile(r"{}:{}:(?P<rc>\d+)".format(re.escape(marker), re.escape(token)))

    # IMPORTANT: use `sh -c '<cmd>'` with safe single-quote escaping.
    # This keeps pipelines/redirects and `$?` behavior consistent.
    sh_cmd = "sh -c {}".format(_sh_single_quote(cmd))

    full = "{}\n".format(sh_cmd)
    full += "echo {}:{}:$?\n".format(marker, token)
    _shell_send(chan, full)

    def _pred(buf: str) -> bool:
        # Search the rolling buffer. Looking only at a tail can miss markers when
        # the server prints a large login banner/MOTD after the marker.
        return marker_re.search(_normalize_text(buf)) is not None

    raw = _read_until(chan, _pred, timeout=timeout, stage="cmd")

    # Extract rc from the last marker occurrence.
    m = None
    raw_no_ansi = _normalize_text(raw)
    for mm in marker_re.finditer(raw_no_ansi):
        m = mm
    rc = int(m.group("rc")) if m else 1

    # Clean interactive shell artifacts: strip our prompts, drop echoed input lines, and
    # remove any marker lines (both echoed input and the marker output).
    cleaned_lines: List[str] = []
    cmd_stripped = cmd.strip()
    sh_cmd_stripped = sh_cmd.strip()
    for line in raw_no_ansi.splitlines():
        # Drop marker lines completely.
        if marker in line:
            continue

        # Strip known prompts (if present).
        for p in _PROMPTS:
            if line.startswith(p):
                line = line[len(p) :]
                break

        # Drop prompt-only lines from unknown PS1 formats.
        if _PROMPT_ONLY_RE.match(line.strip()):
            continue

        # If a prompt was included at the start of a line, strip it.
        line = _PROMPT_PREFIX_RE.sub("", line)

        # Drop echoed input lines (either the raw command or our sh wrapper).
        if line.strip() == cmd_stripped or line.strip() == sh_cmd_stripped:
            continue

        cleaned_lines.append(line)

    out_clean = "\n".join(cleaned_lines).strip("\n")
    return CmdResult(rc=rc, out=out_clean)


def _connect(host: str, username: str, password: str, timeout: float) -> "paramiko.SSHClient":
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    use_password = bool(password)

    client.connect(
        hostname=host,
        username=username,
        password=(password if use_password else None),
        # On Windows, agent/key discovery can be surprisingly slow and may cause
        # the whole diagnostics call to time out. If a password was provided,
        # prefer password auth only.
        look_for_keys=not use_password,
        allow_agent=not use_password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
    )
    return client


def _become_root(chan: "paramiko.Channel", root_password: str, timeout: float) -> None:
    # Attempt `su - root` and set a deterministic prompt.
    _shell_send(chan, "su - root\n")

    def _pred(buf: str) -> bool:
        b = buf.lower()
        # Detect a password prompt, a failure, or an apparent root prompt.
        return (
            ("password" in b)
            or ("authentication" in b)
            or ("sorry" in b)
            or ("incorrect" in b)
            or re.search(r"\n[^\n]*#\s*$", buf) is not None
        )

    out = _read_until(chan, _pred, timeout=timeout, stage="su")

    if "password" in out.lower():
        if not root_password:
            raise RuntimeError("Root password required for su - root")
        _shell_send(chan, root_password + "\n")

    # Sync and validate we are actually root.
    _sync_shell(chan, timeout=timeout)

    # Validate root via return code to avoid prompt/banner contamination.
    # (Some systems print the prompt as a standalone line, which can confuse
    # output-based checks.)
    chk = _run_shell_cmd(chan, 'test "$(id -u)" = "0"', timeout=timeout)
    if chk.rc != 0:
        # Preserve any cleaned output for debugging.
        raise RuntimeError("Failed to become root" + (" (details={!r})".format(chk.out) if chk.out else ""))

    # Best-effort: set a deterministic prompt after becoming root.
    _shell_send(chan, "export PS1='__FREEPBXTOOLS_ROOT__# '; export PROMPT_COMMAND='';\n")
    _sync_shell(chan, timeout=timeout)


def _parse_active_calls(text: str) -> Optional[int]:
    for line in text.splitlines():
        l = line.lower()
        if "active" in l and ("call" in l or "channel" in l):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


def _parse_pjsip_contacts(text: str) -> List[str]:
    # Count unique endpoint IDs from lines like:
    # Contact: 100/sip:100@1.2.3.4:5060;...
    endpoints = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Contact:"):
            continue
        rest = line[len("Contact:") :].strip()
        endpoint = rest.split("/", 1)[0].strip()
        if endpoint:
            endpoints.add(endpoint)
    return sorted(endpoints)


def collect_one(host: str, username: str, password: str, root_password: str, timeout: float) -> Dict:
    client = _connect(host, username, password, timeout=timeout)
    try:
        chan = client.invoke_shell(width=200, height=60)
        chan.settimeout(timeout)

        # FreePBX often prints a large banner (MOTD/network info) on login and/or `su -`.
        # Give the initial handshake/escalation a bit more time than per-command timeouts.
        boot_timeout = max(timeout, 45.0)

        # Sync with the remote interactive shell.
        # Best-effort: set deterministic user prompt for cleaner output.
        _shell_send(chan, "export PS1='__FREEPBXTOOLS_USER__$ '; export PROMPT_COMMAND='';\n")
        _sync_shell(chan, timeout=boot_timeout)
        _become_root(chan, root_password=root_password, timeout=boot_timeout)

        # Meta
        hostname = _run_shell_cmd(chan, "hostname", timeout=timeout).out.strip().splitlines()[-1].strip()

        freepbx_ver = _run_shell_cmd(
            chan,
            "(cat /etc/schmooze/pbx-version 2>/dev/null | head -n 1) || (fwconsole -V 2>/dev/null | head -n 1) || echo 'N/A'",
            timeout=timeout,
        ).out.strip().splitlines()[-1].strip()

        ast_ver_line = _run_shell_cmd(
            chan,
            "asterisk -rx 'core show version' 2>/dev/null | head -n 1 || echo 'N/A'",
            timeout=timeout,
        ).out.strip().splitlines()[-1].strip()

        # Active calls
        calls_raw = _run_shell_cmd(chan, "asterisk -rx 'core show channels count' 2>/dev/null || true", timeout=timeout).out
        active_calls = _parse_active_calls(calls_raw)

        # Endpoints
        total_ext_raw = _run_shell_cmd(
            chan,
            "mysql -NBe \"SELECT COUNT(*) FROM users\" asterisk 2>/dev/null || echo ''",
            timeout=timeout,
        ).out.strip().splitlines()
        total_endpoints = None
        if total_ext_raw:
            tail = total_ext_raw[-1].strip()
            if tail.isdigit():
                total_endpoints = int(tail)

        contacts_raw = _run_shell_cmd(chan, "asterisk -rx 'pjsip show contacts' 2>/dev/null || true", timeout=timeout).out
        registered_endpoints = _parse_pjsip_contacts(contacts_raw)

        reg_count = len(registered_endpoints)
        total = int(total_endpoints) if total_endpoints is not None else None
        unreg_count = (total - reg_count) if (total is not None) else None

        # Time conditions
        tc_total_raw = _run_shell_cmd(
            chan,
            "mysql -NBe \"SELECT COUNT(*) FROM timeconditions\" asterisk 2>/dev/null || echo '0'",
            timeout=timeout,
        ).out.strip().splitlines()
        tc_total = int(tc_total_raw[-1].strip()) if tc_total_raw and tc_total_raw[-1].strip().isdigit() else 0

        forced_count = 0
        has_inuse = _run_shell_cmd(
            chan,
            "mysql -NBe \"SHOW COLUMNS FROM timeconditions LIKE 'inuse_state'\" asterisk 2>/dev/null | wc -l",
            timeout=timeout,
        ).out.strip().splitlines()
        if has_inuse and has_inuse[-1].strip().isdigit() and int(has_inuse[-1].strip()) > 0:
            forced_raw = _run_shell_cmd(
                chan,
                "mysql -NBe \"SELECT COUNT(*) FROM timeconditions WHERE inuse_state IN (1,2)\" asterisk 2>/dev/null || echo '0'",
                timeout=timeout,
            ).out.strip().splitlines()
            if forced_raw and forced_raw[-1].strip().isdigit():
                forced_count = int(forced_raw[-1].strip())

        # Services
        services = ["asterisk", "httpd", "mariadb", "fail2ban", "php-fpm", "crond"]
        svc_rows = []
        for s in services:
            cmd = "(systemctl is-active {svc} 2>/dev/null || true)".format(svc=s)
            res = _run_shell_cmd(chan, cmd, timeout=timeout).out.strip().splitlines()
            state = res[-1].strip() if res else "unknown"
            if state not in ("active", "inactive", "failed", "unknown"):
                # Some systems return empty; fall back to service
                cmd2 = "service {svc} status >/dev/null 2>&1 && echo active || echo inactive".format(svc=s)
                state = _run_shell_cmd(chan, cmd2, timeout=timeout).out.strip().splitlines()[-1].strip()
            svc_rows.append({"name": s, "state": state})

        # Snapshot file (if tool installed)
        snap_path = "/home/123net/callflows/freepbx_dump.json"
        snap = {"path": snap_path, "exists": False, "size_bytes": None, "mtime_epoch": None, "age_seconds": None}
        stat_out = _run_shell_cmd(chan, "stat -c '%s %Y' {} 2>/dev/null || echo ''".format(snap_path), timeout=timeout).out
        stat_line = (stat_out.strip().splitlines() or [""])[-1].strip()
        if stat_line:
            parts = stat_line.split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                size_b = int(parts[0])
                mtime = int(parts[1])
                snap.update({"exists": True, "size_bytes": size_b, "mtime_epoch": mtime, "age_seconds": int(time.time() - mtime)})

        pct = None
        if total and total > 0:
            pct = int((reg_count / float(total)) * 100)

        return {
            "ok": True,
            "server": host,
            "generated_at_utc": _now_utc_ts(),
            "meta": {
                "hostname": hostname,
                "freepbx_version": freepbx_ver,
                "asterisk_version": ast_ver_line,
            },
            "calls": {"active": active_calls},
            "endpoints": {
                "total": total,
                "registered": reg_count,
                "unregistered": unreg_count,
                "percent_registered": pct,
                "registered_ids": registered_endpoints,
            },
            "time_conditions": {"total": tc_total, "forced": forced_count, "auto": max(0, tc_total - forced_count)},
            "services": svc_rows,
            "snapshot": snap,
        }
    finally:
        try:
            client.close()
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Collect remote FreePBX diagnostics over SSH (JSON output).")
    p.add_argument("--server", required=True, help="Target FreePBX host")
    p.add_argument("--user", default=os.environ.get("FREEPBX_USER", "123net"))
    p.add_argument("--password", default=os.environ.get("FREEPBX_PASSWORD", ""))
    p.add_argument("--root-password", default=os.environ.get("FREEPBX_ROOT_PASSWORD", ""))
    p.add_argument("--timeout", default="15", help="SSH/command timeout seconds (default: 15)")
    ns = p.parse_args(argv)

    try:
        timeout = float(ns.timeout)
    except Exception:
        timeout = 15.0

    try:
        # Quick DNS sanity (gives a faster/clearer error than Paramiko sometimes)
        socket.getaddrinfo(ns.server, 22)

        payload = collect_one(
            host=ns.server,
            username=ns.user,
            password=ns.password,
            root_password=ns.root_password,
            timeout=timeout,
        )
        sys.stdout.write(json.dumps(payload, sort_keys=True))
        sys.stdout.write("\n")
        return 0
    except Exception as e:
        err = {"ok": False, "server": ns.server, "error": "{}: {}".format(type(e).__name__, str(e))}
        sys.stdout.write(json.dumps(err, sort_keys=True))
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
