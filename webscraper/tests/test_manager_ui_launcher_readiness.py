from __future__ import annotations

import os
import socket
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
        try:
            self.request.recv(128)
        except Exception:
            pass


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


def test_readiness_succeeds_on_open_port_fallback(tcp_server):
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


def test_readiness_succeeds_with_stdout_marker(tmp_path):
    log_path = tmp_path / "frontend.log"
    log_path.write_text("[next] Ready in 3.2s\n", encoding="utf-8")

    reason = dev_runtime.wait_for_dev_server_ready(
        pid=os.getpid(),
        host="127.0.0.1",
        port=65000,
        timeout_s=3,
        http_paths=["/"],
        log_path=log_path,
        allow_open_port_fallback=False,
        process_stable_s=0.1,
        success_markers=["Ready in", "Local: http://localhost:3004"],
    )
    assert "stdout marker" in reason


def test_run_all_returns_success_when_ui_alive_and_port_open(monkeypatch):
    monkeypatch.setattr(run_all_web_apps, "run_checked", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "ensure_manager_ui_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "stop_all_known_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "maybe_open_browser", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_all_web_apps, "load_services", lambda *args, **kwargs: {"manager_ui_frontend": {"pid": 1234}})
    monkeypatch.setattr(run_all_web_apps, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(run_all_web_apps, "is_port_open", lambda host, port: port == 3004)

    class _Result:
        returncode = 1

    monkeypatch.setattr(run_all_web_apps.subprocess, "run", lambda *args, **kwargs: _Result())
    monkeypatch.setattr(sys, "argv", ["run_all_web_apps.py", "--no-bootstrap"])

    assert run_all_web_apps.main() == 0


def test_readiness_timeout_when_process_dies(monkeypatch):
    monkeypatch.setattr(dev_runtime, "is_pid_alive", lambda pid: False)
    with pytest.raises(dev_runtime.LauncherError, match="died"):
        dev_runtime.wait_for_dev_server_ready(
            pid=999,
            host="127.0.0.1",
            port=3004,
            timeout_s=2,
            http_paths=["/"],
            log_path=None,
        )


def test_readiness_timeout_when_port_never_opens(monkeypatch):
    monkeypatch.setattr(dev_runtime, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(dev_runtime, "is_port_open", lambda host, port, timeout=0.5: False)

    with pytest.raises(dev_runtime.LauncherError, match="readiness failed"):
        dev_runtime.wait_for_dev_server_ready(
            pid=999,
            host="127.0.0.1",
            port=3004,
            timeout_s=1,
            http_paths=["/"],
            log_path=None,
            allow_open_port_fallback=False,
        )
