"""Background heartbeat — reports client status to INGEST_SERVER_URL every 30 s."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("webscraper.heartbeat")

_CLIENT_ID_PATH = Path(__file__).resolve().parents[2] / "var" / "client_id.txt"

_VPN_ADAPTER_KEYWORDS = (
    "tap-windows", "openvpn", "cisco anyconnect",
    "globalprotect", "wireguard", "nordvpn", "expressvpn",
)


def _get_client_id() -> str:
    if _CLIENT_ID_PATH.exists():
        cid = _CLIENT_ID_PATH.read_text().strip()
        if cid:
            return cid
    _CLIENT_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    hostname = socket.gethostname()
    cid = f"{hostname}-{uuid.uuid4().hex[:8]}"
    _CLIENT_ID_PATH.write_text(cid)
    return cid


def detect_vpn() -> tuple[bool, str | None]:
    """Return (connected, ip_or_None). Works on Windows; falls back to psutil on Unix."""
    import re
    try:
        result = subprocess.run(
            ["ipconfig", "/all"], capture_output=True, text=True, timeout=5
        )
        in_vpn_block = False
        for line in result.stdout.splitlines():
            if line and not line.startswith(" ") and not line.startswith("\t"):
                in_vpn_block = False
            low = line.lower()
            if "description" in low and any(kw in low for kw in _VPN_ADAPTER_KEYWORDS):
                in_vpn_block = True
            if in_vpn_block and "ipv4 address" in low:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    ip = m.group(1)
                    if not ip.startswith("169.254"):
                        return True, ip
    except Exception:
        pass
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            if any(kw in name.lower() for kw in _VPN_ADAPTER_KEYWORDS):
                for addr in addrs:
                    if addr.family == 2 and not addr.address.startswith("169.254"):
                        return True, addr.address
    except Exception:
        pass
    return False, None


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class HeartbeatThread:
    """Thread-safe heartbeat that fires every `interval` seconds."""

    def __init__(self, interval: int = 30) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "client_id": _get_client_id(),
            "status": "idle",
            "job_id": None,
            "current_handle": None,
            "handles_done": None,
            "handles_total": None,
        }
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="heartbeat"
        )
        self._thread.start()
        _LOG.info("heartbeat started client_id=%s interval=%ds", self._state["client_id"], self._interval)

    def stop(self) -> None:
        self._stop.set()
        _LOG.info("heartbeat stopped")

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            self._state.update(kwargs)

    def _send(self) -> None:
        from webscraper.ticket_api import db_client
        with self._lock:
            state = dict(self._state)
        vpn_connected, vpn_ip = detect_vpn()
        server = os.getenv("INGEST_SERVER_URL", "").rstrip("/")
        try:
            db_client.upsert_client_heartbeat(
                db_path="",
                client_id=state["client_id"],
                status=state.get("status", "idle"),
                vpn_connected=vpn_connected,
                vpn_ip=vpn_ip,
                job_id=state.get("job_id"),
                current_handle=state.get("current_handle"),
                handles_done=state.get("handles_done"),
                handles_total=state.get("handles_total"),
                ts_utc=_iso_now(),
            )
            _LOG.info(
                "heartbeat POST %s/api/ingest/heartbeat -> 200 "
                "client=%s status=%s vpn=%s ip=%s",
                server,
                state["client_id"],
                state.get("status"),
                vpn_connected,
                vpn_ip,
            )
        except Exception as exc:
            _LOG.warning("heartbeat POST %s/api/ingest/heartbeat failed: %s", server, exc)

    def _loop(self) -> None:
        self._send()
        while not self._stop.wait(self._interval):
            self._send()
