#!/usr/bin/env python3
"""Remote SSH command executor and log tailer for FreePBX Tools.

Modes:
  --mode run   SSH in, (optionally) become root, run --command, emit JSON to stdout, exit.
  --mode tail  SSH in, become root, run 'tail -f --log-path', stream lines to stdout.

Credentials via env: FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from typing import List, Optional

try:
    import paramiko
except ImportError:
    import subprocess as _sp
    _sp.check_call([sys.executable, "-m", "pip", "install", "--quiet", "paramiko"])
    import paramiko  # type: ignore

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROMPT_ONLY_RE = re.compile(r"^\s*\[[^\]]+\][#$]\s*$")
_PROMPT_PREFIX_RE = re.compile(r"^\s*(\[[^\]]+\][#$]|[^\n]*[#$])\s+")
_PROMPTS = ("__FREEPBXTOOLS_USER__$ ", "__FREEPBXTOOLS_ROOT__# ")
_MAX_BUF = 600_000


def _normalize(s: str) -> str:
    s = _ANSI_RE.sub("", s).replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in s if ch in ("\n", "\t") or (32 <= ord(ch) != 127))


def _read_until(chan: "paramiko.Channel", predicate, timeout: float, stage: str = "") -> str:
    buf, start = "", time.time()
    while True:
        if chan.recv_ready():
            buf += chan.recv(65535).decode("utf-8", errors="replace")
            if len(buf) > _MAX_BUF:
                buf = buf[-_MAX_BUF:]
            if predicate(buf):
                return buf
        else:
            time.sleep(0.05)
        if time.time() - start > timeout:
            raise TimeoutError(
                f"Timed out (stage={stage})\n--- last output ---\n{_normalize(buf[-3000:])}"
            )


def _send(chan: "paramiko.Channel", s: str) -> None:
    chan.send(s.encode("utf-8", errors="replace"))


def _sync(chan: "paramiko.Channel", timeout: float) -> None:
    tok = uuid.uuid4().hex[:12]
    marker = f"__SSH_EXEC_SYNC__:{tok}"
    _send(chan, f"echo {marker}\n")
    _read_until(chan, lambda b: marker in _normalize(b), timeout=timeout, stage="sync")


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _run_cmd(chan: "paramiko.Channel", cmd: str, timeout: float) -> tuple[int, str]:
    m_key, tok = "__SSH_EXEC_MARK__", uuid.uuid4().hex[:12]
    m_re = re.compile(rf"{re.escape(m_key)}:{re.escape(tok)}:(?P<rc>\d+)")
    _send(chan, f"sh -c {_sh_quote(cmd)}\necho {m_key}:{tok}:$?\n")
    raw = _read_until(chan, lambda b: m_re.search(_normalize(b)) is not None, timeout=timeout, stage="cmd")
    raw_n = _normalize(raw)
    m = None
    for mm in m_re.finditer(raw_n):
        m = mm
    rc = int(m.group("rc")) if m else 1
    sh_wrapped = f"sh -c {_sh_quote(cmd)}"
    cleaned = []
    for line in raw_n.splitlines():
        if m_key in line:
            continue
        for p in _PROMPTS:
            if line.startswith(p):
                line = line[len(p):]
                break
        if _PROMPT_ONLY_RE.match(line.strip()):
            continue
        line = _PROMPT_PREFIX_RE.sub("", line)
        if line.strip() in (cmd.strip(), sh_wrapped.strip()):
            continue
        cleaned.append(line)
    return rc, "\n".join(cleaned).strip("\n")


def _connect(host: str, username: str, password: str, timeout: float) -> "paramiko.SSHClient":
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    use_pw = bool(password)
    c.connect(
        host, username=username,
        password=password if use_pw else None,
        look_for_keys=not use_pw, allow_agent=not use_pw,
        timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
    )
    return c


def _become_root(chan: "paramiko.Channel", root_password: str, timeout: float) -> None:
    _send(chan, "su - root\n")
    out = _read_until(
        chan,
        lambda b: "password" in b.lower() or "authentication" in b.lower()
                  or "sorry" in b.lower() or re.search(r"\n[^\n]*#\s*$", b) is not None,
        timeout=timeout, stage="su",
    )
    if "password" in out.lower():
        if not root_password:
            raise RuntimeError("Root password required for su - root")
        _send(chan, root_password + "\n")
    _sync(chan, timeout=timeout)
    rc, _ = _run_cmd(chan, 'test "$(id -u)" = "0"', timeout=timeout)
    if rc != 0:
        raise RuntimeError("Failed to become root")
    _send(chan, "export PS1='__FREEPBXTOOLS_ROOT__# '; export PROMPT_COMMAND='';\n")
    _sync(chan, timeout=timeout)


def mode_run(ns: argparse.Namespace) -> int:
    password = os.environ.get("FREEPBX_PASSWORD", ns.password)
    root_pw = os.environ.get("FREEPBX_ROOT_PASSWORD", ns.root_password or password)
    t = ns.timeout
    boot = max(t, 45.0)
    result: dict
    try:
        client = _connect(ns.server, ns.user, password, t)
        try:
            chan = client.invoke_shell(width=220, height=60)
            chan.settimeout(t)
            _send(chan, "export PS1='__FREEPBXTOOLS_USER__$ '; export PROMPT_COMMAND='';\n")
            _sync(chan, boot)
            if ns.as_root:
                _become_root(chan, root_pw, boot)
            rc, out = _run_cmd(chan, ns.command, t)
            result = {"ok": rc == 0, "rc": rc, "output": out, "command": ns.command, "server": ns.server}
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as e:
        result = {"ok": False, "rc": 1, "error": f"{type(e).__name__}: {e}", "server": ns.server}
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    return 0


def mode_tail(ns: argparse.Namespace) -> int:
    password = os.environ.get("FREEPBX_PASSWORD", ns.password)
    root_pw = os.environ.get("FREEPBX_ROOT_PASSWORD", ns.root_password or password)
    t = ns.timeout
    boot = max(t, 45.0)
    try:
        client = _connect(ns.server, ns.user, password, t)
        try:
            chan = client.invoke_shell(width=300, height=60)
            chan.settimeout(None)
            _send(chan, "export PS1='__FREEPBXTOOLS_USER__$ '; export PROMPT_COMMAND='';\n")
            _sync(chan, boot)
            _become_root(chan, root_pw, boot)

            if ns.filter:
                cmd = f"tail -n 0 -f {_sh_quote(ns.log_path)} | grep --line-buffered {_sh_quote(ns.filter)}"
            else:
                cmd = f"tail -n 0 -f {_sh_quote(ns.log_path)}"
            _send(chan, cmd + "\n")
            time.sleep(0.8)  # let tail start and skip the echoed command line

            buf = ""
            while True:
                if chan.recv_ready():
                    buf += chan.recv(65535).decode("utf-8", errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        clean = _normalize(line).rstrip("\n")
                        if not clean:
                            continue
                        # Skip echoed command and prompt-only lines
                        if ns.log_path in clean and "tail" in clean.lower():
                            continue
                        if _PROMPT_ONLY_RE.match(clean.strip()):
                            continue
                        sys.stdout.write(clean + "\n")
                        sys.stdout.flush()
                else:
                    time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as e:
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Remote SSH executor / log tailer")
    p.add_argument("--mode", choices=["run", "tail"], required=True)
    p.add_argument("--server", required=True)
    p.add_argument("--user", default=os.environ.get("FREEPBX_USER", "123net"))
    p.add_argument("--password", default="")
    p.add_argument("--root-password", dest="root_password", default="")
    p.add_argument("--timeout", type=float, default=30.0)
    # run mode
    p.add_argument("--command", default="")
    p.add_argument("--as-root", dest="as_root", action="store_true", default=True)
    p.add_argument("--no-root", dest="as_root", action="store_false")
    # tail mode
    p.add_argument("--log-path", dest="log_path", default="/var/log/asterisk/full")
    p.add_argument("--filter", default="")
    ns = p.parse_args(argv)

    if ns.mode == "run":
        if not ns.command:
            sys.stderr.write("--command is required for run mode\n")
            return 2
        return mode_run(ns)
    return mode_tail(ns)


if __name__ == "__main__":
    raise SystemExit(main())
