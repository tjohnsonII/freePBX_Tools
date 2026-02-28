from __future__ import annotations

from pathlib import Path
from typing import Any

import psutil

SAFE_PROCESS_NAMES = {"node", "node.exe", "python", "python.exe", "py", "py.exe", "uvicorn"}
SAFE_CMDLINE_MARKERS = ("next dev", "ticket-ui", "uvicorn", "ticket_api", "webscraper_manager")


def find_listening_pids(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return pids

    for conn in conns:
        if conn.status != psutil.CONN_LISTEN:
            continue
        laddr = conn.laddr
        if not laddr:
            continue
        try:
            local_port = int(getattr(laddr, "port", laddr[1]))
        except Exception:
            continue
        if local_port != int(port):
            continue
        if conn.pid:
            pids.add(int(conn.pid))
    return pids


def describe_process(pid: int) -> dict[str, Any]:
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        exe = proc.exe()
        cmdline = proc.cmdline()
        return {
            "name": name,
            "exe": exe,
            "cmdline": cmdline,
            "cmdline_text": " ".join(cmdline),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {
            "name": "<unknown>",
            "exe": "",
            "cmdline": [],
            "cmdline_text": "",
        }


def should_kill(pid: int, scope: str, repo_root: Path) -> bool:
    normalized_scope = str(scope or "repo").strip().lower()
    if normalized_scope == "force":
        return True

    meta = describe_process(pid)
    name = str(meta.get("name") or "").strip().lower()
    cmdline_text = str(meta.get("cmdline_text") or "").strip().lower()
    exe = str(meta.get("exe") or "").strip().lower()
    repo_str = str(repo_root).replace("\\", "/").lower()

    if normalized_scope == "repo":
        haystack = " ".join(part for part in (cmdline_text, exe) if part)
        return repo_str in haystack.replace("\\", "/")

    if normalized_scope == "safe":
        name_ok = name in SAFE_PROCESS_NAMES
        marker_ok = any(marker in cmdline_text for marker in SAFE_CMDLINE_MARKERS)
        return bool(name_ok and marker_ok)

    return False


def kill_process_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return

    children = parent.children(recursive=True)
    for child in reversed(children):
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    _, alive_children = psutil.wait_procs(children, timeout=3)
    for child in alive_children:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    try:
        parent.terminate()
        parent.wait(timeout=3)
    except psutil.TimeoutExpired:
        parent.kill()
        parent.wait(timeout=3)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return
