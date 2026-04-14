#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""remote_run_tool.py

SSH into a FreePBX host and run one installed freepbx-* tool.
Streams the tool output to stdout line by line so the deploy-backend job
machinery can forward it to browser WebSocket clients.

For freepbx-dump, the resulting dump file is also read back and emitted on a
single line with a known marker so the UI can parse the JSON:

    __FREEPBX_DUMP_JSON__:<compact-json>

Usage:
    python scripts/remote_run_tool.py \\
        --server 1.2.3.4 \\
        --user 123net \\
        --password <pass> \\
        --root-password <root-pass> \\
        --command freepbx-dump \\
        --timeout 120
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from typing import List

try:
    import paramiko
except Exception as _e:  # pragma: no cover
    print("ERROR: paramiko is required: {}".format(_e), flush=True)
    sys.exit(2)

# ── ANSI / prompt normalisation ────────────────────────────────────────────
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROMPT_ONLY_RE = re.compile(r"^\s*\[[^\]]+\][#$]\s*$")
_PROMPT_PREFIX_RE = re.compile(r"^\s*(\[[^\]]+\][#$]|[^\n]*[#$])\s+")
_PROMPTS = ("__FPBXRUN_USER__$ ", "__FPBXRUN_ROOT__# ")
_MAX_BUF = 600_000

# Marker emitted before the dump JSON line so the UI can find it reliably
DUMP_JSON_MARKER = "__FREEPBX_DUMP_JSON__"
DUMP_FILE_PATH = "/home/123net/callflows/freepbx_dump.json"

# Commands that generate a JSON dump file (read back after execution)
_DUMP_COMMANDS = frozenset({"freepbx-dump"})

# Allow-list: only these tool names can be executed remotely
ALLOWED_COMMANDS = frozenset({
    "freepbx-dump",
    "freepbx-tc-status",
    "freepbx-module-status",
    "freepbx-module-analyzer",
    "freepbx-paging-fax-analyzer",
    "freepbx-comprehensive-analyzer",
    "freepbx-ascii-callflow",
    "freepbx-version-check",
    "asterisk-full-diagnostic.sh",
})


# ── Low-level SSH helpers (mirrors remote_freepbx_diagnostics.py) ──────────

def _strip_ansi(s: str) -> str:
    return _ANSI_CSI_RE.sub("", s)


def _normalize(s: str) -> str:
    """Strip ANSI codes, normalise line endings, drop control chars."""
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
            msg = "Timed out waiting for remote output"
            if stage:
                msg += " (stage={})".format(stage)
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


def _run_cmd(chan: "paramiko.Channel", cmd: str, timeout: float):
    """Run *cmd* inside the current shell; return (rc: int, output: str)."""
    marker = "__FPBXRUN_RC__"
    token = uuid.uuid4().hex[:12]
    marker_re = re.compile(r"{}:{}:(?P<rc>\d+)".format(re.escape(marker), re.escape(token)))

    sh_cmd = "sh -c {}".format(_sh_single_quote(cmd))
    _send(chan, "{}\necho {}:{}:$?\n".format(sh_cmd, marker, token))

    def pred(buf: str) -> bool:
        return marker_re.search(_normalize(buf)) is not None

    raw = _read_until(chan, pred, timeout=timeout, stage="cmd")
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
        description="Run a freepbx-* tool on a remote FreePBX host via SSH."
    )
    parser.add_argument("--server", required=True, help="Target host IP / hostname")
    parser.add_argument("--user", default="123net", help="SSH username")
    parser.add_argument("--password", default="", help="SSH password")
    parser.add_argument("--root-password", default="", help="Root password for su -")
    parser.add_argument("--command", required=True, help="freepbx-* tool name to run")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="Per-command timeout in seconds (default: 120)")
    args = parser.parse_args()

    # Allow env-var overrides (consistent with deploy scripts)
    password = args.password or os.environ.get("FREEPBX_PASSWORD", "")
    root_password = (
        args.root_password
        or os.environ.get("FREEPBX_ROOT_PASSWORD", "")
        or password
    )
    cmd = args.command.strip()

    if cmd not in ALLOWED_COMMANDS:
        print("ERROR: command not in allowed list: {!r}".format(cmd), flush=True)
        print("Allowed commands: {}".format(sorted(ALLOWED_COMMANDS)), flush=True)
        return 1

    print("[remote_run] Connecting to {} as {}...".format(args.server, args.user), flush=True)

    connect_timeout = min(args.timeout, 30.0)
    try:
        client = _connect(args.server, args.user, password, timeout=connect_timeout)
    except Exception as e:
        print("ERROR: SSH connect failed: {}".format(e), flush=True)
        return 1

    print("[remote_run] Connected. Starting interactive shell...", flush=True)
    chan = client.invoke_shell(width=200, height=60)
    chan.settimeout(args.timeout)

    try:
        boot_timeout = max(args.timeout, 45.0)

        # Set deterministic user prompt then sync
        _send(chan, "export PS1='__FPBXRUN_USER__$ '; export PROMPT_COMMAND='';\n")
        _sync(chan, timeout=boot_timeout)

        print("[remote_run] Escalating to root...", flush=True)
        _become_root(chan, root_password=root_password, timeout=boot_timeout)

        print("[remote_run] Root shell ready. Running: {}".format(cmd), flush=True)
        print("=" * 60, flush=True)

        rc, output = _run_cmd(chan, cmd, timeout=args.timeout)

        for line in output.splitlines():
            print(line, flush=True)

        print("=" * 60, flush=True)
        print("[remote_run] Command exited with code: {}".format(rc), flush=True)

        # For dump commands: read back the generated JSON file and emit it with
        # a known marker so the browser UI can parse it out of the log stream.
        if cmd in _DUMP_COMMANDS:
            print("[remote_run] Reading dump file {}...".format(DUMP_FILE_PATH), flush=True)
            _, dump_raw = _run_cmd(chan, "cat {}".format(DUMP_FILE_PATH), timeout=args.timeout)
            dump_raw = dump_raw.strip()
            if dump_raw:
                try:
                    parsed = json.loads(dump_raw)
                    compact = json.dumps(parsed, separators=(",", ":"))
                except Exception:
                    compact = dump_raw  # emit as-is even if not valid JSON
                print("{}:{}".format(DUMP_JSON_MARKER, compact), flush=True)
            else:
                print("[remote_run] Dump file not found or empty.", flush=True)

        return rc

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