from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from websocket import create_connection


class ChromeCDPError(RuntimeError):
    pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def launch_chrome_with_debug(
    *,
    chrome_path: Path,
    profile_dir_name: str | None,
    user_data_dir: str | None,
    port: int,
    initial_url: str,
) -> subprocess.Popen:
    command = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins=http://127.0.0.1:{port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if user_data_dir:
        command.append(f"--user-data-dir={user_data_dir}")
    if profile_dir_name:
        command.append(f"--profile-directory={profile_dir_name}")
    command.append(initial_url)
    return subprocess.Popen(command)


def get_ws_url(port: int, timeout_seconds: float = 8.0) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            response = requests.get(endpoint, timeout=0.8)
            response.raise_for_status()
            payload = response.json()
            ws_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
            if ws_url:
                return ws_url
            last_error = f"Endpoint returned no webSocketDebuggerUrl: {payload}"
        except Exception as exc:  # pragma: no cover - timing/runtime dependent
            last_error = str(exc)
        time.sleep(0.2)
    raise ChromeCDPError(f"Could not connect to Chrome CDP at {endpoint}. {last_error or ''}".strip())


def cdp_call(ws: Any, method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None) -> Any:
    call_id = int(getattr(ws, "_cdp_call_id", 0)) + 1
    setattr(ws, "_cdp_call_id", call_id)
    payload: dict[str, Any] = {"id": call_id, "method": method, "params": params or {}}
    if session_id:
        payload["sessionId"] = session_id
    ws.send(json.dumps(payload))

    while True:
        raw_message = ws.recv()
        message = json.loads(raw_message)
        if message.get("id") != call_id:
            continue
        if "error" in message:
            raise ChromeCDPError(f"CDP {method} failed: {message['error']}")
        return message.get("result", {})


def connect_browser_ws(port: int):
    ws_url = get_ws_url(port)
    try:
        return create_connection(ws_url, timeout=5)
    except Exception as exc:  # pragma: no cover - runtime dependent
        raise ChromeCDPError(f"Could not open Chrome CDP websocket {ws_url}: {exc}") from exc


def _open_target_session(ws: Any) -> str:
    cached = getattr(ws, "_cdp_default_session", None)
    if isinstance(cached, str) and cached:
        return cached
    target_id = None
    target_info = cdp_call(ws, "Target.getTargets", {})
    target_infos = target_info.get("targetInfos") if isinstance(target_info, dict) else []
    if isinstance(target_infos, list):
        secure_targets = []
        normal_targets = []
        for row in target_infos:
            if not isinstance(row, dict):
                continue
            if str(row.get("type") or "") != "page":
                continue
            row_url = str(row.get("url") or "").lower()
            row_id = row.get("targetId")
            if not row_id:
                continue
            if "secure.123.net" in row_url:
                secure_targets.append(str(row_id))
            elif row_url and row_url != "about:blank":
                normal_targets.append(str(row_id))
        if secure_targets:
            target_id = secure_targets[0]
        elif normal_targets:
            target_id = normal_targets[0]

    if not target_id:
        target = cdp_call(ws, "Target.createTarget", {"url": "about:blank"})
        target_id = target.get("targetId")
    if not target_id:
        raise ChromeCDPError("CDP Target.createTarget did not return targetId.")
    attached = cdp_call(ws, "Target.attachToTarget", {"targetId": target_id, "flatten": True})
    session_id = attached.get("sessionId")
    if not session_id:
        raise ChromeCDPError("CDP Target.attachToTarget did not return sessionId.")
    session_value = str(session_id)
    setattr(ws, "_cdp_default_session", session_value)
    return session_value


def get_all_cookies(ws: Any) -> list[dict[str, Any]]:
    session_id = _open_target_session(ws)
    result = cdp_call(ws, "Network.getAllCookies", {}, session_id=session_id)
    cookies = result.get("cookies") or []
    if isinstance(cookies, list):
        return cookies
    return []


def set_cookie(ws: Any, cookie_dict: dict[str, Any]) -> None:
    session_id = _open_target_session(ws)
    payload = dict(cookie_dict)
    result = cdp_call(ws, "Network.setCookie", payload, session_id=session_id)
    if not result.get("success", False):
        raise ChromeCDPError(f"CDP rejected cookie {payload.get('name')} for {payload.get('domain')}")


def navigate(ws: Any, url: str) -> None:
    session_id = _open_target_session(ws)
    cdp_call(ws, "Page.enable", {}, session_id=session_id)
    cdp_call(ws, "Page.navigate", {"url": url}, session_id=session_id)
