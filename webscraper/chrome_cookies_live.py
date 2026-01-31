#!/usr/bin/env python3
"""Export authenticated cookies from a live Chrome debugging session."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

import websocket

DEFAULT_DEBUG_URL = "http://127.0.0.1:9222/json"
DEFAULT_OUT = "webscraper/output/live_cookies.json"
TARGET_HOST_SNIPPET = "secure.123.net"
TARGET_DOMAIN_SUFFIX = "123.net"


def fetch_debug_targets(debug_url: str) -> List[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(debug_url, timeout=5) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to reach Chrome DevTools endpoint at {debug_url}: {exc}"
        ) from exc

    try:
        targets = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Chrome DevTools endpoint returned invalid JSON.") from exc

    if not isinstance(targets, list):
        raise RuntimeError("Chrome DevTools endpoint did not return a list of targets.")

    return targets


def find_target(targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    for target in targets:
        url = target.get("url", "")
        if TARGET_HOST_SNIPPET in url:
            return target
    raise RuntimeError(
        f"No open Chrome tab found with URL containing '{TARGET_HOST_SNIPPET}'."
    )


def request_cookies(ws_url: str) -> List[Dict[str, Any]]:
    ws = websocket.create_connection(ws_url, timeout=10)
    message_id = 0

    def send_command(method: str, params: Dict[str, Any] | None = None) -> int:
        nonlocal message_id
        message_id += 1
        payload: Dict[str, Any] = {"id": message_id, "method": method}
        if params:
            payload["params"] = params
        ws.send(json.dumps(payload))
        return message_id

    def wait_for_response(request_id: int, timeout: int = 10) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(max(deadline - time.time(), 0.1))
            raw = ws.recv()
            if not raw:
                continue
            message = json.loads(raw)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(
                    f"Chrome DevTools error: {message['error'].get('message', 'Unknown error')}"
                )
            return message.get("result", {})
        raise TimeoutError("Timed out waiting for Chrome DevTools response.")

    try:
        enable_id = send_command("Network.enable")
        wait_for_response(enable_id)
        cookies_id = send_command("Network.getAllCookies")
        result = wait_for_response(cookies_id)
    finally:
        ws.close()

    cookies = result.get("cookies")
    if not isinstance(cookies, list):
        raise RuntimeError("Chrome DevTools did not return a cookie list.")

    return cookies


def filter_cookies(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lstrip(".")
        if domain.endswith(TARGET_DOMAIN_SUFFIX):
            filtered.append(cookie)
    return filtered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export authenticated cookies from a live Chrome debugging session."
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Output JSON file (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--debug-url",
        default=DEFAULT_DEBUG_URL,
        help=f"Chrome DevTools JSON endpoint (default: {DEFAULT_DEBUG_URL})",
    )
    return parser.parse_args()


def ensure_output_path(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def main() -> int:
    args = parse_args()

    try:
        targets = fetch_debug_targets(args.debug_url)
        target = find_target(targets)
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("Selected Chrome target is missing webSocketDebuggerUrl.")
        cookies = request_cookies(ws_url)
        filtered = filter_cookies(cookies)
        ensure_output_path(args.out)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(filtered, handle, indent=2)
        print(f"Saved {len(filtered)} cookies to {args.out}")
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
