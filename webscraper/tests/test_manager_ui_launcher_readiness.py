from __future__ import annotations

import json
import os
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import dev_runtime  # type: ignore  # noqa: E402
import run_all_web_apps  # type: ignore  # noqa: E402


class _DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib signature
        if self.path == "/":
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"not-ready")
            return
        if self.path == "/dashboard":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


class _OpenPortHandler(socketserver.BaseRequestHandler):
    def handle(self):
        _ = self.request.recv(128)


@pytest.fixture()
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture()
def tcp_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), _OpenPortHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_readiness_succeeds_on_dashboard_when_root_fails(http_server):
    reason = dev_runtime.wait_for_dev_server_ready(
        pid=os.getpid(),
        host="127.0.0.1",
        port=http_server,
        timeout_s=10,
        http_paths=["/", "/dashboard", "/api/health"],
        log_path=None,
        allow_open_port_fallback=False,
        process_stable_s=0.1,
    )
    assert "dashboard" in reason
    assert "HTTP 200" in reason


def test_readiness_requires_opt_in_for_open_port_fallback(tcp_server):
    with pytest.raises(dev_runtime.LauncherError, match="readiness failed"):
        dev_runtime.wait_for_dev_server_ready(
            pid=os.getpid(),
            host="127.0.0.1",
            port=tcp_server,
            timeout_s=2,
            http_paths=["/"],
            log_path=None,
            allow_open_port_fallback=False,
            process_stable_s=0.1,
        )


def test_readiness_succeeds_with_open_port_fallback_when_enabled(tcp_server):
    reason = dev_runtime.wait_for_dev_server_ready(
        pid=os.getpid(),
        host="127.0.0.1",
        port=tcp_server,
        timeout_s=8,
        http_paths=["/"],
        log_path=None,
        allow_open_port_fallback=True,
        open_port_fallback_s=1,
        process_stable_s=0.1,
    )
    assert "open port fallback" in reason


def test_launch_browser_mode_none_is_predictable():
    details = dev_runtime.launch_browser_mode(mode="none", url="http://127.0.0.1:3004/dashboard")
    assert details.mode == "none"
    assert details.launched is False
    assert details.command == []


def test_run_all_dry_run_writes_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all_web_apps, "run_checked", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "ensure_manager_ui_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "stop_all_known_services", lambda *args, **kwargs: None)

    class _Browser:
        mode = "none"
        browser_path = None
        user_data_dir = None
        profile_directory = None
        url = "http://127.0.0.1:3004/dashboard"
        command = []
        launched = False
        reason = "disabled"

    monkeypatch.setattr(run_all_web_apps, "launch_browser_mode", lambda **kwargs: _Browser())
    monkeypatch.setattr(run_all_web_apps, "_read_runtime_services", lambda _root: {})
    status_file = tmp_path / "summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_all_web_apps.py", "--dry-run", "--status-file", str(status_file)],
    )
    assert run_all_web_apps.main() == 0
    assert status_file.exists()
    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert "timestamp" in payload
    assert payload["args"]["browser"] == "none"
    assert "services_attempted" in payload


def test_run_all_rejects_deprecated_open_browser_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_all_web_apps.py", "--open-browser"])
    assert run_all_web_apps.main() == 1
