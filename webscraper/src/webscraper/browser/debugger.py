from __future__ import annotations

import json
import urllib.request
from typing import Any


def probe_edge_debugger(host: str, port: int, timeout: float) -> dict[str, Any]:
    url = f"http://{host}:{port}/json/version"
    result: dict[str, Any] = {"ok": False, "url": url, "status": None, "error": None, "body": None}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            result["status"] = resp.status
            payload = resp.read().decode("utf-8", errors="replace")
            result["body"] = payload
            result["ok"] = resp.status == 200
    except Exception as exc:
        result["error"] = str(exc)
    return result


def edge_debug_targets(host: str, port: int, timeout: float) -> list[dict[str, Any]]:
    try:
        url = f"http://{host}:{port}/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, list):
            return payload
    except Exception:
        return []
    return []
