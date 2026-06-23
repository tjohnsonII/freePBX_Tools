#!/usr/bin/env python3
"""Scrape Manager GUI — desktop app to start, resume, monitor, and stop webscraper jobs.

Requirements:
    pip install customtkinter requests

Run:
    python scrape_gui.py
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import requests
import customtkinter as ctk

# Give this process a unique App User Model ID so Windows taskbar pins use the
# shortcut icon (123net.ico) instead of the generic pythonw.exe icon.
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("123net.ScrapeManager.1")

# ── Config ────────────────────────────────────────────────────────────────────

_PORT = os.getenv("WEBSCRAPER_PORT", "8789")
API_BASE = f"http://localhost:{_PORT}"

POLL_FAST_MS = 2_000   # while a job is running
POLL_SLOW_MS = 6_000   # while idle

_TERMINAL = {"completed", "failed", "cancelled", "done", "error"}
_ACTIVE   = {"running", "queued"}

# ── Scraper tab config ────────────────────────────────────────────────────────

_SCRAPERS: list[dict] = [
    {
        "key":          "vpbx",
        "label":        "VPBX",
        "api_start":    "/api/vpbx/refresh",
        "event_prefix": "vpbx:",
        "login_hint":   "Chrome will open — log in to secure.123.net (vpbx.cgi) when prompted.",
    },
    {
        "key":          "phone_configs",
        "label":        "Phone Configs",
        "api_start":    "/api/vpbx/device-configs/refresh",
        "api_state":    "/api/vpbx/device-configs/state",
        "event_prefix": "vpbx_device_configs:",
        "login_hint":   "Chrome will open — log in to secure.123.net when prompted.",
    },
    {
        "key":          "site_config",
        "label":        "Site Config",
        "api_start":    "/api/vpbx/site-configs/refresh",
        "api_state":    "/api/vpbx/site-configs/state",
        "event_prefix": "vpbx_site_configs:",
        "login_hint":   "Chrome will open — log in to secure.123.net when prompted.",
    },
    {
        "key":          "noc_queue",
        "label":        "NOC Queue",
        "api_start":    "/api/noc-queue/refresh",
        "event_prefix": "noc_queue:",
        "login_hint":   "Chrome will open — log in to noc-tickets.123.net when prompted.",
    },
    {
        "key":          "orders",
        "label":        "Orders",
        "api_start":    "/api/orders/refresh",
        "event_prefix": "orders_refresh:",
        "login_hint":   "Uses ORDERS_123NET_USERNAME/PASSWORD from .env — no browser needed.",
    },
]

# ── Deploy backend (FreePBX Tools) ────────────────────────────────────────────

_DEPLOY_PORT = os.getenv("DEPLOY_PORT", "8002")
_DEPLOY_HOST = os.getenv("DEPLOY_HOST", "localhost")
_DEPLOY_DIRECT_URL = os.getenv("DEPLOY_API_URL", f"http://{_DEPLOY_HOST}:{_DEPLOY_PORT}")
_DEPLOY_TUNNEL_URL = f"http://localhost:{_DEPLOY_PORT}"
_deploy_active_url: list[str] = [_DEPLOY_DIRECT_URL]   # mutable — updated by auto-connect
DEPLOY_API_BASE = _DEPLOY_DIRECT_URL  # alias

_DEPLOY_ACTIONS = [
    ("deploy",       "Deploy"),
    ("uninstall",    "Uninstall"),
    ("clean_deploy", "Clean Deploy (uninstall + install)"),
    ("connect_only", "Connect-only (test SSH)"),
    ("upload_only",  "Upload-only (no install)"),
    ("bundle",       "Build offline bundle (.zip)"),
]

_REMOTE_RUN_MENU = [
    ("1",  "1 - Refresh DB snapshot"),
    ("2",  "2 - Show inventory + list DIDs"),
    ("3",  "3 - Generate call-flow for selected DID(s)"),
    ("4",  "4 - Generate call-flows for ALL DIDs"),
    ("5",  "5 - Generate call-flows ALL DIDs (skip OPEN label)"),
    ("6",  "6 - Time-Condition status"),
    ("7",  "7 - Module analysis"),
    ("8",  "8 - Paging / overhead / fax analysis"),
    ("9",  "9 - Comprehensive component analysis"),
    ("10", "10 - ASCII art call-flows"),
    ("12", "12 - Full Asterisk diagnostic"),
    ("13", "13 - Automated log analysis"),
    ("14", "14 - Error map & quick reference"),
    ("15", "15 - Network diagnostics"),
    ("16", "16 - Enhanced log analysis (dmesg/journal)"),
    ("17", "17 - CDR/CEL call log analysis"),
    ("18", "18 - Phone/endpoint analysis"),
]
# Label -> key lookup so _on_rrun_start never relies on splitting the label string
_RRUN_LABEL_TO_KEY: dict[str, str] = {lbl: key for key, lbl in _REMOTE_RUN_MENU}


def _deploy_get(path: str, **kw: Any) -> Any:
    r = requests.get(f"{_deploy_active_url[0]}{path}", timeout=15, **kw)
    r.raise_for_status()
    return r.json()


def _deploy_post(path: str, **kw: Any) -> Any:
    r = requests.post(f"{_deploy_active_url[0]}{path}", timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def _deploy_state_color(status: str) -> str:
    return {
        "succeeded": "#2ecc71",
        "running":   "#3498db",
        "queued":    "#f39c12",
        "failed":    "#e74c3c",
        "cancelled": "#95a5a6",
    }.get(status, "#ecf0f1")


# ── VPN detection ─────────────────────────────────────────────────────────────

_VPN_ADAPTER_KEYWORDS = (
    "tap-windows", "openvpn", "cisco anyconnect",
    "globalprotect", "wireguard", "nordvpn", "expressvpn",
)

def detect_vpn() -> tuple[bool, str | None]:
    import re as _re
    try:
        result = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        return False, None

    in_vpn_block = False
    for line in result.stdout.splitlines():
        if line and not line.startswith(" ") and not line.startswith("\t"):
            in_vpn_block = False
        low = line.lower()
        if "description" in low and any(kw in low for kw in _VPN_ADAPTER_KEYWORDS):
            in_vpn_block = True
        if in_vpn_block and "ipv4 address" in low:
            m = _re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            if m:
                ip = m.group(1)
                if not ip.startswith("169.254"):
                    return True, ip
    return False, None


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── API helpers ───────────────────────────────────────────────────────────────

def _get(path: str, **kw: Any) -> Any:
    r = requests.get(f"{API_BASE}{path}", timeout=8, **kw)
    r.raise_for_status()
    return r.json()

def _post(path: str, **kw: Any) -> Any:
    r = requests.post(f"{API_BASE}{path}", timeout=8, **kw)
    r.raise_for_status()
    return r.json()

def _fetch_jobs() -> list[dict]:
    data = _get("/api/jobs")
    items = data if isinstance(data, list) else data.get("items", [])
    return items

def _fetch_job(job_id: str) -> dict:
    return _get(f"/api/jobs/{job_id}")

def _fetch_events(job_id: str, limit: int = 60) -> list[dict]:
    data = _get(f"/api/jobs/{job_id}/events", params={"limit": limit})
    return data.get("events", []) if isinstance(data, dict) else []

def _fetch_state() -> dict:
    return _get("/api/scrape/state")

def _short_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso[11:19]

def _state_color(state: str) -> str:
    return {
        "running":   "#2ecc71",
        "queued":    "#f39c12",
        "completed": "#2ecc71",
        "done":      "#2ecc71",
        "failed":    "#e74c3c",
        "error":     "#e74c3c",
        "cancelled": "#95a5a6",
    }.get(state, "#ecf0f1")

# ── Main Application ──────────────────────────────────────────────────────────

class ScrapeManagerApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()

        self.title("Scrape Manager")
        self.geometry("1060x740")
        self.minsize(860, 580)

        self._project_root = Path(__file__).resolve().parent
        self._server_proc: subprocess.Popen | None = None

        # Load .env into os.environ NOW so getenv() calls during UI build see the values.
        # Also refresh module-level deploy URL constants which were computed at import time.
        _env_file = self._project_root / ".env"
        if _env_file.exists():
            for _raw in _env_file.read_text(encoding="utf-8").splitlines():
                _line = _raw.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        global _DEPLOY_HOST, _DEPLOY_DIRECT_URL
        _DEPLOY_HOST = os.getenv("DEPLOY_HOST", _DEPLOY_HOST)
        _DEPLOY_DIRECT_URL = os.getenv("DEPLOY_API_URL", f"http://{_DEPLOY_HOST}:{_DEPLOY_PORT}")
        _deploy_active_url[0] = _DEPLOY_DIRECT_URL

        # Ticket scraper state
        self._connected = False
        self._closing = False
        self._active_job: dict | None = None
        self._jobs: list[dict] = []
        self._event_ids: set[int] = set()
        self._ui_queue: queue.Queue = queue.Queue()
        self._poll_after_id: str | None = None
        self._vpn_connected = False
        self._vpn_ip: str | None = None
        self._job_paused = False

        # Per-scraper tab state (VPBX / Phone Configs / Site Config / NOC Queue)
        self._scraper: dict[str, dict] = {
            cfg["key"]: {"job_id": None, "running": False, "paused": False, "event_ids": set()}
            for cfg in _SCRAPERS
        }
        self._scraper_w: dict[str, dict] = {}   # widget refs keyed by scraper key

        # Diagnostics / Deploy tab state
        self._deploy_w: dict = {}
        self._rrun_w: dict = {}
        self._sdiag_w: dict = {}
        self._deploy_active_job: dict | None = None
        self._deploy_jobs: list[dict] = []
        self._rrun_active_job: dict | None = None
        self._deploy_backend_ok = False
        self._deploy_backend_proc: subprocess.Popen | None = None
        self._deploy_conn_method: str = ""   # "direct", "tunnel", ""
        self._ssh_tunnel_proc: subprocess.Popen | None = None
        self._ssh_tunnel_alive = False

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Set taskbar + title-bar icon on Windows.
        # ctypes AppUserModelID must be set before the window is shown so the
        # taskbar groups the app under this ID and picks up the .ico resource.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "123net.ScrapeManager.1"
                )
            except Exception:
                pass

        self._build_ui()

        # iconbitmap after the window exists — deferred so Tk has created the HWND.
        _ico = Path(__file__).parent / "assets" / "123net.ico"
        _png = Path(__file__).parent / "assets" / "123net_64.png"
        if _ico.exists():
            try:
                self.iconbitmap(default=str(_ico))
            except Exception:
                pass
        if _png.exists():
            try:
                from PIL import ImageTk
                _img = ImageTk.PhotoImage(file=str(_png))
                self.iconphoto(True, _img)
                self._icon_ref = _img
            except Exception:
                pass
        threading.Thread(target=self._ensure_server, daemon=True).start()
        threading.Thread(target=self._ensure_deploy_backend, daemon=True, name="deploy-backend").start()
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat").start()
        self._log_file_pos = 0
        threading.Thread(target=self._tail_log_loop, daemon=True, name="log-tail").start()
        threading.Thread(target=self._deploy_poll_loop, daemon=True, name="deploy-poll").start()
        self._schedule_poll(delay_ms=3_500)

    # ── Server lifecycle ──────────────────────────────────────────────────────

    def _load_dotenv(self) -> dict[str, str]:
        env_file = self._project_root / ".env"
        result: dict[str, str] = {}
        if not env_file.exists():
            return result
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
        return result

    def _ensure_server(self) -> None:
        try:
            requests.get(f"{API_BASE}/api/health", timeout=2)
            self._queue_log(f"Server already running on {API_BASE}", "info")
            return
        except Exception:
            pass

        self._ui_queue.put(("conn_label", "● Starting server…", "#f39c12"))
        self._queue_log("Starting uvicorn server…", "info")

        env = os.environ.copy()
        env.update(self._load_dotenv())
        env.setdefault("WEBSCRAPER_PORT", _PORT)

        python = Path(sys.executable)
        python_exe = python.parent / "python.exe"
        exe = str(python_exe if python_exe.exists() else python)

        cmd = [
            exe, "-m", "uvicorn",
            "webscraper.ticket_api.app:app",
            "--host", "0.0.0.0",
            "--port", env["WEBSCRAPER_PORT"],
            "--app-dir", str(self._project_root / "webscraper" / "src"),
        ]

        self._queue_log(f"CMD: {' '.join(cmd)}", "info")

        kwargs: dict = dict(
            cwd=str(self._project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self._server_proc = subprocess.Popen(cmd, **kwargs)
            threading.Thread(
                target=self._stream_server_output, daemon=True, name="server-log"
            ).start()
        except Exception as exc:
            self._queue_log(f"Server failed to start: {exc}", "error")
            self._ui_queue.put(("conn_label", f"● Server failed to start: {exc}", "#e74c3c"))

    def _ensure_deploy_backend(self) -> None:
        """Auto-start the local deploy backend if DEPLOY_HOST is localhost."""
        host = os.getenv("DEPLOY_HOST", "localhost").strip().lower()
        if host not in ("localhost", "127.0.0.1"):
            return  # remote backend — don't manage it locally

        health_url = f"http://localhost:{_DEPLOY_PORT}/api/health"
        try:
            requests.get(health_url, timeout=2)
            self._queue_log("Deploy backend already running on localhost", "info")
            return
        except Exception:
            pass

        self._queue_log("Starting local deploy backend…", "info")

        python = Path(sys.executable)
        python_exe = python.parent / "python.exe"
        exe = str(python_exe if python_exe.exists() else python)

        src_dir = str(self._project_root / "freepbx-deploy-backend" / "src")
        env = os.environ.copy()
        env["PYTHONPATH"] = src_dir

        cmd = [
            exe, "-m", "uvicorn",
            "freepbx_deploy_backend.main:app",
            "--host", "0.0.0.0",
            "--port", _DEPLOY_PORT,
        ]

        kwargs: dict = dict(
            cwd=str(self._project_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self._deploy_backend_proc = subprocess.Popen(cmd, **kwargs)
            self._queue_log(f"Deploy backend started (pid {self._deploy_backend_proc.pid})", "info")
        except Exception as exc:
            self._queue_log(f"Deploy backend failed to start: {exc}", "error")

    def _stream_server_output(self) -> None:
        if not self._server_proc or not self._server_proc.stdout:
            return
        for raw in self._server_proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            upper = line.upper()
            if "ERROR" in upper or "CRITICAL" in upper:
                level = "error"
            elif "WARNING" in upper or "WARN" in upper:
                level = "warning"
            else:
                level = "info"
            self._queue_log(f"[server] {line}", level)
        self._queue_log("[server] process exited", "warning")

    def _on_close(self) -> None:
        self._closing = True
        # Stop log tail stream if active
        stop_evt = self._sdiag_w.get("tail_stop_event")
        if stop_evt:
            stop_evt.set()
        # Cancel scheduled after-callbacks
        for key in ("auto_refresh_after_id", "call_watch_after_id"):
            aid = self._sdiag_w.get(key)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
        for proc in (self._server_proc, self._deploy_backend_proc):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._kill_ssh_tunnel()
        self.destroy()

    def _kill_ssh_tunnel(self) -> None:
        proc = self._ssh_tunnel_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._ssh_tunnel_proc = None
        self._ssh_tunnel_alive = False

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_main()
        self._build_footer()

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, height=56, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="Scrape Manager",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        self._lbl_vpn = ctk.CTkLabel(
            hdr, text="● VPN …",
            font=ctk.CTkFont(size=12),
            text_color="#7f8c8d",
        )
        self._lbl_vpn.grid(row=0, column=1, padx=(0, 8), sticky="e")

        self._lbl_conn = ctk.CTkLabel(
            hdr, text="● Connecting…",
            font=ctk.CTkFont(size=12),
            text_color="#f39c12",
        )
        self._lbl_conn.grid(row=0, column=2, padx=(0, 8), sticky="e")

        self._lbl_job_badge = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12))
        self._lbl_job_badge.grid(row=0, column=3, padx=(0, 16), sticky="e")

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(8, 0))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self._top_tabs = ctk.CTkTabview(main)
        self._top_tabs.grid(row=0, column=0, sticky="nsew")

        tickets_tab = self._top_tabs.add("Tickets")
        vpbx_tab    = self._top_tabs.add("VPBX")
        phone_tab   = self._top_tabs.add("Phone Configs")
        site_tab    = self._top_tabs.add("Site Config")
        noc_tab     = self._top_tabs.add("NOC Queue")
        orders_tab  = self._top_tabs.add("Orders")
        log_tab     = self._top_tabs.add("Server Log")

        self._build_tickets_tab(tickets_tab)
        self._build_vpbx_tab(vpbx_tab)
        self._build_phone_configs_tab(phone_tab)
        self._build_site_config_tab(site_tab)
        self._build_noc_queue_tab(noc_tab)
        self._build_orders_tab(orders_tab)
        self._build_log_tab(log_tab)

        diag_tab = self._top_tabs.add("Diagnostics")
        self._build_diagnostics_tab(diag_tab)

    # ── Tickets tab ───────────────────────────────────────────────────────────

    def _build_tickets_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        self._build_ticket_controls(tab)   # row 0
        self._build_ticket_panels(tab)     # row 1

    def _build_ticket_controls(self, parent: Any) -> None:
        row = ctk.CTkFrame(parent, corner_radius=8)
        row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure(4, weight=1)

        btn_cfg = dict(width=120, height=36, font=ctk.CTkFont(size=13))

        self._btn_start = ctk.CTkButton(
            row, text="▶  Deploy", fg_color="#27ae60", hover_color="#1e8449",
            command=self._on_start, **btn_cfg,
        )
        self._btn_start.grid(row=0, column=0, padx=(12, 6), pady=10)

        self._btn_resume = ctk.CTkButton(
            row, text="↺  Resume", fg_color="#2980b9", hover_color="#1f6391",
            command=self._on_resume, **btn_cfg,
        )
        self._btn_resume.grid(row=0, column=1, padx=6, pady=10)

        self._btn_pause = ctk.CTkButton(
            row, text="⏸  Pause", fg_color="#8e44ad", hover_color="#6c3483",
            command=self._on_pause_resume, state="disabled", **btn_cfg,
        )
        self._btn_pause.grid(row=0, column=2, padx=6, pady=10)

        self._btn_stop = ctk.CTkButton(
            row, text="■  Stop", fg_color="#c0392b", hover_color="#922b21",
            command=self._on_stop, state="disabled", **btn_cfg,
        )
        self._btn_stop.grid(row=0, column=3, padx=6, pady=10)

        self._btn_smoke = ctk.CTkButton(
            row, text="🧪  Smoke Test", fg_color="#d35400", hover_color="#a04000",
            command=self._on_smoke_test, width=130, height=36, font=ctk.CTkFont(size=13),
        )
        self._btn_smoke.grid(row=0, column=4, padx=6, pady=10)

        self._btn_doctor = ctk.CTkButton(
            row, text="🩺  Doctor", fg_color="#16a085", hover_color="#0e6655",
            command=self._on_doctor, width=110, height=36, font=ctk.CTkFont(size=13),
        )
        self._btn_doctor.grid(row=0, column=5, padx=6, pady=10)

        self._btn_refresh = ctk.CTkButton(
            row, text="⟳  Refresh", fg_color="#7f8c8d", hover_color="#626567",
            command=self._force_refresh, width=100, height=36, font=ctk.CTkFont(size=13),
        )
        self._btn_refresh.grid(row=0, column=6, padx=(6, 12), pady=10)

    def _build_ticket_panels(self, parent: Any) -> None:
        sub = ctk.CTkTabview(parent)
        sub.grid(row=1, column=0, sticky="nsew")

        monitor_tab = sub.add("Monitor")
        events_tab  = sub.add("Events")
        history_tab = sub.add("History")

        self._build_monitor_tab(monitor_tab)
        self._build_events_tab(events_tab)
        self._build_history_tab(history_tab)

    # ── Monitor tab ───────────────────────────────────────────────────────────

    def _build_monitor_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        info_row = ctk.CTkFrame(tab, corner_radius=8)
        info_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        info_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(info_row, text="Job ID:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=8, sticky="w"
        )
        self._lbl_job_id = ctk.CTkLabel(info_row, text="—", text_color="#7f8c8d")
        self._lbl_job_id.grid(row=0, column=1, padx=4, sticky="w")

        self._lbl_status = ctk.CTkLabel(info_row, text="", font=ctk.CTkFont(weight="bold"))
        self._lbl_status.grid(row=0, column=2, padx=12, sticky="e")

        prog_frame = ctk.CTkFrame(tab, corner_radius=8)
        prog_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        prog_frame.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(prog_frame, height=20, corner_radius=6)
        self._progress.set(0)
        self._progress.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        self._lbl_progress = ctk.CTkLabel(
            prog_frame, text="0 / 0 handles", font=ctk.CTkFont(size=12),
        )
        self._lbl_progress.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="w")

        self._lbl_step = ctk.CTkLabel(
            prog_frame, text="", font=ctk.CTkFont(size=12), text_color="#7f8c8d",
        )
        self._lbl_step.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="w")

        self._login_hint = ctk.CTkLabel(
            tab,
            text="⚠  A Chrome window will open — log in to 123.net when prompted.",
            font=ctk.CTkFont(size=12),
            text_color="#f39c12",
            wraplength=700,
        )

        stats_frame = ctk.CTkFrame(tab, corner_radius=8)
        stats_frame.grid(row=3, column=0, sticky="nsew")
        for i in range(4):
            stats_frame.grid_columnconfigure(i, weight=1)

        self._stat_widgets: dict[str, ctk.CTkLabel] = {}
        for col, (key, label) in enumerate([
            ("started_at",    "Started"),
            ("completed_at",  "Finished"),
            ("error_message", "Error"),
        ]):
            ctk.CTkLabel(
                stats_frame, text=label, font=ctk.CTkFont(size=11), text_color="#7f8c8d",
            ).grid(row=0, column=col, padx=16, pady=(12, 2), sticky="w")
            lbl = ctk.CTkLabel(stats_frame, text="—", font=ctk.CTkFont(size=12))
            lbl.grid(row=1, column=col, padx=16, pady=(0, 12), sticky="w")
            self._stat_widgets[key] = lbl

    # ── Events tab ────────────────────────────────────────────────────────────

    def _build_events_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(tab, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self._events_text = tk.Text(
            frame,
            bg="#1a1a2e", fg="#ecf0f1",
            font=("Consolas", 11),
            state="disabled", relief="flat", wrap="word",
            padx=8, pady=8,
        )
        self._events_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(frame, command=self._events_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._events_text.configure(yscrollcommand=scrollbar.set)

        self._events_text.tag_configure("error",   foreground="#e74c3c")
        self._events_text.tag_configure("warning", foreground="#f39c12")
        self._events_text.tag_configure("info",    foreground="#3498db")
        self._events_text.tag_configure("ts",      foreground="#7f8c8d")

        btn_clear = ctk.CTkButton(
            tab, text="Clear", width=80, height=28,
            command=self._clear_events,
            fg_color="#7f8c8d", hover_color="#626567",
        )
        btn_clear.grid(row=1, column=0, sticky="e", pady=(4, 0))

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(tab, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#2b2b3b", foreground="#ecf0f1",
            rowheight=24, fieldbackground="#2b2b3b", borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure("Treeview.Heading", background="#1a1a2e", foreground="#ecf0f1",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#2980b9")])

        cols = ("job_id", "state", "progress", "step", "started", "finished")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)

        col_cfg = {
            "job_id":   ("Job ID",   90,  "w"),
            "state":    ("State",    90,  "center"),
            "progress": ("Progress", 80,  "center"),
            "step":     ("Step",     220, "w"),
            "started":  ("Started",  80,  "center"),
            "finished": ("Finished", 80,  "center"),
        }
        for col, (heading, width, anchor) in col_cfg.items():
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "step"))

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<Double-1>", self._on_history_double_click)

    # ── Server Log tab ────────────────────────────────────────────────────────

    def _build_log_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(tab, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self._log_text = tk.Text(
            frame,
            bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 10),
            state="disabled", relief="flat", wrap="none",
            padx=8, pady=8,
        )
        self._log_text.grid(row=0, column=0, sticky="nsew")

        xsb = ctk.CTkScrollbar(frame, orientation="horizontal", command=self._log_text.xview)
        xsb.grid(row=1, column=0, sticky="ew")
        ysb = ctk.CTkScrollbar(frame, command=self._log_text.yview)
        ysb.grid(row=0, column=1, sticky="ns")
        self._log_text.configure(xscrollcommand=xsb.set, yscrollcommand=ysb.set)

        self._log_text.tag_configure("error",   foreground="#f85149")
        self._log_text.tag_configure("warning", foreground="#d29922")
        self._log_text.tag_configure("info",    foreground="#c9d1d9")

        btn_clear_log = ctk.CTkButton(
            tab, text="Clear", width=80, height=28,
            command=self._clear_log,
            fg_color="#7f8c8d", hover_color="#626567",
        )
        btn_clear_log.grid(row=1, column=0, sticky="e", pady=(4, 0))

    # ── Reusable scraper panel ────────────────────────────────────────────────

    def _build_scraper_panel(
        self, tab: Any, key: str, *, extra_controls_fn: Any = None
    ) -> None:
        """Build a self-contained scraper tab: controls + progress + login hint + live events."""
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)   # events area expands

        w: dict = {}
        self._scraper_w[key] = w

        # ── Controls row ─────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(tab, corner_radius=8)
        ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        next_col = [0]   # mutable counter passed into extra_controls_fn

        if extra_controls_fn:
            extra_controls_fn(ctrl, w, next_col)

        cfg_for_key = next((c for c in _SCRAPERS if c["key"] == key), {})
        has_resume = bool(cfg_for_key.get("api_state"))

        col = next_col[0]
        w["btn_start"] = ctk.CTkButton(
            ctrl, text="▶  Scrape",
            fg_color="#27ae60", hover_color="#1e8449",
            width=120, height=36, font=ctk.CTkFont(size=13),
            command=lambda k=key: self._on_scraper_start(k),
        )
        padx_left = 12 if col == 0 else 6
        w["btn_start"].grid(row=0, column=col, padx=(padx_left, 6), pady=10)
        col += 1

        if has_resume:
            w["btn_resume_last"] = ctk.CTkButton(
                ctrl, text="↺  Resume",
                fg_color="#2980b9", hover_color="#1f6391",
                width=120, height=36, font=ctk.CTkFont(size=13),
                state="disabled",
                command=lambda k=key: self._on_scraper_resume_last(k),
            )
            w["btn_resume_last"].grid(row=0, column=col, padx=6, pady=10)
            col += 1

        w["btn_pause"] = ctk.CTkButton(
            ctrl, text="⏸  Pause",
            fg_color="#8e44ad", hover_color="#6c3483",
            width=110, height=36, font=ctk.CTkFont(size=13),
            state="disabled",
            command=lambda k=key: self._on_scraper_pause_resume(k),
        )
        w["btn_pause"].grid(row=0, column=col, padx=6, pady=10)
        col += 1

        w["btn_stop"] = ctk.CTkButton(
            ctrl, text="■  Stop",
            fg_color="#c0392b", hover_color="#922b21",
            width=100, height=36, font=ctk.CTkFont(size=13),
            state="disabled",
            command=lambda k=key: self._on_scraper_stop(k),
        )
        w["btn_stop"].grid(row=0, column=col, padx=6, pady=10)
        col += 1

        w["lbl_badge"] = ctk.CTkLabel(
            ctrl, text="idle",
            font=ctk.CTkFont(size=12), text_color="#7f8c8d",
        )
        w["lbl_badge"].grid(row=0, column=col, padx=(4, 12), pady=10, sticky="w")

        # ── Progress ─────────────────────────────────────────────────────────
        prog = ctk.CTkFrame(tab, corner_radius=8)
        prog.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        prog.grid_columnconfigure(0, weight=1)

        w["progress"] = ctk.CTkProgressBar(prog, height=18, corner_radius=6)
        w["progress"].set(0)
        w["progress"].grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        w["lbl_step"] = ctk.CTkLabel(
            prog, text="", font=ctk.CTkFont(size=12), text_color="#7f8c8d",
        )
        w["lbl_step"].grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        # Login hint (hidden until scraper navigates to login page)
        hint_text = next(
            (c["login_hint"] for c in _SCRAPERS if c["key"] == key),
            "Chrome will open — authenticate when prompted.",
        )
        w["login_hint"] = ctk.CTkLabel(
            tab, text=f"⚠  {hint_text}",
            font=ctk.CTkFont(size=12), text_color="#f39c12", wraplength=800,
        )

        # ── Live events text area ─────────────────────────────────────────────
        evts_frame = ctk.CTkFrame(tab, corner_radius=8)
        evts_frame.grid(row=3, column=0, sticky="nsew")
        evts_frame.grid_columnconfigure(0, weight=1)
        evts_frame.grid_rowconfigure(0, weight=1)

        w["events"] = tk.Text(
            evts_frame,
            bg="#1a1a2e", fg="#ecf0f1",
            font=("Consolas", 11),
            state="disabled", relief="flat", wrap="word",
            padx=8, pady=8,
        )
        w["events"].grid(row=0, column=0, sticky="nsew")

        ysb = ctk.CTkScrollbar(evts_frame, command=w["events"].yview)
        ysb.grid(row=0, column=1, sticky="ns")
        w["events"].configure(yscrollcommand=ysb.set)

        w["events"].tag_configure("error",   foreground="#e74c3c")
        w["events"].tag_configure("warning", foreground="#f39c12")
        w["events"].tag_configure("info",    foreground="#3498db")

        ctk.CTkButton(
            tab, text="Clear", width=80, height=28,
            fg_color="#7f8c8d", hover_color="#626567",
            command=lambda k=key: self._clear_scraper_events(k),
        ).grid(row=4, column=0, sticky="e", pady=(4, 0))

    # ── VPBX tab ──────────────────────────────────────────────────────────────

    def _build_vpbx_tab(self, tab: Any) -> None:
        self._build_scraper_panel(tab, "vpbx")

    # ── Phone Configs tab ─────────────────────────────────────────────────────

    def _build_phone_configs_tab(self, tab: Any) -> None:
        def _extra(ctrl: Any, w: dict, next_col: list) -> None:
            c = next_col[0]
            ctk.CTkLabel(ctrl, text="Handle(s):", font=ctk.CTkFont(size=12)).grid(
                row=0, column=c, padx=(12, 4), pady=10, sticky="w"
            )
            c += 1
            w["handle_entry"] = ctk.CTkEntry(
                ctrl, placeholder_text="e.g. ACG or ACG,BTI  (blank = all)",
                width=220, height=36,
            )
            w["handle_entry"].grid(row=0, column=c, padx=(0, 10), pady=10)
            c += 1
            w["chk_force_var"] = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(ctrl, text="Force re-scrape", variable=w["chk_force_var"]).grid(
                row=0, column=c, padx=(0, 10), pady=10
            )
            c += 1
            w["chk_incomplete_var"] = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(ctrl, text="Incomplete only", variable=w["chk_incomplete_var"]).grid(
                row=0, column=c, padx=(0, 10), pady=10
            )
            c += 1
            next_col[0] = c

        self._build_scraper_panel(tab, "phone_configs", extra_controls_fn=_extra)

    # ── Site Config tab ───────────────────────────────────────────────────────

    def _build_site_config_tab(self, tab: Any) -> None:
        def _extra(ctrl: Any, w: dict, next_col: list) -> None:
            c = next_col[0]
            ctk.CTkLabel(ctrl, text="Handle(s):", font=ctk.CTkFont(size=12)).grid(
                row=0, column=c, padx=(12, 4), pady=10, sticky="w"
            )
            c += 1
            w["handle_entry"] = ctk.CTkEntry(
                ctrl, placeholder_text="e.g. ACG or leave blank for all",
                width=240, height=36,
            )
            w["handle_entry"].grid(row=0, column=c, padx=(0, 10), pady=10)
            c += 1
            next_col[0] = c

        self._build_scraper_panel(tab, "site_config", extra_controls_fn=_extra)

    # ── NOC Queue tab ─────────────────────────────────────────────────────────

    def _build_noc_queue_tab(self, tab: Any) -> None:
        _VIEW_LABELS = ["All Queues", "Hosted", "NOC", "All Queue", "Local NOC"]

        def _extra(ctrl: Any, w: dict, next_col: list) -> None:
            c = next_col[0]
            ctk.CTkLabel(ctrl, text="View:", font=ctk.CTkFont(size=12)).grid(
                row=0, column=c, padx=(12, 4), pady=10, sticky="w"
            )
            c += 1
            w["view_var"] = tk.StringVar(value="All Queues")
            ctk.CTkOptionMenu(
                ctrl,
                variable=w["view_var"],
                values=_VIEW_LABELS,
                width=160, height=36,
            ).grid(row=0, column=c, padx=(0, 10), pady=10)
            c += 1
            next_col[0] = c

        self._build_scraper_panel(tab, "noc_queue", extra_controls_fn=_extra)

    # ── Orders tab ───────────────────────────────────────────────────────────

    def _build_orders_tab(self, tab: Any) -> None:
        self._build_scraper_panel(tab, "orders")

    # ── Server log tail ───────────────────────────────────────────────────────

    def _tail_log_loop(self) -> None:
        log_path = self._project_root / "webscraper" / "var" / "logs" / "ticket_api.log"
        try:
            if log_path.exists():
                self._log_file_pos = log_path.stat().st_size
        except Exception:
            pass
        while not self._closing:
            try:
                if log_path.exists():
                    size = log_path.stat().st_size
                    if size < self._log_file_pos:
                        self._log_file_pos = 0
                    if size > self._log_file_pos:
                        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self._log_file_pos)
                            new_text = f.read(65536)
                            self._log_file_pos = f.tell()
                        if new_text:
                            self._ui_queue.put(("server_log", new_text))
            except Exception:
                pass
            time.sleep(0.5)

    def _append_server_log(self, text: str) -> None:
        self._log_text.configure(state="normal")
        for line in text.splitlines():
            upper = line.upper()
            tag = "error" if ("ERROR" in upper or "CRITICAL" in upper) \
                else "warning" if ("WARNING" in upper or "WARN" in upper) \
                else "info"
            self._log_text.insert("end", line + "\n", tag)
        line_count = int(self._log_text.index("end-1c").split(".")[0])
        if line_count > 2000:
            self._log_text.delete("1.0", f"{line_count - 2000}.0")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, height=30, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self._lbl_footer = ctk.CTkLabel(
            footer, text=f"API: {API_BASE}",
            font=ctk.CTkFont(size=10), text_color="#7f8c8d",
        )
        self._lbl_footer.grid(row=0, column=0, padx=12, sticky="w")

        self._lbl_last_update = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=10), text_color="#7f8c8d",
        )
        self._lbl_last_update.grid(row=0, column=1, padx=12, sticky="e")

    # ── Ticket scraper button callbacks ───────────────────────────────────────

    def _on_start(self) -> None:
        if not self._connected:
            messagebox.showerror(
                "Not Connected",
                "Server is still starting up — wait a moment, then try again.\n\n"
                f"If the problem persists check that .env is configured correctly\n"
                f"in:\n  {self._project_root / '.env'}",
            )
            return
        if self._active_job and self._active_job.get("current_state") in _ACTIVE:
            if not messagebox.askyesno("Job Running",
                                       "A scrape job is already running.\nStart a new one anyway?"):
                return
        self._run_in_thread(self._do_start, fresh=True)

    def _on_resume(self) -> None:
        if not self._connected:
            messagebox.showerror("Not Connected",
                                 "Server is still starting up — wait a moment, then try again.")
            return
        self._run_in_thread(self._do_start, fresh=False)

    def _on_pause_resume(self) -> None:
        job = self._active_job
        if not job:
            return
        jid = job.get("job_id", "")
        if self._job_paused:
            self._run_in_thread(self._do_resume, job_id=jid)
        else:
            self._run_in_thread(self._do_pause, job_id=jid)

    def _on_smoke_test(self) -> None:
        if not self._connected:
            messagebox.showerror("Not Connected", "Server is still starting up.")
            return
        if not messagebox.askyesno("Smoke Test",
                                   "Run a quick end-to-end test on the first 2 handles?\n\n"
                                   "Chrome will open and you will need to authenticate."):
            return
        self._run_in_thread(self._do_smoke_test)

    def _on_doctor(self) -> None:
        if not self._connected:
            messagebox.showerror("Not Connected", "Server is still starting up.")
            return
        self._run_in_thread(self._do_doctor)

    def _on_stop(self) -> None:
        job = self._active_job
        if not job:
            return
        jid = job.get("job_id", "")
        if not messagebox.askyesno(
            "Cancel Job",
            f"Cancel job {jid[:16]}…?\n\n"
            "The scraper will finish the current handle, then stop.\n"
            "Progress is saved and you can resume later.",
        ):
            return
        self._run_in_thread(self._do_stop, job_id=jid)

    def _force_refresh(self) -> None:
        self._run_poll()

    def _on_history_double_click(self, _event: Any) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        job_id = item["values"][0] if item["values"] else None
        if job_id:
            match = next((j for j in self._jobs if j.get("job_id", "").startswith(job_id)), None)
            if match:
                self._active_job = match
                self._refresh_monitor_tab(match, [])
                self._run_in_thread(self._fetch_and_show_events, job_id=match["job_id"])

    # ── Scraper tab button callbacks ──────────────────────────────────────────

    def _on_scraper_start(self, key: str) -> None:
        if not self._connected:
            messagebox.showerror("Not Connected", "Server is still starting up.")
            return
        if self._scraper[key]["running"]:
            messagebox.showinfo("Already Running", f"A {key} scrape job is already in progress.")
            return
        payload = self._build_scraper_payload(key)
        self._run_in_thread(self._do_scraper_start, key=key, payload=payload)

    def _on_scraper_pause_resume(self, key: str) -> None:
        s = self._scraper[key]
        jid = s.get("job_id")
        if not jid:
            return
        if s.get("paused"):
            self._run_in_thread(self._do_scraper_resume, key=key, job_id=jid)
        else:
            self._run_in_thread(self._do_scraper_pause, key=key, job_id=jid)

    def _on_scraper_resume_last(self, key: str) -> None:
        if not self._connected:
            messagebox.showerror("Not Connected", "Server is still starting up.")
            return
        if self._scraper[key]["running"]:
            messagebox.showinfo("Already Running", "A scrape job is already in progress.")
            return
        self._run_in_thread(self._do_scraper_resume_last, key=key)

    def _do_scraper_resume_last(self, key: str) -> None:
        cfg = next((c for c in _SCRAPERS if c["key"] == key), {})
        state_api = cfg.get("api_state")
        if not state_api:
            return
        try:
            state = _get(state_api)
            last = (state or {}).get("last_completed_handle")
            if not last:
                self.after(0, lambda: messagebox.showinfo(
                    "No Resume Point",
                    f"No previous {cfg.get('label', key)} scrape found.\nUse Scrape to start fresh.",
                ))
                return
            payload = self._build_scraper_payload(key)
            payload["resume_from_handle"] = last
            self._scraper_append_event(key, f"Resuming from handle: {last}", "info")
            self._do_scraper_start(key=key, payload=payload)
        except Exception as exc:
            self._scraper_append_event(key, f"Resume error: {exc}", "error")

    def _on_scraper_stop(self, key: str) -> None:
        s = self._scraper[key]
        jid = s.get("job_id")
        if not jid:
            return
        cfg = next(c for c in _SCRAPERS if c["key"] == key)
        if not messagebox.askyesno(
            "Stop Scrape",
            f"Stop the {cfg['label']} scrape?\n\n"
            "Any handles already completed have been saved.",
        ):
            return
        self._run_in_thread(self._do_scraper_stop, key=key, job_id=jid)

    def _do_scraper_pause(self, key: str, job_id: str) -> None:
        w = self._scraper_w.get(key, {})
        try:
            _post("/api/scrape/pause", json={"job_id": job_id})
            self._scraper[key]["paused"] = True
            self._scraper_append_event(key, "Pause requested — will pause after current handle.", "warning")
            self.after(0, lambda: w["btn_pause"].configure(
                text="▶  Resume", fg_color="#27ae60", hover_color="#1e8449",
            ))
        except Exception as exc:
            self._scraper_append_event(key, f"Pause error: {exc}", "error")

    def _do_scraper_resume(self, key: str, job_id: str) -> None:
        w = self._scraper_w.get(key, {})
        try:
            _post("/api/scrape/resume", json={"job_id": job_id})
            self._scraper[key]["paused"] = False
            self._scraper_append_event(key, "Resumed.", "info")
            self.after(0, lambda: w["btn_pause"].configure(
                text="⏸  Pause", fg_color="#8e44ad", hover_color="#6c3483",
            ))
        except Exception as exc:
            self._scraper_append_event(key, f"Resume error: {exc}", "error")

    def _do_scraper_stop(self, key: str, job_id: str) -> None:
        try:
            _post("/api/scrape/cancel", json={"job_id": job_id})
            self._scraper_append_event(key, "Stop requested — finishing current handle then stopping.", "warning")
        except Exception as exc:
            self._scraper_append_event(key, f"Stop error: {exc}", "error")

    def _build_scraper_payload(self, key: str) -> dict:
        w = self._scraper_w.get(key, {})

        if key == "vpbx":
            return {}

        elif key == "phone_configs":
            raw = w.get("handle_entry", None)
            raw_text = (raw.get().strip() if raw else "") or ""
            handles = [h.strip().upper() for h in raw_text.split(",") if h.strip()] or None
            payload: dict = {}
            if handles:
                payload["handles"] = handles
            if w.get("chk_force_var") and w["chk_force_var"].get():
                payload["force"] = True
            if w.get("chk_incomplete_var") and w["chk_incomplete_var"].get():
                payload["incomplete_only"] = True
            return payload

        elif key == "site_config":
            raw = w.get("handle_entry", None)
            raw_text = (raw.get().strip() if raw else "") or ""
            handles = [h.strip().upper() for h in raw_text.split(",") if h.strip()] or None
            return {"handles": handles} if handles else {}

        elif key == "noc_queue":
            _view_map = {
                "All Queues": None,
                "Hosted":     "hosted",
                "NOC":        "noc",
                "All Queue":  "all",
                "Local NOC":  "local",
            }
            label = w.get("view_var") and w["view_var"].get() or "All Queues"
            view = _view_map.get(label)
            return {"view": view} if view else {}

        return {}

    def _do_scraper_start(self, key: str, payload: dict) -> None:
        w = self._scraper_w.get(key, {})
        self.after(0, lambda: w["btn_start"].configure(state="disabled", text="Running…"))
        try:
            api_path = next(c["api_start"] for c in _SCRAPERS if c["key"] == key)
            data = _post(api_path, json=payload)
            job_id = data.get("job_id", "")
            self._scraper[key]["job_id"] = job_id
            self._scraper[key]["running"] = True
            self._scraper[key]["event_ids"] = set()
            self._scraper_append_event(key, f"Job queued: {job_id}", "info")
            cfg = next(c for c in _SCRAPERS if c["key"] == key)
            self._scraper_append_event(key, cfg["login_hint"], "warning")
            # Show login hint label
            self.after(0, lambda: w["login_hint"].grid(row=2, column=0, sticky="ew", pady=(0, 4)))
        except requests.HTTPError as exc:
            self._scraper_append_event(key, f"Start failed: {exc.response.text}", "error")
            messagebox.showerror("Start Failed", exc.response.text)
            self.after(0, lambda: w["btn_start"].configure(state="normal", text="▶  Scrape"))
        except Exception as exc:
            self._scraper_append_event(key, f"Error: {exc}", "error")
            self.after(0, lambda: w["btn_start"].configure(state="normal", text="▶  Scrape"))

    # ── API actions (ticket scraper) ──────────────────────────────────────────

    def _run_in_thread(self, fn: Any, **kwargs: Any) -> None:
        threading.Thread(target=fn, kwargs=kwargs, daemon=True).start()

    def _do_start(self, fresh: bool) -> None:
        self._set_buttons_busy()
        try:
            payload: dict = {}
            if not fresh:
                state = _fetch_state()
                last = state.get("last_completed_handle")
                if last:
                    payload = {"resume_from_handle": last}
                    self._queue_log(f"Resuming after handle: {last}", "info")
                else:
                    self._queue_log("No checkpoint found — starting fresh.", "warning")

            data = _post("/api/scrape/start", json=payload)
            job_id = data["job_id"]
            self._queue_log(f"Job queued: {job_id}", "info")
            self._queue_log("Chrome will open — log in to 123.net when prompted.", "warning")
            self._ui_queue.put(("set_active_job_id", job_id))
        except requests.HTTPError as exc:
            self._queue_log(f"Start failed: {exc.response.text}", "error")
            messagebox.showerror("Start Failed", exc.response.text)
        except Exception as exc:
            self._queue_log(f"Start error: {exc}", "error")
            messagebox.showerror("Error", str(exc))
        finally:
            self._ui_queue.put(("refresh",))

    def _do_pause(self, job_id: str) -> None:
        try:
            _post("/api/scrape/pause", json={"job_id": job_id})
            self._job_paused = True
            self._queue_log("Pause requested — will pause after current handle.", "warning")
            self._ui_queue.put(("set_paused", True))
        except Exception as exc:
            self._queue_log(f"Pause error: {exc}", "error")

    def _do_resume(self, job_id: str) -> None:
        try:
            _post("/api/scrape/resume", json={"job_id": job_id})
            self._job_paused = False
            self._queue_log("Job resumed.", "info")
            self._ui_queue.put(("set_paused", False))
        except Exception as exc:
            self._queue_log(f"Resume error: {exc}", "error")

    def _do_smoke_test(self) -> None:
        self._set_buttons_busy()
        try:
            data = _post("/api/scrape/smoke_test")
            job_id = data["job_id"]
            self._queue_log(f"Smoke test queued: {job_id} (2 handles)", "info")
            self._queue_log("Chrome will open — authenticate when prompted.", "warning")
            self._ui_queue.put(("set_active_job_id", job_id))
        except requests.HTTPError as exc:
            self._queue_log(f"Smoke test failed: {exc.response.text}", "error")
            messagebox.showerror("Smoke Test Failed", exc.response.text)
        except Exception as exc:
            self._queue_log(f"Smoke test error: {exc}", "error")
            messagebox.showerror("Error", str(exc))
        finally:
            self._ui_queue.put(("refresh",))

    def _do_doctor(self) -> None:
        try:
            data = _get("/api/doctor")
        except Exception as exc:
            self._queue_log(f"Doctor error: {exc}", "error")
            messagebox.showerror("Doctor Error", str(exc))
            return

        checks  = data.get("checks", {})
        overall = data.get("ok", False)

        win = tk.Toplevel(self)
        win.title("Doctor — System Check")
        win.geometry("560x380")
        win.configure(bg="#0d1117")
        win.resizable(True, True)

        tk.Label(
            win,
            text="✅  All checks passed" if overall else "❌  One or more checks failed",
            fg="#2ecc71" if overall else "#e74c3c",
            bg="#0d1117", font=("Segoe UI", 13, "bold"), pady=12,
        ).pack(fill="x")

        frame = tk.Frame(win, bg="#0d1117")
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for name, info in checks.items():
            ok    = info.get("ok", False)
            icon  = "✅" if ok else "❌"
            color = "#2ecc71" if ok else "#e74c3c"
            label = info.get("detail", "")
            row_frame = tk.Frame(frame, bg="#161b22", pady=4)
            row_frame.pack(fill="x", pady=3)
            tk.Label(row_frame, text=f"  {icon}  {name}", fg=color, bg="#161b22",
                     font=("Consolas", 11, "bold"), width=20, anchor="w").pack(side="left")
            tk.Label(row_frame, text=label, fg="#c9d1d9", bg="#161b22",
                     font=("Consolas", 10), anchor="w", wraplength=360).pack(
                         side="left", fill="x", expand=True)

        tk.Button(
            win, text="Close", command=win.destroy,
            bg="#21262d", fg="#c9d1d9", relief="flat",
            font=("Segoe UI", 11), padx=20, pady=6,
        ).pack(pady=8)

    def _do_stop(self, job_id: str) -> None:
        try:
            data = _post("/api/scrape/cancel", json={"job_id": job_id})
            self._queue_log(data.get("message", "Cancel requested."), "warning")
        except requests.HTTPError as exc:
            self._queue_log(f"Stop failed: {exc.response.text}", "error")
            messagebox.showerror("Stop Failed", exc.response.text)
        except Exception as exc:
            self._queue_log(f"Stop error: {exc}", "error")

    def _heartbeat_loop(self) -> None:
        import socket as _socket
        client_id = _socket.gethostname().lower()
        first = True
        while not self._closing:
            if not first:
                for _ in range(30):
                    if self._closing:
                        return
                    time.sleep(1)
            first = False

            vpn_ok, vpn_ip = detect_vpn()
            self._vpn_connected = vpn_ok
            self._vpn_ip = vpn_ip
            self._ui_queue.put(("vpn", vpn_ok, vpn_ip))

            if not self._connected:
                continue

            job    = self._active_job or {}
            state  = job.get("current_state", "")
            step   = (job.get("current_step") or "")

            if state == "running":
                status = "waiting_login" if ("login" in step or "browser" in step) else "scraping"
            elif state == "queued":
                status = "queued"
            else:
                status = "idle"

            handle = None
            if "scraping_handle " in step:
                handle = step.replace("scraping_handle ", "").strip()

            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            try:
                _post("/api/client/heartbeat", json={
                    "client_id":      client_id,
                    "status":         status,
                    "vpn_connected":  vpn_ok,
                    "vpn_ip":         vpn_ip,
                    "job_id":         job.get("job_id"),
                    "current_handle": handle,
                    "handles_done":   job.get("records_written"),
                    "handles_total":  job.get("records_found"),
                })
            except Exception:
                pass

    def _fetch_and_show_events(self, job_id: str) -> None:
        try:
            evts = _fetch_events(job_id, limit=100)
            self._ui_queue.put(("load_events", evts))
        except Exception:
            pass

    # ── Polling ───────────────────────────────────────────────────────────────

    def _schedule_poll(self, delay_ms: int | None = None) -> None:
        if self._poll_after_id:
            self.after_cancel(self._poll_after_id)
        active = self._active_job and self._active_job.get("current_state") in _ACTIVE
        any_scraper_active = any(s["running"] for s in self._scraper.values())
        if delay_ms is not None:
            ms = delay_ms
        elif not self._connected:
            ms = 2_000   # retry quickly while server is starting up
        elif active or any_scraper_active:
            ms = POLL_FAST_MS
        else:
            ms = POLL_SLOW_MS
        self._poll_after_id = self.after(ms, self._run_poll)

    def _run_poll(self) -> None:
        threading.Thread(target=self._poll_worker, daemon=True).start()

    def _poll_worker(self) -> None:
        # ── health check ──────────────────────────────────────────────────────
        try:
            _get("/api/health")
            connected = True
        except Exception:
            connected = False

        self._ui_queue.put(("connected", connected))

        if not connected:
            self._ui_queue.put(("schedule",))
            return

        # ── ticket scraper jobs ───────────────────────────────────────────────
        try:
            jobs = _fetch_jobs()
            self._ui_queue.put(("jobs", jobs))

            active = next((j for j in jobs if j.get("current_state") in _ACTIVE), None)
            if active is None and self._active_job:
                prev_state = self._active_job.get("current_state", "")
                if prev_state not in _TERMINAL:
                    active = next(
                        (j for j in jobs if j.get("job_id") == self._active_job.get("job_id")),
                        None,
                    )

            if active:
                job  = _fetch_job(active["job_id"])
                evts = _fetch_events(active["job_id"], limit=60)
                self._ui_queue.put(("active_job", job, evts))
                state      = job.get("current_state", "")
                done       = job.get("records_written", 0) or 0
                total      = job.get("records_found",  0) or 0
                step       = job.get("current_step", "") or ""
                prev_state = (self._active_job or {}).get("current_state", "")
                prev_step  = (self._active_job or {}).get("current_step", "")
                if state != prev_state:
                    self._queue_log(f"Job {job['job_id'][:8]} → {state} ({done}/{total})", "info")
                elif step != prev_step and step:
                    self._queue_log(f"  {step}", "info")
                if state in _TERMINAL and prev_state not in _TERMINAL:
                    self._queue_log(
                        f"Job finished: {state}",
                        "info" if state in ("completed", "done") else "warning",
                    )
        except Exception as exc:
            self._queue_log(f"Poll error: {exc}", "error")

        # ── per-scraper tab jobs ──────────────────────────────────────────────
        for cfg in _SCRAPERS:
            k = cfg["key"]
            s = self._scraper[k]
            jid = s.get("job_id")
            if jid and s.get("running"):
                try:
                    job  = _fetch_job(jid)
                    evts = _fetch_events(jid, limit=50)
                    self._ui_queue.put(("scraper_update", k, job, evts))
                except Exception:
                    pass

        self._ui_queue.put(("schedule",))

    def _queue_log(self, msg: str, level: str = "info") -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._ui_queue.put(("log", f"{ts}  {msg}", level))

    # ── UI update (main thread via after) ─────────────────────────────────────

    def _process_ui_queue(self) -> None:
        try:
            while True:
                item = self._ui_queue.get_nowait()
                cmd  = item[0]

                if cmd == "connected":
                    self._update_connection(item[1])
                elif cmd == "vpn":
                    self._update_vpn(item[1], item[2])
                elif cmd == "conn_label":
                    self._lbl_conn.configure(text=item[1], text_color=item[2])
                elif cmd == "jobs":
                    self._jobs = item[1]
                    self._refresh_history(item[1])
                elif cmd == "active_job":
                    _, job, evts = item
                    self._active_job = job
                    self._refresh_monitor_tab(job, evts)
                elif cmd == "set_active_job_id":
                    self._active_job = {"job_id": item[1], "current_state": "queued"}
                elif cmd == "log":
                    self._append_event_log(item[1], item[2] if len(item) > 2 else "info")
                elif cmd == "load_events":
                    self._load_event_log(item[1])
                elif cmd == "server_log":
                    self._append_server_log(item[1])
                elif cmd == "set_paused":
                    self._job_paused = item[1]
                    self._btn_pause.configure(
                        text="▶  Resume" if item[1] else "⏸  Pause",
                        fg_color="#27ae60" if item[1] else "#8e44ad",
                        hover_color="#1e8449" if item[1] else "#6c3483",
                    )
                elif cmd == "scraper_update":
                    _, key, job, evts = item
                    self._refresh_scraper_tab(key, job, evts)
                elif cmd == "deploy_job_update":
                    _, job, tail = item
                    self._deploy_active_job = job
                    self._refresh_deploy_tab(job, tail)
                elif cmd == "deploy_jobs":
                    self._refresh_deploy_jobs_list(item[1])
                elif cmd == "rrun_job_update":
                    _, job, tail = item
                    self._rrun_active_job = job
                    self._refresh_rrun_tab(job, tail)
                elif cmd == "sdiag_result":
                    _, data, error = item
                    self._display_sdiag_result(data, error)
                elif cmd == "sdiag_cmd_result":
                    _, data, error = item
                    self._display_sdiag_cmd_result(data, error)
                elif cmd == "sdiag_tail_line":
                    self._sdiag_append_log_line(item[1])
                elif cmd == "sdiag_tail_status":
                    w = self._sdiag_w
                    if w.get("tail_status_lbl"):
                        w["tail_status_lbl"].configure(text=item[1], text_color=item[2])
                elif cmd == "sdiag_tail_done":
                    w = self._sdiag_w
                    if w.get("tail_btn_start"):
                        w["tail_btn_start"].configure(state="normal")
                    if w.get("tail_btn_stop"):
                        w["tail_btn_stop"].configure(state="disabled")
                elif cmd == "sdiag_call_count":
                    w = self._sdiag_w
                    count = item[1]
                    if w.get("call_count_lbl"):
                        if count is None:
                            w["call_count_lbl"].configure(text="err", text_color="#e74c3c")
                        else:
                            color = "#e74c3c" if count > 0 else "#2ecc71"
                            w["call_count_lbl"].configure(text=str(count), text_color=color)
                elif cmd == "refresh":
                    self._run_poll()
                elif cmd == "schedule":
                    self._schedule_poll()

        except queue.Empty:
            pass

        from datetime import datetime
        self._lbl_last_update.configure(
            text=f"Updated {datetime.now().strftime('%H:%M:%S')}"
        )
        self.after(200, self._process_ui_queue)

    def _update_connection(self, connected: bool) -> None:
        prev = self._connected
        self._connected = connected
        if connected:
            if not prev:
                self._queue_log(f"Connected to {API_BASE}", "info")
                # Reload VPBX pickers on first connect so they don't show "offline"
                self._run_in_thread(self._do_vpbx_fetch_for_picker)
                self._run_in_thread(self._do_sdiag_vpbx_fetch)
                self._run_in_thread(self._do_rrun_vpbx_fetch)
                # Kick off deploy backend auto-connect
                threading.Thread(target=self._deploy_auto_connect, daemon=True,
                                 name="deploy-autoconn-init").start()
            self._lbl_conn.configure(text="● Connected", text_color="#2ecc71")
            self._btn_start.configure(state="normal")
            self._btn_resume.configure(state="normal")
            for cfg in _SCRAPERS:
                w = self._scraper_w.get(cfg["key"], {})
                if w.get("btn_start") and not self._scraper[cfg["key"]]["running"]:
                    w["btn_start"].configure(state="normal")
                # Populate resume button label on first connect
                state_api = cfg.get("api_state")
                if state_api and w.get("btn_resume_last") and not prev:
                    def _init_resume(api=state_api, btn=w["btn_resume_last"]) -> None:
                        try:
                            s = _get(api)
                            last = (s or {}).get("last_completed_handle")
                            label = f"↺  Resume from {last}" if last else "↺  Resume"
                            btn_state = "normal" if last else "disabled"
                            self.after(0, lambda: btn.configure(text=label, state=btn_state))
                        except Exception:
                            pass
                    self._run_in_thread(_init_resume)
        else:
            if prev:
                self._queue_log(f"Lost connection to {API_BASE} — retrying…", "warning")
            self._lbl_conn.configure(text="● Offline", text_color="#e74c3c")
            self._btn_start.configure(state="disabled")
            self._btn_resume.configure(state="disabled")
            self._btn_stop.configure(state="disabled", fg_color="#5d1f1a", hover_color="#5d1f1a")
            for cfg in _SCRAPERS:
                w = self._scraper_w.get(cfg["key"], {})
                if w.get("btn_start"):
                    w["btn_start"].configure(state="disabled")
                if w.get("btn_stop"):
                    w["btn_stop"].configure(state="disabled", fg_color="#5d1f1a", hover_color="#5d1f1a")
                if w.get("btn_pause"):
                    w["btn_pause"].configure(state="disabled")
                if w.get("btn_resume_last"):
                    w["btn_resume_last"].configure(state="disabled")

    def _update_vpn(self, connected: bool, ip: str | None) -> None:
        prev = self._vpn_connected
        self._vpn_connected = connected
        self._vpn_ip = ip
        if connected:
            label = f"● VPN  {ip}" if ip else "● VPN"
            self._lbl_vpn.configure(text=label, text_color="#2ecc71")
            if not prev:
                self._queue_log(f"VPN connected — {ip}", "info")
        else:
            self._lbl_vpn.configure(text="● VPN off", text_color="#e74c3c")
            if prev:
                self._queue_log("VPN disconnected", "warning")

    def _set_buttons_busy(self) -> None:
        self._btn_start.configure(state="disabled")
        self._btn_resume.configure(state="disabled")

    # ── Refresh scraper tab (per-tab state update) ────────────────────────────

    def _refresh_scraper_tab(self, key: str, job: dict, evts: list[dict]) -> None:
        w = self._scraper_w.get(key, {})
        if not w:
            return

        state = job.get("current_state", "unknown")
        step  = job.get("current_step", "") or ""
        done  = int(job.get("records_written", 0) or 0)
        total = int(job.get("records_found",  0) or 0)
        err   = job.get("error_message") or ""

        color = _state_color(state)
        if w.get("lbl_badge"):
            badge_text = state.upper()
            if total > 0:
                badge_text += f"  {done}/{total}"
            w["lbl_badge"].configure(text=badge_text, text_color=color)

        if w.get("progress"):
            if state in _TERMINAL:
                w["progress"].set(1.0 if state in ("completed", "done") else 0)
            elif total > 0:
                w["progress"].set(done / total)
            else:
                w["progress"].set(0)

        if w.get("lbl_step"):
            display = step or (err[:80] if err else "")
            w["lbl_step"].configure(
                text=display,
                text_color="#e74c3c" if err and state in _TERMINAL else "#7f8c8d",
            )

        # Login hint: show while waiting for authentication, hide once scraping
        hint = w.get("login_hint")
        if hint:
            waiting = state in _ACTIVE and (
                "login" in step.lower()
                or "launched_browser" in step.lower()
                or "browser" in step.lower()
                or "waiting" in step.lower()
            )
            if waiting:
                hint.grid(row=2, column=0, sticky="ew", pady=(0, 4))
            else:
                hint.grid_remove()

        # Stop / Pause buttons: enabled while active
        is_active = state in _ACTIVE or state == "paused"
        if w.get("btn_stop"):
            w["btn_stop"].configure(
                state="normal" if is_active else "disabled",
                fg_color="#c0392b" if is_active else "#5d1f1a",
                hover_color="#922b21" if is_active else "#5d1f1a",
            )
        if w.get("btn_pause"):
            w["btn_pause"].configure(state="normal" if is_active else "disabled")
            # Sync pause button label with actual paused state
            if state == "paused" and not self._scraper[key].get("paused"):
                self._scraper[key]["paused"] = True
                w["btn_pause"].configure(text="▶  Resume", fg_color="#27ae60", hover_color="#1e8449")
            elif state != "paused" and self._scraper[key].get("paused"):
                self._scraper[key]["paused"] = False
                w["btn_pause"].configure(text="⏸  Pause", fg_color="#8e44ad", hover_color="#6c3483")
        if w.get("btn_resume_last"):
            w["btn_resume_last"].configure(state="disabled" if is_active else "normal")

        # Re-enable Start button when terminal; refresh Resume button label from state
        if state in _TERMINAL:
            self._scraper[key]["running"] = False
            self._scraper[key]["paused"] = False
            if w.get("btn_start"):
                w["btn_start"].configure(state="normal", text="▶  Scrape")
            if w.get("btn_pause"):
                w["btn_pause"].configure(
                    state="disabled", text="⏸  Pause",
                    fg_color="#8e44ad", hover_color="#6c3483",
                )
            if hint:
                hint.grid_remove()
            # Update resume button with last completed handle
            if w.get("btn_resume_last"):
                cfg_key = next((c for c in _SCRAPERS if c["key"] == key), {})
                state_api = cfg_key.get("api_state")
                if state_api and self._connected:
                    def _fetch_resume_label(k=key, api=state_api, btn=w["btn_resume_last"]) -> None:
                        try:
                            s = _get(api)
                            last = (s or {}).get("last_completed_handle")
                            label = f"↺  Resume from {last}" if last else "↺  Resume"
                            btn_state = "normal" if last else "disabled"
                            self.after(0, lambda: btn.configure(text=label, state=btn_state))
                        except Exception:
                            pass
                    self._run_in_thread(_fetch_resume_label)

        # Append new events (deduplicated by id)
        s = self._scraper[key]
        for ev in evts:
            ev_id = ev.get("id")
            if ev_id not in s["event_ids"]:
                s["event_ids"].add(ev_id)
                ts  = _short_ts(ev.get("ts_utc"))
                msg = ev.get("message", "")
                lvl = ev.get("level", "info")
                self._scraper_append_event(key, f"{ts}  {msg}", lvl)

    def _scraper_append_event(self, key: str, msg: str, level: str = "info") -> None:
        w   = self._scraper_w.get(key, {})
        txt = w.get("events")
        if not txt:
            return
        tag = level if level in ("error", "warning", "info") else "info"
        txt.configure(state="normal")
        txt.insert("end", msg + "\n", tag)
        txt.see("end")
        txt.configure(state="disabled")

    def _clear_scraper_events(self, key: str) -> None:
        w   = self._scraper_w.get(key, {})
        txt = w.get("events")
        if txt:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.configure(state="disabled")
        self._scraper[key]["event_ids"].clear()

    # ── Ticket scraper tab UI refresh ─────────────────────────────────────────

    def _refresh_monitor_tab(self, job: dict, evts: list[dict]) -> None:
        state = job.get("current_state", "unknown")
        step  = job.get("current_step", "") or ""
        done  = int(job.get("records_written", 0) or 0)
        total = int(job.get("records_found",  0) or 0)
        jid   = job.get("job_id", "")
        err   = job.get("error_message") or ""

        self._lbl_job_badge.configure(text=state.upper(), text_color=_state_color(state))
        self._lbl_job_id.configure(text=jid[:28] + ("…" if len(jid) > 28 else ""))
        self._lbl_status.configure(text=state.upper(), text_color=_state_color(state))

        pct = done / total if total > 0 else 0
        self._progress.set(pct)
        self._lbl_progress.configure(text=f"{done} / {total} handles  ({int(pct * 100)}%)")
        self._lbl_step.configure(text=step)

        waiting_login = state in _ACTIVE and (
            "login" in step.lower() or "launched_browser" in step.lower()
            or "browser" in step.lower() or done == 0
        )
        if waiting_login:
            self._login_hint.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        else:
            self._login_hint.grid_remove()

        self._stat_widgets["started_at"].configure(
            text=_short_ts(job.get("started_at")) or "—"
        )
        self._stat_widgets["completed_at"].configure(
            text=_short_ts(job.get("completed_at")) or "—"
        )
        self._stat_widgets["error_message"].configure(
            text=(err[:60] + "…" if len(err) > 60 else err) or "—",
            text_color="#e74c3c" if err else "#ecf0f1",
        )

        if state in _ACTIVE or state == "paused":
            self._btn_stop.configure(state="normal", fg_color="#c0392b", hover_color="#922b21")
            self._btn_pause.configure(state="normal")
        else:
            self._btn_stop.configure(state="disabled", fg_color="#5d1f1a", hover_color="#5d1f1a")
            self._btn_pause.configure(state="disabled")
            if state not in _ACTIVE and self._job_paused:
                self._job_paused = False
                self._btn_pause.configure(text="⏸  Pause", fg_color="#8e44ad", hover_color="#6c3483")

        if self._connected:
            self._btn_start.configure(state="normal")
            self._btn_resume.configure(state="normal")

        for ev in evts:
            ev_id = ev.get("id")
            if ev_id not in self._event_ids:
                self._event_ids.add(ev_id)
                ts  = _short_ts(ev.get("ts_utc"))
                msg = ev.get("message", "")
                lvl = ev.get("level", "info")
                self._append_event_log(f"{ts}  {msg}", lvl)

    def _refresh_history(self, jobs: list[dict]) -> None:
        self._tree.delete(*self._tree.get_children())
        for j in jobs:
            jid   = (j.get("job_id") or "")[:8]
            state = j.get("current_state") or "unknown"
            done  = j.get("records_written", 0) or 0
            total = j.get("records_found",  0) or 0
            step  = (j.get("current_step") or "")[:30]
            start = _short_ts(j.get("started_at"))
            end   = _short_ts(j.get("completed_at"))
            prog  = f"{done}/{total}" if total else "—"
            self._tree.insert("", "end", values=(jid, state, prog, step, start, end))

    def _append_event_log(self, msg: str, level: str = "info") -> None:
        tag = level if level in ("error", "warning", "info") else "info"
        self._events_text.configure(state="normal")
        self._events_text.insert("end", msg + "\n", tag)
        self._events_text.see("end")
        self._events_text.configure(state="disabled")

    def _load_event_log(self, evts: list[dict]) -> None:
        self._events_text.configure(state="normal")
        self._events_text.delete("1.0", "end")
        self._event_ids.clear()
        for ev in evts:
            ev_id = ev.get("id")
            self._event_ids.add(ev_id)
            ts  = _short_ts(ev.get("ts_utc"))
            msg = ev.get("message", "")
            lvl = ev.get("level", "info")
            tag = lvl if lvl in ("error", "warning", "info") else "info"
            self._events_text.insert("end", f"{ts}  {msg}\n", tag)
        self._events_text.see("end")
        self._events_text.configure(state="disabled")

    def _clear_events(self) -> None:
        self._events_text.configure(state="normal")
        self._events_text.delete("1.0", "end")
        self._events_text.configure(state="disabled")
        self._event_ids.clear()


    # ── Diagnostics tab ───────────────────────────────────────────────────────

    def _build_diagnostics_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        sub = ctk.CTkTabview(tab)
        sub.grid(row=0, column=0, sticky="nsew")

        self._build_deploy_sub_tab(sub.add("Deploy Tools"))
        self._build_rrun_sub_tab(sub.add("Remote Run"))
        self._build_sdiag_sub_tab(sub.add("Server Diagnostics"))

    # ── Deploy Tools sub-tab ─────────────────────────────────────────────────

    def _build_deploy_sub_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        w = self._deploy_w

        # ── Form ─────────────────────────────────────────────────────────────
        form = ctk.CTkFrame(tab, corner_radius=8)
        form.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Row 0: action / workers / credentials
        ctk.CTkLabel(form, text="Action:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, padx=(12, 4), pady=10, sticky="w"
        )
        w["action_var"] = tk.StringVar(value="Clean Deploy (uninstall + install)")
        ctk.CTkOptionMenu(
            form, variable=w["action_var"],
            values=[lbl for _, lbl in _DEPLOY_ACTIONS],
            width=260, height=34,
            command=self._on_deploy_action_changed,
        ).grid(row=0, column=1, padx=(0, 12), pady=10, sticky="w")

        ctk.CTkLabel(form, text="Workers:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=2, padx=(12, 4), pady=10, sticky="w"
        )
        w["workers_var"] = tk.StringVar(value="1")
        ctk.CTkEntry(form, textvariable=w["workers_var"], width=48, height=34).grid(
            row=0, column=3, padx=(0, 12), pady=10
        )

        ctk.CTkLabel(form, text="SSH User:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=4, padx=(12, 4), pady=10, sticky="w"
        )
        w["username_entry"] = ctk.CTkEntry(form, width=100, height=34)
        w["username_entry"].insert(0, "123net")
        w["username_entry"].grid(row=0, column=5, padx=(0, 12), pady=10)

        ctk.CTkLabel(form, text="SSH Pass:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=6, padx=(12, 4), pady=10, sticky="w"
        )
        w["password_entry"] = ctk.CTkEntry(form, show="●", width=120, height=34)
        w["password_entry"].grid(row=0, column=7, padx=(0, 12), pady=10)

        ctk.CTkLabel(form, text="Root Pass:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=8, padx=(12, 4), pady=10, sticky="w"
        )
        w["root_password_entry"] = ctk.CTkEntry(form, show="●", width=120, height=34)
        w["root_password_entry"].insert(0, "sdxczvsdxczv")
        w["root_password_entry"].grid(row=0, column=9, padx=(0, 16), pady=10)

        # Row 1: embedded VPBX site picker (VPBX mode) or servers textbox (manual mode)
        w["servers_label"] = ctk.CTkLabel(form, text="Sites:", font=ctk.CTkFont(size=12))
        w["servers_label"].grid(row=1, column=0, padx=(12, 4), pady=(0, 10), sticky="nw")

        form.grid_columnconfigure(1, weight=1)
        w["vpbx_mode_manual"] = False

        # ── Embedded VPBX site picker ─────────────────────────────────────────
        _pbg = "#0f172a"
        picker_frm = tk.Frame(form, bg=_pbg, highlightbackground="#1e293b", highlightthickness=1)
        picker_frm.grid(row=1, column=1, columnspan=5, padx=(0, 12), pady=(0, 10), sticky="ew")
        w["picker_frm"] = picker_frm

        filter_row = tk.Frame(picker_frm, bg=_pbg)
        filter_row.pack(fill="x", padx=4, pady=(4, 2))

        w["vpbx_status_var"] = tk.StringVar(value="All")
        w["vpbx_status_cb"] = ttk.Combobox(
            filter_row, textvariable=w["vpbx_status_var"],
            values=["All", "production_billed", "testing", "decomissioned", "provisioning"],
            width=18, state="readonly",
        )
        w["vpbx_status_cb"].pack(side="left", padx=(0, 6))

        tk.Label(filter_row, text="Search:", bg=_pbg, fg="#94a3b8",
                 font=("Segoe UI", 9)).pack(side="left")
        w["vpbx_search_var"] = tk.StringVar()
        tk.Entry(
            filter_row, textvariable=w["vpbx_search_var"], width=18,
            bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0",
            relief="flat", font=("Segoe UI", 9),
        ).pack(side="left", padx=(3, 8))

        w["vpbx_count_lbl"] = tk.Label(filter_row, text="loading…",
                                        bg=_pbg, fg="#64748b", font=("Segoe UI", 9))
        w["vpbx_count_lbl"].pack(side="left")

        tk.Button(
            filter_row, text="↻ Refresh", bg="#1e3a5f", fg="#93c5fd",
            relief="flat", font=("Segoe UI", 8), padx=6,
            command=self._on_deploy_vpbx_refresh,
        ).pack(side="right")

        w["btn_scrape_creds_deploy"] = tk.Button(
            filter_row, text="🔑 Scrape Passwords", bg="#1a3a1a", fg="#4ade80",
            relief="flat", font=("Segoe UI", 8), padx=6,
            command=self._on_deploy_scrape_creds,
        )
        w["btn_scrape_creds_deploy"].pack(side="right", padx=(0, 4))

        lb_frm = tk.Frame(picker_frm, bg="#0d1117")
        lb_frm.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        vsb_p = ttk.Scrollbar(lb_frm, orient="vertical")
        vsb_p.pack(side="right", fill="y")
        w["vpbx_listbox"] = tk.Listbox(
            lb_frm, selectmode="extended",
            bg="#0d1117", fg="#e2e8f0", font=("Courier New", 9),
            selectbackground="#1d4ed8", selectforeground="#ffffff",
            yscrollcommand=vsb_p.set, activestyle="none",
            bd=0, highlightthickness=0, height=4,
        )
        vsb_p.config(command=w["vpbx_listbox"].yview)
        w["vpbx_listbox"].pack(side="left", fill="both", expand=True)

        w["vpbx_records"] = []
        w["vpbx_filtered"] = []

        w["vpbx_status_cb"].bind("<<ComboboxSelected>>", lambda _: self._vpbx_picker_refresh())
        w["vpbx_search_var"].trace_add("write", lambda *_: self._vpbx_picker_refresh())
        w["vpbx_listbox"].bind("<<ListboxSelect>>", self._on_vpbx_listbox_select)

        # Manual fallback textbox (hidden by default, shown when user toggles)
        w["servers_text"] = ctk.CTkTextbox(form, height=56, corner_radius=6)

        w["bundle_label"] = ctk.CTkLabel(form, text="Bundle name:", font=ctk.CTkFont(size=12))
        w["bundle_entry"] = ctk.CTkEntry(form, width=280, height=34)
        w["bundle_entry"].insert(0, "freepbx-tools-bundle.zip")

        # Server count label
        w["lbl_server_count"] = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["lbl_server_count"].grid(row=1, column=6, columnspan=4, padx=(4, 0), pady=(0, 4), sticky="w")

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=2, column=6, columnspan=4, padx=(0, 16), pady=(0, 10), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        w["btn_start"] = ctk.CTkButton(
            btn_row, text="▶  Deploy",
            fg_color="#27ae60", hover_color="#1e8449",
            height=34, font=ctk.CTkFont(size=13),
            command=self._on_deploy_start,
        )
        w["btn_start"].grid(row=0, column=0, padx=(0, 4), pady=(0, 4), sticky="ew")

        w["btn_cancel"] = ctk.CTkButton(
            btn_row, text="■  Cancel",
            fg_color="#c0392b", hover_color="#922b21",
            height=34, font=ctk.CTkFont(size=13),
            state="disabled",
            command=self._on_deploy_cancel,
        )
        w["btn_cancel"].grid(row=0, column=1, padx=(4, 0), pady=(0, 4), sticky="ew")

        w["btn_manual"] = ctk.CTkButton(
            btn_row, text="⌨  Manual IPs",
            fg_color="#374151", hover_color="#4b5563",
            height=30, font=ctk.CTkFont(size=12),
            command=self._on_deploy_toggle_manual,
        )
        w["btn_manual"].grid(row=1, column=0, padx=(0, 4), pady=(0, 4), sticky="ew")

        w["btn_paste"] = ctk.CTkButton(
            btn_row, text="📋  Paste IPs",
            fg_color="#2c3e50", hover_color="#1a252f",
            height=30, font=ctk.CTkFont(size=12),
            command=self._on_deploy_paste_servers,
        )
        w["btn_paste"].grid(row=1, column=1, padx=(4, 0), pady=(0, 4), sticky="ew")

        w["btn_browse"] = ctk.CTkButton(
            btn_row, text="📂  Browse CSV / TXT",
            fg_color="#6c3483", hover_color="#5b2c6f",
            height=30, font=ctk.CTkFont(size=12),
            command=self._on_deploy_browse_csv,
        )
        w["btn_browse"].grid(row=2, column=0, columnspan=2, pady=(0, 4), sticky="ew")

        # Row 3: Deploy backend connection — auto tries direct then SSH tunnel
        ctk.CTkLabel(form, text="Deploy Server:", font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, padx=(12, 4), pady=(4, 8), sticky="w"
        )
        _tunnel_ip_default = os.getenv("DEPLOY_SERVER_IP", "") or (
            _DEPLOY_HOST if _DEPLOY_HOST != "localhost" else ""
        )
        w["tunnel_ip_entry"] = ctk.CTkEntry(form, width=150, height=32)
        w["tunnel_ip_entry"].insert(0, _tunnel_ip_default)
        w["tunnel_ip_entry"].grid(row=3, column=1, padx=(0, 8), pady=(4, 8), sticky="w")

        ctk.CTkLabel(form, text="SSH User:", font=ctk.CTkFont(size=12)).grid(
            row=3, column=2, padx=(4, 4), pady=(4, 8), sticky="w"
        )
        w["tunnel_user_entry"] = ctk.CTkEntry(form, width=80, height=32)
        w["tunnel_user_entry"].insert(0, os.getenv("DEPLOY_SSH_USER", "tim2"))
        w["tunnel_user_entry"].grid(row=3, column=3, padx=(0, 12), pady=(4, 8), sticky="w")

        w["tunnel_dot"] = ctk.CTkLabel(
            form, text="●", font=ctk.CTkFont(size=16), text_color="#e74c3c", width=20,
        )
        w["tunnel_dot"].grid(row=3, column=4, padx=(4, 2), pady=(4, 8))

        w["tunnel_status_lbl"] = ctk.CTkLabel(
            form, text="Connecting…", font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["tunnel_status_lbl"].grid(row=3, column=5, padx=(0, 12), pady=(4, 8), sticky="w")

        w["btn_tunnel"] = ctk.CTkButton(
            form, text="↻ Reconnect",
            fg_color="#374151", hover_color="#4b5563",
            height=30, font=ctk.CTkFont(size=12), width=120,
            command=self._on_deploy_force_reconnect,
        )
        w["btn_tunnel"].grid(row=3, column=6, columnspan=2, padx=(0, 12), pady=(4, 8), sticky="w")

        w["lbl_status"] = ctk.CTkLabel(
            form, text="Deploy backend: checking…",
            font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["lbl_status"].grid(row=4, column=0, columnspan=10, padx=12, pady=(0, 8), sticky="w")

        # ── Split: job list (left) + output (right) ───────────────────────────
        split = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        split.grid(row=2, column=0, sticky="nsew")
        split.grid_columnconfigure(1, weight=1)
        split.grid_rowconfigure(0, weight=1)

        # Recent jobs
        jobs_frame = ctk.CTkFrame(split, corner_radius=8, width=230)
        jobs_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        jobs_frame.grid_rowconfigure(1, weight=1)
        jobs_frame.grid_propagate(False)

        ctk.CTkLabel(
            jobs_frame, text="Recent Jobs",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")

        w["jobs_list"] = tk.Listbox(
            jobs_frame,
            bg="#1a1a2e", fg="#ecf0f1",
            font=("Consolas", 9),
            selectbackground="#2980b9",
            relief="flat", borderwidth=0,
            activestyle="none",
        )
        w["jobs_list"].grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        jobs_frame.grid_columnconfigure(0, weight=1)
        w["jobs_list"].bind("<<ListboxSelect>>", self._on_deploy_job_select)

        # Live output
        out_frame = ctk.CTkFrame(split, corner_radius=8)
        out_frame.grid(row=0, column=1, sticky="nsew")
        out_frame.grid_rowconfigure(0, weight=1)
        out_frame.grid_columnconfigure(0, weight=1)

        w["output"] = tk.Text(
            out_frame,
            bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 10),
            state="disabled", relief="flat", wrap="none",
            padx=8, pady=8,
        )
        w["output"].grid(row=0, column=0, sticky="nsew")

        xsb = ctk.CTkScrollbar(out_frame, orientation="horizontal", command=w["output"].xview)
        xsb.grid(row=1, column=0, sticky="ew")
        ysb = ctk.CTkScrollbar(out_frame, command=w["output"].yview)
        ysb.grid(row=0, column=1, sticky="ns")
        w["output"].configure(xscrollcommand=xsb.set, yscrollcommand=ysb.set)

        for tag, color in [
            ("ok",      "#2ecc71"),
            ("error",   "#e74c3c"),
            ("warning", "#f39c12"),
            ("info",    "#c9d1d9"),
        ]:
            w["output"].tag_configure(tag, foreground=color)

        ctk.CTkButton(
            tab, text="Clear Output", width=100, height=28,
            fg_color="#7f8c8d", hover_color="#626567",
            command=lambda: self._clear_text_widget(w.get("output")),
        ).grid(row=3, column=0, sticky="e", pady=(4, 0))

        # Auto-load VPBX site list on tab build
        self._run_in_thread(self._do_vpbx_fetch_for_picker)

    # ── Deploy backend auto-connect (Option A: direct, Option B: SSH tunnel) ─────

    def _on_deploy_force_reconnect(self) -> None:
        w = self._deploy_w
        if w.get("tunnel_status_lbl"):
            w["tunnel_status_lbl"].configure(text="Reconnecting…", text_color="#f59e0b")
        if w.get("tunnel_dot"):
            w["tunnel_dot"].configure(text_color="#f59e0b")
        threading.Thread(target=self._deploy_auto_connect, daemon=True,
                         name="deploy-reconnect").start()

    def _check_deploy_url(self, url: str) -> bool:
        try:
            r = requests.get(f"{url}/api/jobs", timeout=3)
            return r.status_code < 500
        except Exception:
            return False

    def _start_ssh_tunnel(self, ip: str, user: str) -> None:
        self._kill_ssh_tunnel()
        target = f"{user}@{ip}" if user else ip
        try:
            proc = subprocess.Popen(
                ["ssh",
                 "-o", "StrictHostKeyChecking=no",
                 "-o", "BatchMode=yes",
                 "-o", "PasswordAuthentication=no",
                 "-o", "ServerAliveInterval=15",
                 "-o", "ExitOnForwardFailure=yes",
                 "-L", f"{_DEPLOY_PORT}:127.0.0.1:{_DEPLOY_PORT}",
                 target, "-N"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._ssh_tunnel_proc = proc
            time.sleep(2)
            if proc.poll() is not None:
                self._ssh_tunnel_proc = None
                self._ssh_tunnel_alive = False
                return
            self._ssh_tunnel_alive = True
            threading.Thread(target=self._monitor_ssh_tunnel, args=(proc,),
                             daemon=True, name="ssh-tunnel-mon").start()
        except Exception:
            self._ssh_tunnel_proc = None
            self._ssh_tunnel_alive = False

    def _monitor_ssh_tunnel(self, proc: subprocess.Popen) -> None:
        proc.wait()
        if self._closing:
            return
        self._ssh_tunnel_alive = False
        self._ssh_tunnel_proc = None
        # Tunnel died — trigger auto-reconnect
        threading.Thread(target=self._deploy_auto_connect, daemon=True,
                         name="deploy-reconnect").start()

    def _deploy_auto_connect(self) -> None:
        """Try Option A (direct), then Option B (SSH tunnel). Updates active URL and UI."""
        # Option A: direct connection
        if self._check_deploy_url(_DEPLOY_DIRECT_URL):
            _deploy_active_url[0] = _DEPLOY_DIRECT_URL
            self._deploy_conn_method = "direct"
            self.after(0, self._update_deploy_conn_ui)
            return

        # Option B: tunnel already alive
        if self._ssh_tunnel_alive and self._check_deploy_url(_DEPLOY_TUNNEL_URL):
            _deploy_active_url[0] = _DEPLOY_TUNNEL_URL
            self._deploy_conn_method = "tunnel"
            self.after(0, self._update_deploy_conn_ui)
            return

        # Option B: start tunnel then check
        w = self._deploy_w
        ip = (w.get("tunnel_ip_entry") and w["tunnel_ip_entry"].get().strip()) or ""
        user = (w.get("tunnel_user_entry") and w["tunnel_user_entry"].get().strip()) or ""
        if ip:
            self._start_ssh_tunnel(ip, user)
            if self._ssh_tunnel_alive and self._check_deploy_url(_DEPLOY_TUNNEL_URL):
                _deploy_active_url[0] = _DEPLOY_TUNNEL_URL
                self._deploy_conn_method = "tunnel"
                self.after(0, self._update_deploy_conn_ui)
                return

        # Both failed
        _deploy_active_url[0] = _DEPLOY_DIRECT_URL
        self._deploy_conn_method = ""
        self.after(0, self._update_deploy_conn_ui)

    def _update_deploy_conn_ui(self) -> None:
        w = self._deploy_w
        method = self._deploy_conn_method
        self._deploy_backend_ok = bool(method)
        if method == "direct":
            dot_color, conn_txt = "#2ecc71", f"● Direct  ({_DEPLOY_HOST}:{_DEPLOY_PORT})"
            status_txt, status_color = (
                f"Deploy backend ready — direct ({_DEPLOY_HOST}:{_DEPLOY_PORT})", "#2ecc71"
            )
        elif method == "tunnel":
            dot_color, conn_txt = "#3498db", f"● Tunnel  (SSH → port {_DEPLOY_PORT})"
            status_txt, status_color = "Deploy backend ready — SSH tunnel", "#3498db"
        else:
            dot_color, conn_txt = "#e74c3c", "○ Offline — retrying…"
            status_txt, status_color = "Deploy backend offline — retrying…", "#e74c3c"
        if w.get("tunnel_dot"):
            w["tunnel_dot"].configure(text_color=dot_color)
        if w.get("tunnel_status_lbl"):
            w["tunnel_status_lbl"].configure(text=conn_txt, text_color=dot_color)
        if w.get("lbl_status") and not (
            self._deploy_active_job and
            self._deploy_active_job.get("status") in ("queued", "running")
        ):
            w["lbl_status"].configure(text=status_txt, text_color=status_color)

    def _on_deploy_action_changed(self, label: str) -> None:
        w = self._deploy_w
        is_bundle = (label == "Build offline bundle (.zip)")
        if is_bundle:
            w["servers_label"].grid_remove()
            try: w["picker_frm"].grid_remove()
            except Exception: pass
            try: w["servers_text"].grid_remove()
            except Exception: pass
            w["bundle_label"].grid(row=1, column=0, padx=(12, 4), pady=(0, 10), sticky="w")
            w["bundle_entry"].grid(row=1, column=1, columnspan=3, padx=(0, 12), pady=(0, 10))
        else:
            try: w["bundle_label"].grid_remove()
            except Exception: pass
            try: w["bundle_entry"].grid_remove()
            except Exception: pass
            w["servers_label"].grid(row=1, column=0, padx=(12, 4), pady=(0, 10), sticky="nw")
            if w.get("vpbx_mode_manual"):
                w["servers_text"].grid(row=1, column=1, columnspan=5, padx=(0, 12), pady=(0, 10), sticky="ew")
            else:
                w["picker_frm"].grid(row=1, column=1, columnspan=5, padx=(0, 12), pady=(0, 10), sticky="ew")

    def _on_deploy_start(self) -> None:
        w = self._deploy_w
        action_label = w["action_var"].get()
        action = next((a for a, l in _DEPLOY_ACTIONS if l == action_label), "deploy")
        is_bundle = (action == "bundle")

        workers_str = w["workers_var"].get().strip()
        workers = int(workers_str) if workers_str.isdigit() and int(workers_str) > 0 else 1
        bundle_name = w["bundle_entry"].get().strip() if is_bundle else "freepbx-tools-bundle.zip"

        # Multi-credential CSV deploy: fire one job per credential group
        groups = w.get("csv_server_groups")
        if groups and w.get("vpbx_mode_manual") and not is_bundle:
            w["csv_server_groups"] = None
            for g in groups:
                self._run_in_thread(
                    self._do_deploy_start,
                    action=action,
                    servers="\n".join(g["ips"]),
                    workers=min(len(g["ips"]), workers),
                    username=g["username"],
                    password=g["password"],
                    root_password=g["root_password"],
                    bundle_name=bundle_name,
                )
            return

        if is_bundle:
            servers = ""
        elif w.get("vpbx_mode_manual"):
            servers = w["servers_text"].get("1.0", "end").strip()
        else:
            sel = w["vpbx_listbox"].curselection()
            if not sel:
                messagebox.showwarning("No Sites Selected",
                    "Select at least one site from the list, or click ⌨ Manual IPs to enter IPs directly.")
                return
            recs = [w["vpbx_filtered"][i] for i in sel]
            form_pass = w["password_entry"].get()
            root_password = w["root_password_entry"].get()
            username = w["username_entry"].get().strip() or "123net"
            # Group by ftp_pass; fall back to form password for sites without stored credentials
            groups_by_pass: dict[str, list[str]] = {}
            for rec in recs:
                ip = rec.get("ip") or ""
                if not ip:
                    continue
                key = (rec.get("ftp_pass") or "").strip() or form_pass
                groups_by_pass.setdefault(key, []).append(ip)
            if not any(groups_by_pass.values()):
                messagebox.showwarning("No IPs", "Selected sites have no IP addresses.")
                return
            for pass_key, ips in groups_by_pass.items():
                self._run_in_thread(
                    self._do_deploy_start,
                    action=action, servers="\n".join(ips),
                    workers=min(len(ips), workers),
                    username=username, password=pass_key,
                    root_password=root_password, bundle_name=bundle_name,
                )
            return
        username = w["username_entry"].get().strip() or "123net"
        password = w["password_entry"].get()
        root_password = w["root_password_entry"].get()
        self._run_in_thread(
            self._do_deploy_start,
            action=action, servers=servers, workers=workers,
            username=username, password=password,
            root_password=root_password, bundle_name=bundle_name,
        )

    def _do_deploy_start(
        self, action: str, servers: str, workers: int,
        username: str, password: str, root_password: str, bundle_name: str,
    ) -> None:
        w = self._deploy_w
        self.after(0, lambda: w["btn_start"].configure(state="disabled", text="Running…"))
        self.after(0, lambda: w["btn_cancel"].configure(state="normal"))
        try:
            data = _deploy_post("/api/jobs", json={
                "action": action, "servers": servers, "workers": workers,
                "username": username, "password": password,
                "root_password": root_password, "bundle_name": bundle_name,
            })
            self._deploy_active_job = data
            jid = data.get("id", "")
            self._deploy_append_output(f"Job started: {jid[:8]}\n", "info")
            self.after(0, lambda: w["lbl_status"].configure(
                text=f"Job {jid[:8]}  —  running", text_color="#3498db",
            ))
        except requests.HTTPError as exc:
            self._deploy_append_output(f"[ERROR] {exc.response.text}\n", "error")
            self.after(0, lambda: w["btn_start"].configure(state="normal", text="▶  Deploy"))
            self.after(0, lambda: w["btn_cancel"].configure(state="disabled"))
        except Exception as exc:
            self._deploy_append_output(f"[ERROR] Deploy backend unreachable: {exc}\n", "error")
            self.after(0, lambda: w["btn_start"].configure(state="normal", text="▶  Deploy"))
            self.after(0, lambda: w["btn_cancel"].configure(state="disabled"))

    def _on_deploy_cancel(self) -> None:
        job = self._deploy_active_job
        if not job:
            return
        self._run_in_thread(self._do_deploy_cancel, job_id=job.get("id", ""))

    def _do_deploy_cancel(self, job_id: str) -> None:
        try:
            _deploy_post(f"/api/jobs/{job_id}/cancel")
            self._deploy_append_output("[CANCELLED] Cancel requested.\n", "warning")
        except Exception as exc:
            self._deploy_append_output(f"[ERROR] Cancel failed: {exc}\n", "error")

    def _update_deploy_server_count(self) -> None:
        w = self._deploy_w
        lbl = w.get("lbl_server_count")
        if not lbl:
            return
        if w.get("vpbx_mode_manual"):
            txt = w.get("servers_text")
            if not txt:
                return
            raw = txt.get("1.0", "end").strip()
            servers = [
                part.strip()
                for line in raw.replace(",", "\n").replace(";", "\n").splitlines()
                for part in line.split()
                if part.strip() and not part.strip().startswith("#")
            ]
            n = len(servers)
        else:
            lb = w.get("vpbx_listbox")
            n = len(lb.curselection()) if lb else 0
        if n == 0:
            lbl.configure(text="", text_color="#7f8c8d")
        else:
            lbl.configure(text=f"{n} server{'s' if n != 1 else ''}", text_color="#3498db")

    def _on_deploy_browse_csv(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select server list file",
            filetypes=[
                ("CSV / text files", "*.csv *.txt *.tsv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        w = self._deploy_w
        # Build handle→IP lookup from already-loaded VPBX records
        handle_map: dict[str, str] = {
            (r.get("handle") or "").upper(): (r.get("ip") or "")
            for r in w.get("vpbx_records", []) if r.get("ip")
        }

        # CSV format: handle_or_ip, username, password, root_user, root_password
        # Columns 2 and 4 (username, root_user) are accepted but never required — defaults: 123net / root
        rows: list[tuple[str, str, str, str]] = []  # (ip, username, password, root_password)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = [p.strip() for p in line.replace("\t", ",").split(",")]
                    raw = parts[0] if parts else ""
                    if not raw:
                        continue
                    # Resolve handle → IP if not already an IP address
                    if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', raw):
                        ip = raw
                    else:
                        ip = handle_map.get(raw.upper(), "")
                        if not ip:
                            continue  # unknown handle — skip
                    username     = parts[1] if len(parts) > 1 and parts[1] else "123net"
                    password     = parts[2] if len(parts) > 2 else ""
                    root_password = parts[4] if len(parts) > 4 else ""
                    rows.append((ip, username, password, root_password))
        except Exception as exc:
            messagebox.showerror("Read Error", f"Could not read file:\n{exc}")
            return

        if not rows:
            messagebox.showwarning(
                "Empty File",
                "No servers resolved.\n\n"
                "Column 1 must be an IP address or a known VPBX handle.\n"
                "Make sure the VPBX data has loaded (↻ Refresh) if using handles.",
            )
            return

        # Group by credentials — each unique credential set becomes its own deploy job
        groups: dict[tuple[str, str, str], list[str]] = {}
        for ip, username, password, root_password in rows:
            key = (username, password, root_password)
            groups.setdefault(key, []).append(ip)

        w["csv_server_groups"] = [
            {"ips": ips, "username": uname, "password": pwd, "root_password": rpwd}
            for (uname, pwd, rpwd), ips in groups.items()
        ]

        all_ips = [ip for g in w["csv_server_groups"] for ip in g["ips"]]
        self._deploy_switch_to_manual_mode()
        w["servers_text"].delete("1.0", "end")
        w["servers_text"].insert("end", "\n".join(all_ips))
        self._update_deploy_server_count()
        w["workers_var"].set(str(min(len(all_ips), 10)))

        # Pre-fill credentials from the first group
        first = w["csv_server_groups"][0]
        w["username_entry"].delete(0, "end")
        w["username_entry"].insert(0, first["username"])
        w["password_entry"].delete(0, "end")
        w["password_entry"].insert(0, first["password"])
        w["root_password_entry"].delete(0, "end")
        w["root_password_entry"].insert(0, first["root_password"])

        fname = Path(path).name
        n_groups = len(w["csv_server_groups"])
        grp_note = f"  —  {n_groups} credential groups" if n_groups > 1 else ""
        if w.get("lbl_status"):
            w["lbl_status"].configure(
                text=f"Loaded {len(all_ips)} server{'s' if len(all_ips) != 1 else ''} from {fname}{grp_note}",
                text_color="#3498db",
            )

    def _on_deploy_paste_servers(self) -> None:
        try:
            clip = self.clipboard_get()
        except Exception:
            return
        if not clip.strip():
            return
        servers: list[str] = []
        for line in clip.replace(",", "\n").replace(";", "\n").splitlines():
            for part in line.split():
                p = part.strip()
                if p and not p.startswith("#"):
                    servers.append(p)
        if not servers:
            messagebox.showwarning("Nothing Found", "No IPs or hostnames found in clipboard.")
            return
        self._deploy_switch_to_manual_mode()
        w = self._deploy_w
        w["csv_server_groups"] = None
        w["servers_text"].delete("1.0", "end")
        w["servers_text"].insert("end", "\n".join(servers))
        self._update_deploy_server_count()
        if w.get("lbl_status"):
            n = len(servers)
            w["lbl_status"].configure(
                text=f"Pasted {n} server{'s' if n != 1 else ''} from clipboard",
                text_color="#3498db",
            )

    def _on_vpbx_listbox_select(self, _event=None) -> None:
        self._update_deploy_server_count()
        w = self._deploy_w
        lb = w.get("vpbx_listbox")
        if not lb:
            return
        sel = lb.curselection()
        n = len(sel)
        if n > 0:
            w["workers_var"].set(str(min(n, 10)))
            first = w["vpbx_filtered"][sel[0]]
            ftp_pass = (first.get("ftp_pass") or "").strip()
            if ftp_pass:
                self._deploy_vpbx_fill_password(ftp_pass)

    def _vpbx_picker_refresh(self) -> None:
        w = self._deploy_w
        lb = w.get("vpbx_listbox")
        if lb is None:
            return
        flt = w["vpbx_status_var"].get()
        q = w["vpbx_search_var"].get().lower()
        filtered = [
            r for r in w["vpbx_records"]
            if (flt == "All" or r.get("account_status") == flt)
            and (not q or q in (r.get("handle") or "").lower()
                        or q in (r.get("name") or "").lower()
                        or q in (r.get("ip") or "").lower())
        ]
        filtered.sort(key=lambda r: (r.get("name") or r.get("handle") or "").lower())
        w["vpbx_filtered"] = filtered
        lb.delete(0, "end")
        for r in filtered:
            h = (r.get("handle") or "").upper()
            ip = r.get("ip") or "—"
            name = (r.get("name") or "")[:32]
            lb.insert("end", f"{h:<5}  {ip:<17}  {name}")
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text=f"{len(filtered)} sites")
        self._update_deploy_server_count()

    def _on_deploy_vpbx_refresh(self) -> None:
        w = self._deploy_w
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text="loading…")
        self._run_in_thread(self._do_vpbx_fetch_for_picker)

    def _on_deploy_scrape_creds(self) -> None:
        w = self._deploy_w
        btn = w.get("btn_scrape_creds_deploy")
        if btn:
            btn.configure(state="disabled", text="Scraping…")
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text="opening browser…", fg="#f59e0b")
        self._run_in_thread(self._do_deploy_scrape_creds)

    def _do_deploy_scrape_creds(self) -> None:
        import time as _time
        try:
            r = requests.post(f"{API_BASE}/api/vpbx/credentials/refresh", json={}, timeout=10)
            r.raise_for_status()
            job_id = r.json().get("job_id", "")
        except Exception as exc:
            def _err(e=exc):
                w = self._deploy_w
                btn = w.get("btn_scrape_creds_deploy")
                if btn:
                    btn.configure(state="normal", text="🔑 Scrape Passwords")
                count_lbl = w.get("vpbx_count_lbl")
                if count_lbl:
                    count_lbl.config(text=f"error: {e}", fg="#f87171")
            self.after(0, _err)
            return

        while True:
            _time.sleep(2)
            try:
                r = requests.get(f"{API_BASE}/api/jobs/{job_id}", timeout=10)
                if not r.ok:
                    break
                row = r.json()
                status = row.get("status", "")
                completed = row.get("completed", 0)
                total = row.get("total", 0)

                if status in ("done", "succeeded"):
                    count = (row.get("result") or {}).get("credentials_count", "?")
                    def _done(n=count):
                        w = self._deploy_w
                        btn = w.get("btn_scrape_creds_deploy")
                        if btn:
                            btn.configure(state="normal", text="🔑 Scrape Passwords")
                        count_lbl = w.get("vpbx_count_lbl")
                        if count_lbl:
                            count_lbl.config(fg="#4ade80")
                        self._run_in_thread(self._do_vpbx_fetch_for_picker)
                    self.after(0, _done)
                    break
                elif status in ("error", "cancelled"):
                    def _fail(s=status):
                        w = self._deploy_w
                        btn = w.get("btn_scrape_creds_deploy")
                        if btn:
                            btn.configure(state="normal", text="🔑 Scrape Passwords")
                        count_lbl = w.get("vpbx_count_lbl")
                        if count_lbl:
                            count_lbl.config(text=s, fg="#f87171")
                    self.after(0, _fail)
                    break
                else:
                    def _prog(c=completed, t=total):
                        count_lbl = self._deploy_w.get("vpbx_count_lbl")
                        if count_lbl:
                            suffix = f"{c}/{t}" if t else str(c)
                            count_lbl.config(text=f"scraping {suffix}…", fg="#f59e0b")
                    self.after(0, _prog)
            except Exception:
                break

    def _do_vpbx_fetch_for_picker(self) -> None:
        try:
            r = requests.get(f"{API_BASE}/api/vpbx/records", timeout=10)
            r.raise_for_status()
            records = r.json().get("items", [])
            self.after(0, lambda recs=records: self._on_deploy_vpbx_loaded(recs))
        except Exception as exc:
            def _err(e=exc):
                w = self._deploy_w
                count_lbl = w.get("vpbx_count_lbl")
                if count_lbl:
                    count_lbl.config(text=f"offline")
            self.after(0, _err)

    def _on_deploy_vpbx_loaded(self, records: list[dict]) -> None:
        w = self._deploy_w
        w["vpbx_records"] = records
        statuses_seen = sorted({(r.get("account_status") or "") for r in records if r.get("account_status")})
        status_cb = w.get("vpbx_status_cb")
        if status_cb:
            status_cb.configure(values=["All"] + statuses_seen)
        self._vpbx_picker_refresh()

    def _on_deploy_toggle_manual(self) -> None:
        w = self._deploy_w
        if w.get("vpbx_mode_manual"):
            self._deploy_switch_to_vpbx_mode()
        else:
            self._deploy_switch_to_manual_mode()

    def _deploy_switch_to_manual_mode(self) -> None:
        w = self._deploy_w
        w["vpbx_mode_manual"] = True
        try: w["picker_frm"].grid_remove()
        except Exception: pass
        w["servers_text"].grid(row=1, column=1, columnspan=5, padx=(0, 12), pady=(0, 10), sticky="ew")
        w["servers_label"].configure(text="Servers:")
        btn = w.get("btn_manual")
        if btn:
            btn.configure(text="🗂  VPBX Sites", fg_color="#1a5276", hover_color="#154360")
        self._update_deploy_server_count()

    def _deploy_switch_to_vpbx_mode(self) -> None:
        w = self._deploy_w
        w["vpbx_mode_manual"] = False
        w["csv_server_groups"] = None
        try: w["servers_text"].grid_remove()
        except Exception: pass
        w["picker_frm"].grid(row=1, column=1, columnspan=5, padx=(0, 12), pady=(0, 10), sticky="ew")
        w["servers_label"].configure(text="Sites:")
        btn = w.get("btn_manual")
        if btn:
            btn.configure(text="⌨  Manual IPs", fg_color="#374151", hover_color="#4b5563")
        self._update_deploy_server_count()

    def _on_deploy_import_vpbx(self) -> None:
        w = self._deploy_w
        if w.get("lbl_status"):
            w["lbl_status"].configure(text="Fetching VPBX records…", text_color="#f39c12")
        self._run_in_thread(self._do_vpbx_fetch)

    def _do_vpbx_fetch(self) -> None:
        try:
            r = requests.get(f"{API_BASE}/api/vpbx/records", timeout=10)
            r.raise_for_status()
            records = r.json().get("items", [])
            self.after(0, lambda recs=records: self._open_vpbx_picker(recs))
        except Exception as exc:
            def _err(e=exc):
                w = self._deploy_w
                if w.get("lbl_status"):
                    w["lbl_status"].configure(
                        text=f"VPBX fetch failed: {e}", text_color="#e74c3c"
                    )
            self.after(0, _err)

    def _open_vpbx_picker(self, records: list[dict]) -> None:
        if not records:
            messagebox.showwarning("No Data", "No VPBX records found. Run the VPBX scraper first.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Import Servers from VPBX")
        dlg.geometry("900x580")
        dlg.configure(bg="#1a1a2e")
        dlg.resizable(True, True)
        dlg.grab_set()

        # ── Filter bar ────────────────────────────────────────────────────────
        filter_frm = tk.Frame(dlg, bg="#1a1a2e")
        filter_frm.pack(fill="x", padx=8, pady=(8, 2))

        tk.Label(filter_frm, text="Status:", bg="#1a1a2e", fg="#bdc3c7",
                 font=("Segoe UI", 10)).pack(side="left")
        all_statuses = sorted({(r.get("account_status") or "") for r in records
                                if r.get("account_status")})
        statuses = ["All"] + all_statuses
        default_status = "production_billed" if "production_billed" in statuses else "All"
        status_var = tk.StringVar(value=default_status)
        status_cb = ttk.Combobox(filter_frm, textvariable=status_var, values=statuses,
                                  width=22, state="readonly")
        status_cb.pack(side="left", padx=(4, 16))

        tk.Label(filter_frm, text="Search:", bg="#1a1a2e", fg="#bdc3c7",
                 font=("Segoe UI", 10)).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(filter_frm, textvariable=search_var, width=22,
                 bg="#2c2c3e", fg="#ecf0f1", insertbackground="#ecf0f1",
                 relief="flat").pack(side="left", padx=(4, 0))

        count_lbl = tk.Label(filter_frm, text="", bg="#1a1a2e", fg="#7f8c8d",
                              font=("Segoe UI", 10))
        count_lbl.pack(side="right")

        # ── Column header ─────────────────────────────────────────────────────
        tk.Label(dlg, text=f"  {'HDL':<5}  {'IP':<18}  {'Company':<38}  Status",
                 bg="#0d0d1a", fg="#7f8c8d", font=("Courier New", 10),
                 anchor="w", pady=2).pack(fill="x", padx=8)

        # ── Listbox ───────────────────────────────────────────────────────────
        list_frm = tk.Frame(dlg, bg="#0d0d1a")
        list_frm.pack(fill="both", expand=True, padx=8, pady=2)

        vsb = ttk.Scrollbar(list_frm, orient="vertical")
        vsb.pack(side="right", fill="y")
        listbox = tk.Listbox(
            list_frm, selectmode="extended",
            bg="#0d0d1a", fg="#ecf0f1", font=("Courier New", 10),
            selectbackground="#2980b9", selectforeground="#ffffff",
            yscrollcommand=vsb.set, activestyle="none",
            bd=0, highlightthickness=0,
        )
        vsb.config(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True)

        filtered_records: list[dict] = []

        def _refresh(*_) -> None:
            nonlocal filtered_records
            flt = status_var.get()
            q = search_var.get().lower()
            filtered_records = [
                r for r in records
                if (flt == "All" or r.get("account_status") == flt)
                and (not q or q in (r.get("handle") or "").lower()
                            or q in (r.get("name") or "").lower()
                            or q in (r.get("ip") or "").lower())
            ]
            listbox.delete(0, "end")
            for r in filtered_records:
                h = (r.get("handle") or "").upper()
                ip = r.get("ip") or ""
                name = (r.get("name") or "")[:38]
                st = r.get("account_status") or ""
                listbox.insert("end", f"  {h:<5}  {ip:<18}  {name:<38}  {st}")
            count_lbl.configure(text=f"{len(filtered_records)} sites")

        _refresh()
        status_cb.bind("<<ComboboxSelected>>", _refresh)
        search_var.trace_add("write", _refresh)

        # ── Select controls + password option ─────────────────────────────────
        ctrl_frm = tk.Frame(dlg, bg="#1a1a2e")
        ctrl_frm.pack(fill="x", padx=8, pady=4)

        tk.Button(ctrl_frm, text="Select All", bg="#27ae60", fg="white",
                  relief="flat", padx=8,
                  command=lambda: listbox.selection_set(0, "end")).pack(side="left", padx=(0, 4))
        tk.Button(ctrl_frm, text="Deselect All", bg="#7f8c8d", fg="white",
                  relief="flat", padx=8,
                  command=lambda: listbox.selection_clear(0, "end")).pack(side="left")

        pass_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            ctrl_frm, text="Auto-fill SSH password from site config",
            variable=pass_var, bg="#1a1a2e", fg="#ecf0f1",
            selectcolor="#2c3e50", activebackground="#1a1a2e",
            activeforeground="#ecf0f1",
        ).pack(side="right")

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_frm = tk.Frame(dlg, bg="#1a1a2e")
        btn_frm.pack(fill="x", padx=8, pady=(2, 8))

        def _do_import() -> None:
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("Nothing Selected", "Select at least one server.")
                return
            chosen = [filtered_records[i] for i in sel]
            ips = [r["ip"] for r in chosen if r.get("ip")]
            if not ips:
                messagebox.showwarning("No IPs", "Selected records have no IP addresses.")
                return
            w = self._deploy_w
            w["servers_text"].delete("1.0", "end")
            w["servers_text"].insert("end", "\n".join(ips))
            self._update_deploy_server_count()
            w["workers_var"].set(str(min(len(ips), 10)))
            if pass_var.get():
                first_handle = (chosen[0].get("handle") or "").upper()
                if first_handle:
                    self._run_in_thread(self._do_vpbx_fetch_password, handle=first_handle)
            if w.get("lbl_status"):
                n = len(ips)
                w["lbl_status"].configure(
                    text=f"Imported {n} server{'s' if n != 1 else ''} from VPBX  —  workers → {w['workers_var'].get()}",
                    text_color="#3498db",
                )
            dlg.destroy()

        tk.Button(btn_frm, text="▶  Import Selected", bg="#27ae60", fg="white",
                  font=("Segoe UI", 11, "bold"), relief="flat", padx=12, pady=4,
                  command=_do_import).pack(side="left")
        tk.Button(btn_frm, text="Cancel", bg="#2c3e50", fg="#ecf0f1",
                  relief="flat", padx=12, pady=4,
                  command=dlg.destroy).pack(side="right")

    def _do_vpbx_fetch_password(self, handle: str) -> None:
        """Look up ftp_pass from already-loaded VPBX records (= SSH password for 123net)."""
        w = self._deploy_w
        for rec in w.get("vpbx_records", []):
            if (rec.get("handle") or "").upper() == handle.upper():
                ftp_pass = (rec.get("ftp_pass") or "").strip()
                if ftp_pass:
                    self.after(0, lambda p=ftp_pass: self._deploy_vpbx_fill_password(p))
                return

    def _deploy_vpbx_fill_password(self, password: str) -> None:
        w = self._deploy_w
        entry = w.get("password_entry")
        if entry and password:
            entry.delete(0, "end")
            entry.insert(0, password)
            if w.get("lbl_status"):
                current = w["lbl_status"].cget("text")
                w["lbl_status"].configure(
                    text=current + "  ✓ SSH password auto-filled",
                    text_color="#2ecc71",
                )

    def _on_deploy_job_select(self, _event: Any) -> None:
        w = self._deploy_w
        sel = w["jobs_list"].curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._deploy_jobs):
            job = self._deploy_jobs[idx]
            self._deploy_active_job = job
            self._run_in_thread(self._do_deploy_load_job, job_id=job.get("id", ""))

    def _do_deploy_load_job(self, job_id: str) -> None:
        try:
            data = _deploy_get(f"/api/jobs/{job_id}")
            self._ui_queue.put(("deploy_job_update", data["job"], data["tail"]))
        except Exception as exc:
            self._deploy_append_output(f"[ERROR] Load job failed: {exc}\n", "error")

    def _deploy_append_output(self, text: str, level: str = "info") -> None:
        w = self._deploy_w
        txt = w.get("output")
        if not txt:
            return
        l = text.lower()
        tag = "ok"      if ("[ok]" in l or "successful" in l) else \
              "error"   if ("[error]" in l or "[failed]" in l) else \
              "warning" if ("[warning]" in l or "warning" in l) else \
              level if level in ("ok", "error", "warning") else "info"
        def _do() -> None:
            txt.configure(state="normal")
            txt.insert("end", text, tag)
            txt.see("end")
            txt.configure(state="disabled")
        self.after(0, _do)

    def _refresh_deploy_tab(self, job: dict, tail: list[str]) -> None:
        w = self._deploy_w
        if not w:
            return
        status = job.get("status", "unknown")
        jid    = job.get("id", "")
        color  = _deploy_state_color(status)
        if w.get("lbl_status"):
            w["lbl_status"].configure(
                text=f"Job {jid[:8]}  —  {status}", text_color=color,
            )
        txt = w.get("output")
        if txt:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            for line in tail:
                l = line.lower()
                tag = "ok"      if ("[ok]" in l or "successful" in l) else \
                      "error"   if ("[error]" in l or "[failed]" in l) else \
                      "warning" if ("[warning]" in l or "warning" in l) else "info"
                txt.insert("end", line, tag)
            txt.see("end")
            txt.configure(state="disabled")
        if status in ("succeeded", "failed", "cancelled"):
            if w.get("btn_start"):
                w["btn_start"].configure(state="normal", text="▶  Deploy")
            if w.get("btn_cancel"):
                w["btn_cancel"].configure(state="disabled")

    def _refresh_deploy_jobs_list(self, jobs: list[dict]) -> None:
        w = self._deploy_w
        lb = w.get("jobs_list")
        if not lb:
            return
        self._deploy_jobs = jobs
        lb.delete(0, "end")
        for j in jobs:
            status = j.get("status", "?")
            action = j.get("action", "?")
            jid    = j.get("id", "")[:8]
            servers = j.get("servers", [])
            srv  = servers[0] if servers else "–"
            icon = "✓" if status == "succeeded" else \
                   "✗" if status in ("failed", "cancelled") else "●"
            lb.insert("end", f"{icon} {jid}  {action[:11]:<11}  {srv}")
            color = "#2ecc71" if status == "succeeded" else \
                    "#e74c3c" if status == "failed"    else \
                    "#f39c12" if status in ("queued", "running") else "#95a5a6"
            lb.itemconfig("end", fg=color)

    # ── Remote Run sub-tab ───────────────────────────────────────────────────

    def _build_rrun_sub_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        w = self._rrun_w

        form = ctk.CTkFrame(tab, corner_radius=8)
        form.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        form.grid_columnconfigure(0, weight=1)

        # Row 0: VPBX site picker
        _pbg = "#0f172a"
        picker_frm = tk.Frame(form, bg=_pbg, highlightbackground="#1e293b", highlightthickness=1)
        picker_frm.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        filter_row = tk.Frame(picker_frm, bg=_pbg)
        filter_row.pack(fill="x", padx=4, pady=(4, 2))

        w["vpbx_status_var"] = tk.StringVar(value="All")
        w["vpbx_status_cb"] = ttk.Combobox(
            filter_row, textvariable=w["vpbx_status_var"],
            values=["All", "production_billed", "production", "provisioning", "testing"],
            width=18, state="readonly",
        )
        w["vpbx_status_cb"].pack(side="left", padx=(0, 6))

        tk.Label(filter_row, text="Search:", bg=_pbg, fg="#94a3b8",
                 font=("Segoe UI", 9)).pack(side="left")
        w["vpbx_search_var"] = tk.StringVar()
        tk.Entry(
            filter_row, textvariable=w["vpbx_search_var"], width=18,
            bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0",
            relief="flat", font=("Segoe UI", 9),
        ).pack(side="left", padx=(3, 8))

        w["vpbx_count_lbl"] = tk.Label(filter_row, text="loading…",
                                        bg=_pbg, fg="#64748b", font=("Segoe UI", 9))
        w["vpbx_count_lbl"].pack(side="left")

        tk.Button(
            filter_row, text="↻ Refresh", bg="#1e3a5f", fg="#93c5fd",
            relief="flat", font=("Segoe UI", 8), padx=6,
            command=self._on_rrun_vpbx_refresh,
        ).pack(side="right")

        lb_frm = tk.Frame(picker_frm, bg="#0d1117")
        lb_frm.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        vsb_p = ttk.Scrollbar(lb_frm, orient="vertical")
        vsb_p.pack(side="right", fill="y")
        w["vpbx_listbox"] = tk.Listbox(
            lb_frm, selectmode="single",
            bg="#0d1117", fg="#e2e8f0", font=("Courier New", 9),
            selectbackground="#1d4ed8", selectforeground="#ffffff",
            yscrollcommand=vsb_p.set, activestyle="none",
            bd=0, highlightthickness=0, height=4,
        )
        vsb_p.config(command=w["vpbx_listbox"].yview)
        w["vpbx_listbox"].pack(side="left", fill="both", expand=True)
        w["vpbx_records"] = []
        w["vpbx_filtered"] = []

        w["vpbx_status_cb"].bind("<<ComboboxSelected>>", lambda _: self._rrun_picker_refresh())
        w["vpbx_search_var"].trace_add("write", lambda *_: self._rrun_picker_refresh())
        w["vpbx_listbox"].bind("<<ListboxSelect>>", self._on_rrun_listbox_select)

        # Row 1: credential fields (auto-filled from picker)
        cred_row = ctk.CTkFrame(form, fg_color="transparent")
        cred_row.grid(row=1, column=0, padx=12, pady=(4, 4), sticky="ew")

        for lbl, key, kw in [
            ("Server:",    "server_entry",       {"width": 160, "placeholder_text": "← select above"}),
            ("User:",      "username_entry",      {"width": 90}),
            ("SSH Pass:",  "password_entry",      {"width": 120, "show": "●"}),
            ("Root Pass:", "root_password_entry", {"width": 120, "show": "●"}),
        ]:
            ctk.CTkLabel(cred_row, text=lbl, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
            ent = ctk.CTkEntry(cred_row, height=34, **kw)
            if key == "username_entry":
                ent.insert(0, "123net")
            elif key == "root_password_entry":
                ent.insert(0, "sdxczvsdxczv")
            ent.pack(side="left", padx=(0, 12))
            w[key] = ent

        # Row 2: menu choice + grab dump + buttons
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(btn_row, text="Menu Choice:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        w["menu_var"] = tk.StringVar(value=_REMOTE_RUN_MENU[0][1])
        ctk.CTkOptionMenu(
            btn_row, variable=w["menu_var"],
            values=[lbl for _, lbl in _REMOTE_RUN_MENU],
            width=280, height=34,
        ).pack(side="left", padx=(0, 12))

        w["grab_dump_var"] = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(btn_row, text="Grab dump JSON", variable=w["grab_dump_var"]).pack(side="left", padx=(0, 12))

        w["btn_run"] = ctk.CTkButton(
            btn_row, text="▶  Run",
            fg_color="#2980b9", hover_color="#1f6391",
            width=120, height=36, font=ctk.CTkFont(size=13),
            command=self._on_rrun_start,
        )
        w["btn_run"].pack(side="left", padx=(0, 8))

        w["btn_cancel"] = ctk.CTkButton(
            btn_row, text="■  Cancel",
            fg_color="#c0392b", hover_color="#922b21",
            width=110, height=36, font=ctk.CTkFont(size=13),
            state="disabled",
            command=self._on_rrun_cancel,
        )
        w["btn_cancel"].pack(side="left")

        w["lbl_status"] = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["lbl_status"].grid(row=3, column=0, padx=12, pady=(0, 8), sticky="w")

        # Output
        out_frame = ctk.CTkFrame(tab, corner_radius=8)
        out_frame.grid(row=2, column=0, sticky="nsew")
        out_frame.grid_rowconfigure(0, weight=1)
        out_frame.grid_columnconfigure(0, weight=1)

        w["output"] = tk.Text(
            out_frame,
            bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 10),
            state="disabled", relief="flat", wrap="none",
            padx=8, pady=8,
        )
        w["output"].grid(row=0, column=0, sticky="nsew")
        xsb = ctk.CTkScrollbar(out_frame, orientation="horizontal", command=w["output"].xview)
        xsb.grid(row=1, column=0, sticky="ew")
        ysb = ctk.CTkScrollbar(out_frame, command=w["output"].yview)
        ysb.grid(row=0, column=1, sticky="ns")
        w["output"].configure(xscrollcommand=xsb.set, yscrollcommand=ysb.set)

        for tag, color in [("ok","#2ecc71"),("error","#e74c3c"),("warning","#f39c12"),("info","#c9d1d9")]:
            w["output"].tag_configure(tag, foreground=color)

        ctk.CTkButton(
            tab, text="Clear Output", width=100, height=28,
            fg_color="#7f8c8d", hover_color="#626567",
            command=lambda: self._clear_text_widget(w.get("output")),
        ).grid(row=3, column=0, sticky="e", pady=(4, 0))

    def _on_rrun_listbox_select(self, _event=None) -> None:
        w = self._rrun_w
        lb = w.get("vpbx_listbox")
        if not lb:
            return
        sel = lb.curselection()
        if not sel:
            return
        rec = w["vpbx_filtered"][sel[0]]
        ip = rec.get("ip") or ""
        ftp_pass = (rec.get("ftp_pass") or "").strip()
        handle = rec.get("handle") or ""
        name = (rec.get("name") or "")[:40]
        srv = w.get("server_entry")
        if srv:
            srv.delete(0, "end")
            srv.insert(0, ip)
        if ftp_pass:
            pwd = w.get("password_entry")
            if pwd:
                pwd.delete(0, "end")
                pwd.insert(0, ftp_pass)
        if w.get("lbl_status"):
            w["lbl_status"].configure(
                text=f"Selected: {handle} — {name}  ({ip})",
                text_color="#3498db",
            )

    def _rrun_picker_refresh(self) -> None:
        w = self._rrun_w
        lb = w.get("vpbx_listbox")
        if not lb:
            return
        flt = w["vpbx_status_var"].get()
        q = w["vpbx_search_var"].get().lower()
        filtered = [
            r for r in w["vpbx_records"]
            if (flt == "All" or r.get("account_status") == flt)
            and (not q or q in (r.get("handle") or "").lower()
                        or q in (r.get("name") or "").lower()
                        or q in (r.get("ip") or "").lower())
        ]
        filtered.sort(key=lambda r: (r.get("name") or r.get("handle") or "").lower())
        w["vpbx_filtered"] = filtered
        lb.delete(0, "end")
        for r in filtered:
            h = (r.get("handle") or "").upper()
            ip = r.get("ip") or "—"
            name = (r.get("name") or "")[:32]
            has_pass = "🔑" if r.get("ftp_pass") else "  "
            lb.insert("end", f"{h:<5}  {ip:<17}  {has_pass}  {name}")
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text=f"{len(filtered)} sites")

    def _on_rrun_vpbx_refresh(self) -> None:
        w = self._rrun_w
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text="loading…")
        self._run_in_thread(self._do_rrun_vpbx_fetch)

    def _do_rrun_vpbx_fetch(self) -> None:
        try:
            r = requests.get(f"{API_BASE}/api/vpbx/records", timeout=10)
            r.raise_for_status()
            records = r.json().get("items", [])
            self.after(0, lambda recs=records: self._on_rrun_vpbx_loaded(recs))
        except Exception:
            def _err():
                w = self._rrun_w
                count_lbl = w.get("vpbx_count_lbl")
                if count_lbl:
                    count_lbl.config(text="offline")
            self.after(0, _err)

    def _on_rrun_vpbx_loaded(self, records: list[dict]) -> None:
        w = self._rrun_w
        w["vpbx_records"] = records
        self._rrun_picker_refresh()

    def _on_rrun_start(self) -> None:
        w = self._rrun_w
        server = w["server_entry"].get().strip()
        if not server:
            messagebox.showerror("Missing Server", "Enter a server IP or hostname.")
            return
        menu_val    = w["menu_var"].get()
        menu_choice = _RRUN_LABEL_TO_KEY.get(menu_val, menu_val.split()[0])
        self._run_in_thread(
            self._do_rrun_start,
            server=server,
            username=w["username_entry"].get().strip() or "123net",
            password=w["password_entry"].get(),
            root_password=w["root_password_entry"].get(),
            menu_choice=menu_choice,
            grab_dump=w["grab_dump_var"].get(),
        )

    def _do_rrun_start(
        self, server: str, username: str, password: str,
        root_password: str, menu_choice: str, grab_dump: bool,
    ) -> None:
        w = self._rrun_w
        self.after(0, lambda: w["btn_run"].configure(state="disabled", text="Running…"))
        self.after(0, lambda: w["btn_cancel"].configure(state="normal"))
        try:
            data = _deploy_post("/api/remote/run", json={
                "server": server, "username": username,
                "password": password, "root_password": root_password,
                "menu_choice": menu_choice, "grab_dump": grab_dump,
            })
            self._rrun_active_job = data
            jid = data.get("id", "")
            self._rrun_append(f"Remote run job started: {jid[:8]}\n", "info")
            self.after(0, lambda: w["lbl_status"].configure(
                text=f"Job {jid[:8]}  —  running", text_color="#3498db",
            ))
        except requests.HTTPError as exc:
            self._rrun_append(f"[ERROR] {exc.response.text}\n", "error")
            self.after(0, lambda: w["btn_run"].configure(state="normal", text="▶  Run"))
            self.after(0, lambda: w["btn_cancel"].configure(state="disabled"))
        except Exception as exc:
            self._rrun_append(f"[ERROR] Deploy backend unreachable: {exc}\n", "error")
            self.after(0, lambda: w["btn_run"].configure(state="normal", text="▶  Run"))
            self.after(0, lambda: w["btn_cancel"].configure(state="disabled"))

    def _on_rrun_cancel(self) -> None:
        job = self._rrun_active_job
        if not job:
            return
        self._run_in_thread(self._do_rrun_cancel, job_id=job.get("id", ""))

    def _do_rrun_cancel(self, job_id: str) -> None:
        try:
            _deploy_post(f"/api/jobs/{job_id}/cancel")
            self._rrun_append("[CANCELLED] Cancel requested.\n", "warning")
        except Exception as exc:
            self._rrun_append(f"[ERROR] Cancel failed: {exc}\n", "error")

    def _rrun_append(self, text: str, level: str = "info") -> None:
        w = self._rrun_w
        txt = w.get("output")
        if not txt:
            return
        l = text.lower()
        tag = "ok"      if ("[ok]" in l or "successful" in l) else \
              "error"   if ("[error]" in l or "[failed]" in l) else \
              "warning" if ("[warning]" in l or "warning" in l) else "info"
        def _do() -> None:
            txt.configure(state="normal")
            txt.insert("end", text, tag)
            txt.see("end")
            txt.configure(state="disabled")
        self.after(0, _do)

    def _refresh_rrun_tab(self, job: dict, tail: list[str]) -> None:
        w = self._rrun_w
        if not w:
            return
        status = job.get("status", "unknown")
        jid    = job.get("id", "")
        color  = _deploy_state_color(status)
        if w.get("lbl_status"):
            w["lbl_status"].configure(text=f"Job {jid[:8]}  —  {status}", text_color=color)
        txt = w.get("output")
        if txt:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            for line in tail:
                l = line.lower()
                tag = "ok"      if ("[ok]" in l or "successful" in l) else \
                      "error"   if ("[error]" in l or "[failed]" in l) else \
                      "warning" if ("[warning]" in l or "warning" in l) else "info"
                txt.insert("end", line, tag)
            txt.see("end")
            txt.configure(state="disabled")
        if status in ("succeeded", "failed", "cancelled"):
            if w.get("btn_run"):
                w["btn_run"].configure(state="normal", text="▶  Run")
            if w.get("btn_cancel"):
                w["btn_cancel"].configure(state="disabled")

    # ── Server Diagnostics sub-tab ───────────────────────────────────────────

    _QUICK_ACTION_CMDS: dict = {
        "watch_calls":      "asterisk -rx 'core show channels count' 2>/dev/null; asterisk -rx 'core show channels verbose' 2>/dev/null | head -50",
        "disk_check":       "df -h 2>/dev/null",
        "top_processes":    "ps aux --sort=-%cpu 2>/dev/null | head -25",
        "asterisk_errors":  "tail -200 /var/log/asterisk/full 2>/dev/null | grep -E 'ERROR|WARNING|NOTICE' | tail -50",
        "network_ports":    "ss -tulpn 2>/dev/null | grep -E ':5060|:4569|:10000|:10001|:443|:80|:22'",
        "restart_asterisk": "systemctl restart asterisk 2>&1 && sleep 2 && systemctl is-active asterisk && echo 'Asterisk is now active'",
        "reload_freepbx":   "fwconsole reload 2>&1 | tail -30",
        "clear_fail2ban":   "fail2ban-client unban --all 2>&1 && fail2ban-client status 2>/dev/null | head -5",
    }

    def _build_sdiag_sub_tab(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        w = self._sdiag_w

        form = ctk.CTkFrame(tab, corner_radius=8)
        form.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 4))
        form.grid_columnconfigure(0, weight=1)

        # ── VPBX site picker ──────────────────────────────────────────────
        _pbg = "#0f172a"
        picker_frm = tk.Frame(form, bg=_pbg, highlightbackground="#1e293b", highlightthickness=1)
        picker_frm.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        filter_row = tk.Frame(picker_frm, bg=_pbg)
        filter_row.pack(fill="x", padx=4, pady=(4, 2))

        w["vpbx_status_var"] = tk.StringVar(value="All")
        w["vpbx_status_cb"] = ttk.Combobox(
            filter_row, textvariable=w["vpbx_status_var"],
            values=["All", "production_billed", "testing", "decomissioned", "provisioning"],
            width=18, state="readonly",
        )
        w["vpbx_status_cb"].pack(side="left", padx=(0, 6))

        tk.Label(filter_row, text="Search:", bg=_pbg, fg="#94a3b8",
                 font=("Segoe UI", 9)).pack(side="left")
        w["vpbx_search_var"] = tk.StringVar()
        tk.Entry(
            filter_row, textvariable=w["vpbx_search_var"], width=18,
            bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0",
            relief="flat", font=("Segoe UI", 9),
        ).pack(side="left", padx=(3, 8))

        w["vpbx_count_lbl"] = tk.Label(filter_row, text="loading…",
                                        bg=_pbg, fg="#64748b", font=("Segoe UI", 9))
        w["vpbx_count_lbl"].pack(side="left")

        tk.Button(
            filter_row, text="↻ Refresh", bg="#1e3a5f", fg="#93c5fd",
            relief="flat", font=("Segoe UI", 8), padx=6,
            command=self._on_sdiag_vpbx_refresh,
        ).pack(side="right")

        w["btn_scrape_creds"] = tk.Button(
            filter_row, text="🔑 Scrape Passwords", bg="#1a3a1a", fg="#4ade80",
            relief="flat", font=("Segoe UI", 8), padx=6,
            command=self._on_sdiag_scrape_creds,
        )
        w["btn_scrape_creds"].pack(side="right", padx=(0, 4))

        lb_frm = tk.Frame(picker_frm, bg="#0d1117")
        lb_frm.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        vsb_p = ttk.Scrollbar(lb_frm, orient="vertical")
        vsb_p.pack(side="right", fill="y")
        w["vpbx_listbox"] = tk.Listbox(
            lb_frm, selectmode="single",
            bg="#0d1117", fg="#e2e8f0", font=("Courier New", 9),
            selectbackground="#1d4ed8", selectforeground="#ffffff",
            yscrollcommand=vsb_p.set, activestyle="none",
            bd=0, highlightthickness=0, height=4,
        )
        vsb_p.config(command=w["vpbx_listbox"].yview)
        w["vpbx_listbox"].pack(side="left", fill="both", expand=True)
        w["vpbx_records"] = []
        w["vpbx_filtered"] = []

        w["vpbx_status_cb"].bind("<<ComboboxSelected>>", lambda _: self._sdiag_picker_refresh())
        w["vpbx_search_var"].trace_add("write", lambda *_: self._sdiag_picker_refresh())
        w["vpbx_listbox"].bind("<<ListboxSelect>>", self._on_sdiag_listbox_select)

        # ── Credentials row ───────────────────────────────────────────────
        cred_row = ctk.CTkFrame(form, fg_color="transparent")
        cred_row.grid(row=1, column=0, padx=12, pady=(4, 6), sticky="ew")

        for lbl, key, kw in [
            ("IP:",        "server_entry",   {"width": 160, "placeholder_text": "pick above or type IP"}),
            ("User:",      "username_entry", {"width": 90}),
            ("SSH Pass:",  "password_entry", {"width": 120, "show": "●", "placeholder_text": "SSH pass"}),
            ("Root Pass:", "root_pw_entry",  {"width": 120, "show": "●", "placeholder_text": "root pass"}),
            ("Timeout:",   "timeout_entry",  {"width": 50}),
        ]:
            ctk.CTkLabel(cred_row, text=lbl, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
            ent = ctk.CTkEntry(cred_row, height=34, **kw)
            if key == "username_entry":
                ent.insert(0, "123net")
            elif key == "root_pw_entry":
                ent.insert(0, "sdxczvsdxczv")
            elif key == "timeout_entry":
                ent.insert(0, "15")
            ent.pack(side="left", padx=(0, 12))
            w[key] = ent

        # ── Status labels ─────────────────────────────────────────────────
        w["lbl_status"] = ctk.CTkLabel(
            form, text="Select a site above, then choose a diagnostic tool.",
            font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["lbl_status"].grid(row=2, column=0, padx=12, pady=(0, 2), sticky="w")

        w["lbl_cred_status"] = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color="#7f8c8d",
        )
        w["lbl_cred_status"].grid(row=3, column=0, padx=12, pady=(0, 4), sticky="w")

        # ── Inner tool tabs ───────────────────────────────────────────────
        inner_tabs = ctk.CTkTabview(tab, corner_radius=6)
        inner_tabs.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        w["inner_tabs"] = inner_tabs

        self._build_sdiag_health_tab(inner_tabs.add("Health Snapshot"))
        self._build_sdiag_log_tab(inner_tabs.add("Live Log Tail"))
        self._build_sdiag_cmd_tab(inner_tabs.add("Run Command"))

        # Auto-load site list
        self._run_in_thread(self._do_sdiag_vpbx_fetch)

    def _build_sdiag_health_tab(self, tab: Any) -> None:
        w = self._sdiag_w
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # Action bar
        action_bar = ctk.CTkFrame(tab, fg_color="transparent")
        action_bar.grid(row=0, column=0, padx=8, pady=(6, 4), sticky="ew")

        w["health_btn_run"] = ctk.CTkButton(
            action_bar, text="🔍  Diagnose",
            fg_color="#2980b9", hover_color="#1f6391",
            width=130, height=34, font=ctk.CTkFont(size=13),
            command=self._on_sdiag_run,
        )
        w["health_btn_run"].pack(side="left", padx=(0, 12))

        w["auto_refresh_var"] = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            action_bar, text="Auto-refresh", variable=w["auto_refresh_var"],
            command=self._on_sdiag_auto_refresh_toggle,
            font=ctk.CTkFont(size=12), width=120,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(action_bar, text="every", font=ctk.CTkFont(size=11)).pack(side="left")
        w["refresh_interval_var"] = tk.StringVar(value="30")
        ctk.CTkEntry(action_bar, textvariable=w["refresh_interval_var"],
                     width=42, height=26, font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        ctk.CTkLabel(action_bar, text="s", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 16))

        # Live call count watcher
        ctk.CTkLabel(action_bar, text="Active calls:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        w["call_count_lbl"] = ctk.CTkLabel(
            action_bar, text="—", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f39c12",
        )
        w["call_count_lbl"].pack(side="left", padx=(0, 6))
        w["watch_calls_btn"] = ctk.CTkButton(
            action_bar, text="Watch", width=70, height=28, font=ctk.CTkFont(size=11),
            fg_color="#2d5016", hover_color="#3d6b20",
            command=self._on_sdiag_watch_calls_toggle,
        )
        w["watch_calls_btn"].pack(side="left")
        w["call_watch_active"] = False
        w["call_watch_after_id"] = None
        w["auto_refresh_after_id"] = None

        # Quick action buttons
        qa_frame = ctk.CTkFrame(tab, corner_radius=6, fg_color="#161b22")
        qa_frame.grid(row=1, column=0, padx=8, pady=(0, 4), sticky="ew")

        ctk.CTkLabel(qa_frame, text="Quick Actions:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#7f8c8d").pack(side="left", padx=(8, 8), pady=6)

        for label, action in [
            ("Active Calls",  "watch_calls"),
            ("Disk Usage",    "disk_check"),
            ("Top Processes", "top_processes"),
            ("Recent Errors", "asterisk_errors"),
            ("VoIP Ports",    "network_ports"),
        ]:
            ctk.CTkButton(
                qa_frame, text=label, width=110, height=28, font=ctk.CTkFont(size=11),
                fg_color="#1e3a5f", hover_color="#2e4a6f",
                command=lambda a=action: self._on_sdiag_quick_action(a),
            ).pack(side="left", padx=3, pady=6)

        ttk.Separator(qa_frame, orient="vertical").pack(side="left", padx=8, fill="y", pady=6)

        for label, action, fg, hv in [
            ("Reload FreePBX",     "reload_freepbx",   "#6b3d00", "#8a5010"),
            ("Restart Asterisk ⚠", "restart_asterisk", "#5c1a1a", "#7a2222"),
            ("Clear Fail2Ban",     "clear_fail2ban",   "#1a4a2a", "#2a6a3a"),
        ]:
            ctk.CTkButton(
                qa_frame, text=label, width=145, height=28, font=ctk.CTkFont(size=11),
                fg_color=fg, hover_color=hv,
                command=lambda a=action: self._on_sdiag_quick_action(a),
            ).pack(side="left", padx=3, pady=6)

        # Health output
        out_frame = ctk.CTkFrame(tab, corner_radius=6)
        out_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))
        out_frame.grid_rowconfigure(0, weight=1)
        out_frame.grid_columnconfigure(0, weight=1)

        w["health_output"] = tk.Text(
            out_frame, bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 10), state="disabled", relief="flat",
            wrap="word", padx=8, pady=8,
        )
        w["health_output"].grid(row=0, column=0, sticky="nsew")
        ysb = ctk.CTkScrollbar(out_frame, command=w["health_output"].yview)
        ysb.grid(row=0, column=1, sticky="ns")
        w["health_output"].configure(yscrollcommand=ysb.set)

        for tag, color in [
            ("ok",      "#2ecc71"), ("key",     "#3498db"),
            ("error",   "#e74c3c"), ("value",   "#ecf0f1"),
            ("hint",    "#f39c12"), ("section", "#9b59b6"),
            ("warn",    "#e67e22"),
        ]:
            w["health_output"].tag_configure(tag, foreground=color)

        ctk.CTkButton(
            tab, text="Clear", width=70, height=26,
            fg_color="#7f8c8d", hover_color="#626567",
            command=lambda: self._clear_text_widget(w.get("health_output")),
        ).grid(row=3, column=0, sticky="e", padx=8, pady=(0, 4))

    def _build_sdiag_log_tab(self, tab: Any) -> None:
        w = self._sdiag_w
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Control bar
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.grid(row=0, column=0, padx=8, pady=(6, 4), sticky="ew")

        ctk.CTkLabel(ctrl, text="Log:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        w["log_path_var"] = tk.StringVar(value="/var/log/asterisk/full")
        ctk.CTkEntry(ctrl, textvariable=w["log_path_var"], width=240, height=30,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(ctrl, text="Filter:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        w["log_filter_var"] = tk.StringVar(value="")
        ctk.CTkEntry(ctrl, textvariable=w["log_filter_var"], width=130, height=30,
                     placeholder_text="grep pattern", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(ctrl, text="Level:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        w["log_level_var"] = tk.StringVar(value="All")
        ttk.Combobox(ctrl, textvariable=w["log_level_var"],
                     values=["All", "ERROR", "WARNING", "NOTICE", "VERBOSE"],
                     state="readonly", width=9).pack(side="left", padx=(0, 12))

        w["tail_btn_start"] = ctk.CTkButton(
            ctrl, text="▶  Start Tail", width=110, height=32,
            fg_color="#2d5016", hover_color="#3d6b20", font=ctk.CTkFont(size=12),
            command=self._on_sdiag_tail_start,
        )
        w["tail_btn_start"].pack(side="left", padx=(0, 6))
        w["tail_btn_stop"] = ctk.CTkButton(
            ctrl, text="■  Stop", width=80, height=32,
            fg_color="#5c1a1a", hover_color="#7a2222",
            font=ctk.CTkFont(size=12), state="disabled",
            command=self._on_sdiag_tail_stop,
        )
        w["tail_btn_stop"].pack(side="left")
        w["tail_status_lbl"] = ctk.CTkLabel(ctrl, text="", font=ctk.CTkFont(size=11), text_color="#7f8c8d")
        w["tail_status_lbl"].pack(side="left", padx=(10, 0))

        # Log output (horizontal scroll for log lines)
        out_frame = ctk.CTkFrame(tab, corner_radius=6)
        out_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 0))
        out_frame.grid_rowconfigure(0, weight=1)
        out_frame.grid_columnconfigure(0, weight=1)

        w["log_output"] = tk.Text(
            out_frame, bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 9), state="disabled", relief="flat",
            wrap="none", padx=8, pady=8,
        )
        w["log_output"].grid(row=0, column=0, sticky="nsew")
        log_ysb = ctk.CTkScrollbar(out_frame, command=w["log_output"].yview)
        log_ysb.grid(row=0, column=1, sticky="ns")
        log_xsb = ttk.Scrollbar(out_frame, orient="horizontal", command=w["log_output"].xview)
        log_xsb.grid(row=1, column=0, sticky="ew")
        w["log_output"].configure(yscrollcommand=log_ysb.set, xscrollcommand=log_xsb.set)

        for tag, color in [
            ("log_error",   "#e74c3c"), ("log_warning", "#f39c12"),
            ("log_notice",  "#3498db"), ("log_verbose", "#7f8c8d"),
            ("log_debug",   "#2980b9"), ("log_normal",  "#c9d1d9"),
        ]:
            w["log_output"].tag_configure(tag, foreground=color)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="e", padx=8, pady=(2, 4))
        ctk.CTkButton(btn_row, text="Clear", width=70, height=26,
                      fg_color="#7f8c8d", hover_color="#626567",
                      command=lambda: self._clear_text_widget(w.get("log_output"))).pack(side="left", padx=4)
        w["log_auto_scroll_var"] = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(btn_row, text="Auto-scroll", variable=w["log_auto_scroll_var"],
                        font=ctk.CTkFont(size=11), width=100).pack(side="left")

        # Tail state
        w["tail_stop_event"] = None
        w["tail_thread"] = None

    def _build_sdiag_cmd_tab(self, tab: Any) -> None:
        w = self._sdiag_w
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Command bar
        cmd_bar = ctk.CTkFrame(tab, fg_color="transparent")
        cmd_bar.grid(row=0, column=0, padx=8, pady=(6, 4), sticky="ew")
        cmd_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cmd_bar, text="$", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#2ecc71").pack(side="left", padx=(4, 6))
        w["cmd_var"] = tk.StringVar()
        cmd_entry = ctk.CTkEntry(cmd_bar, textvariable=w["cmd_var"], height=36,
                                  font=ctk.CTkFont(size=12), placeholder_text="command to run on remote host")
        cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        cmd_entry.bind("<Return>", lambda _: self._on_sdiag_cmd_run())
        w["cmd_entry"] = cmd_entry

        w["as_root_var"] = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(cmd_bar, text="Root", variable=w["as_root_var"],
                        font=ctk.CTkFont(size=11), width=70).pack(side="left", padx=(0, 6))
        w["cmd_btn_run"] = ctk.CTkButton(
            cmd_bar, text="▶  Run", width=90, height=36, font=ctk.CTkFont(size=12),
            fg_color="#2d5016", hover_color="#3d6b20",
            command=self._on_sdiag_cmd_run,
        )
        w["cmd_btn_run"].pack(side="left")

        # Command output
        out_frame = ctk.CTkFrame(tab, corner_radius=6)
        out_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 0))
        out_frame.grid_rowconfigure(0, weight=1)
        out_frame.grid_columnconfigure(0, weight=1)

        w["cmd_output"] = tk.Text(
            out_frame, bg="#0d1117", fg="#c9d1d9",
            font=("Consolas", 10), state="disabled", relief="flat",
            wrap="none", padx=8, pady=8,
        )
        w["cmd_output"].grid(row=0, column=0, sticky="nsew")
        cmd_ysb = ctk.CTkScrollbar(out_frame, command=w["cmd_output"].yview)
        cmd_ysb.grid(row=0, column=1, sticky="ns")
        cmd_xsb = ttk.Scrollbar(out_frame, orient="horizontal", command=w["cmd_output"].xview)
        cmd_xsb.grid(row=1, column=0, sticky="ew")
        w["cmd_output"].configure(yscrollcommand=cmd_ysb.set, xscrollcommand=cmd_xsb.set)

        for tag, color in [
            ("ok", "#2ecc71"), ("error", "#e74c3c"), ("cmd_hdr", "#3498db"), ("value", "#ecf0f1"),
        ]:
            w["cmd_output"].tag_configure(tag, foreground=color)

        ctk.CTkButton(
            tab, text="Clear", width=70, height=26,
            fg_color="#7f8c8d", hover_color="#626567",
            command=lambda: self._clear_text_widget(w.get("cmd_output")),
        ).grid(row=2, column=0, sticky="e", padx=8, pady=(2, 4))

    def _on_sdiag_listbox_select(self, _event=None) -> None:
        w = self._sdiag_w
        lb = w.get("vpbx_listbox")
        if not lb:
            return
        sel = lb.curselection()
        if not sel:
            return
        rec = w["vpbx_filtered"][sel[0]]
        ip = rec.get("ip") or ""
        ftp_pass = (rec.get("ftp_pass") or "").strip()
        handle = rec.get("handle") or ""
        name = (rec.get("name") or "")[:40]
        srv = w.get("server_entry")
        if srv:
            srv.delete(0, "end")
            srv.insert(0, ip)
        if ftp_pass:
            pwd = w.get("password_entry")
            if pwd:
                pwd.delete(0, "end")
                pwd.insert(0, ftp_pass)
        if w.get("lbl_status"):
            w["lbl_status"].configure(
                text=f"Selected: {handle} — {name}  ({ip})",
                text_color="#3498db",
            )

    def _sdiag_picker_refresh(self) -> None:
        w = self._sdiag_w
        lb = w.get("vpbx_listbox")
        if not lb:
            return
        flt = w["vpbx_status_var"].get()
        q = w["vpbx_search_var"].get().lower()
        filtered = [
            r for r in w["vpbx_records"]
            if (flt == "All" or r.get("account_status") == flt)
            and (not q or q in (r.get("handle") or "").lower()
                        or q in (r.get("name") or "").lower()
                        or q in (r.get("ip") or "").lower())
        ]
        filtered.sort(key=lambda r: (r.get("name") or r.get("handle") or "").lower())
        w["vpbx_filtered"] = filtered
        lb.delete(0, "end")
        for r in filtered:
            h = (r.get("handle") or "").upper()
            ip = r.get("ip") or "—"
            name = (r.get("name") or "")[:32]
            has_pass = "🔑" if r.get("ftp_pass") else "  "
            lb.insert("end", f"{h:<5}  {ip:<17}  {has_pass}  {name}")
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text=f"{len(filtered)} sites")

    def _on_sdiag_vpbx_refresh(self) -> None:
        w = self._sdiag_w
        count_lbl = w.get("vpbx_count_lbl")
        if count_lbl:
            count_lbl.config(text="loading…")
        self._run_in_thread(self._do_sdiag_vpbx_fetch)

    def _do_sdiag_vpbx_fetch(self) -> None:
        try:
            r = requests.get(f"{API_BASE}/api/vpbx/records", timeout=10)
            r.raise_for_status()
            records = r.json().get("items", [])
            self.after(0, lambda recs=records: self._on_sdiag_vpbx_loaded(recs))
        except Exception:
            def _err():
                w = self._sdiag_w
                count_lbl = w.get("vpbx_count_lbl")
                if count_lbl:
                    count_lbl.config(text="offline")
            self.after(0, _err)

    def _on_sdiag_vpbx_loaded(self, records: list[dict]) -> None:
        w = self._sdiag_w
        w["vpbx_records"] = records
        self._sdiag_picker_refresh()

    def _on_sdiag_scrape_creds(self) -> None:
        w = self._sdiag_w
        if w.get("btn_scrape_creds"):
            w["btn_scrape_creds"].configure(state="disabled", text="Scraping…")
        if w.get("lbl_cred_status"):
            w["lbl_cred_status"].configure(
                text="Opening browser — log in with SSO to start…", text_color="#f39c12"
            )
        self._run_in_thread(self._do_sdiag_scrape_creds)

    def _do_sdiag_scrape_creds(self) -> None:
        try:
            r = requests.post(f"{API_BASE}/api/vpbx/credentials/refresh", json={}, timeout=10)
            r.raise_for_status()
            job_id = r.json().get("job_id", "")
            self.after(0, lambda jid=job_id: self._sdiag_poll_cred_job(jid))
        except Exception as exc:
            def _err(e=exc):
                w = self._sdiag_w
                if w.get("btn_scrape_creds"):
                    w["btn_scrape_creds"].configure(state="normal", text="🔑  Scrape SSH Passwords")
                if w.get("lbl_cred_status"):
                    w["lbl_cred_status"].configure(
                        text=f"Failed to start: {e}", text_color="#e74c3c"
                    )
            self.after(0, _err)

    def _sdiag_poll_cred_job(self, job_id: str) -> None:
        self._run_in_thread(self._do_sdiag_poll_cred_job, job_id=job_id)

    def _do_sdiag_poll_cred_job(self, job_id: str) -> None:
        import time as _time
        while True:
            try:
                r = requests.get(f"{API_BASE}/api/jobs/{job_id}", timeout=10)
                if not r.ok:
                    break
                row = r.json()
                status = row.get("status", "")
                result = row.get("result") or {}
                if status in ("done", "succeeded"):
                    count = result.get("credentials_count", "?")
                    def _done(n=count):
                        w = self._sdiag_w
                        if w.get("btn_scrape_creds"):
                            w["btn_scrape_creds"].configure(state="normal", text="🔑  Scrape SSH Passwords")
                        if w.get("lbl_cred_status"):
                            w["lbl_cred_status"].configure(
                                text=f"Done — saved SSH passwords for {n} sites. Deploy tab will auto-fill on next site selection.",
                                text_color="#2ecc71",
                            )
                        # Reload vpbx_records so the deploy picker picks up ftp_pass immediately
                        self._run_in_thread(self._do_vpbx_fetch_for_picker)
                    self.after(0, _done)
                    break
                elif status == "error":
                    err_msg = row.get("error_message") or "unknown error"
                    def _err(m=err_msg):
                        w = self._sdiag_w
                        if w.get("btn_scrape_creds"):
                            w["btn_scrape_creds"].configure(state="normal", text="🔑  Scrape SSH Passwords")
                        if w.get("lbl_cred_status"):
                            w["lbl_cred_status"].configure(
                                text=f"Scrape failed: {m}", text_color="#e74c3c"
                            )
                    self.after(0, _err)
                    break
                elif status == "cancelled":
                    def _cancelled():
                        w = self._sdiag_w
                        if w.get("btn_scrape_creds"):
                            w["btn_scrape_creds"].configure(state="normal", text="🔑  Scrape SSH Passwords")
                        if w.get("lbl_cred_status"):
                            w["lbl_cred_status"].configure(text="Scrape cancelled.", text_color="#f39c12")
                    self.after(0, _cancelled)
                    break
                else:
                    completed = row.get("completed", 0)
                    total = row.get("total", 0)
                    def _progress(c=completed, t=total):
                        w = self._sdiag_w
                        if w.get("lbl_cred_status"):
                            suffix = f" ({c}/{t})" if t else ""
                            w["lbl_cred_status"].configure(
                                text=f"Scraping SSH passwords{suffix} — browser must stay open…",
                                text_color="#f39c12",
                            )
                    self.after(0, _progress)
            except Exception:
                break
            _time.sleep(2)

    def _on_sdiag_run(self) -> None:
        w = self._sdiag_w
        server = w["server_entry"].get().strip()
        if not server:
            messagebox.showerror("No Site Selected", "Select a site from the list above.")
            return
        try:
            timeout = float(w["timeout_entry"].get().strip() or "15")
        except ValueError:
            timeout = 15.0
        self._run_in_thread(
            self._do_sdiag_run,
            server=server,
            username=w["username_entry"].get().strip() or "123net",
            password=w["password_entry"].get(),
            root_password=w["root_pw_entry"].get(),
            timeout=timeout,
        )

    def _do_sdiag_run(
        self, server: str, username: str, password: str,
        root_password: str, timeout: float,
    ) -> None:
        w = self._sdiag_w
        btn = w.get("health_btn_run")
        self.after(0, lambda: btn and btn.configure(state="disabled", text="Running…"))
        self.after(0, lambda: w["lbl_status"].configure(
            text=f"Connecting to {server}…", text_color="#f39c12",
        ))
        try:
            data = _deploy_post("/api/diagnostics/summary", json={
                "server": server, "username": username,
                "password": password,
                "root_password": root_password or password,
                "timeout_seconds": timeout,
            })
            self._ui_queue.put(("sdiag_result", data, None))
        except requests.HTTPError as exc:
            try:
                err_data = exc.response.json()
            except Exception:
                err_data = {"error": exc.response.text}
            self._ui_queue.put(("sdiag_result", err_data, str(exc)))
        except Exception as exc:
            self._ui_queue.put(("sdiag_result", {"error": str(exc)}, str(exc)))
        finally:
            self.after(0, lambda: btn and btn.configure(state="normal", text="🔍  Diagnose"))

    def _display_sdiag_result(self, data: dict, error: str | None) -> None:
        w = self._sdiag_w
        txt = w.get("health_output")
        if not txt:
            return
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        if error or not data.get("ok", True):
            msg  = data.get("error") or error or "Diagnostics failed"
            hint = data.get("_hint", "")
            txt.insert("end", f"[ERROR] {msg}\n\n", "error")
            if hint:
                txt.insert("end", f"{hint}\n", "hint")
            if w.get("lbl_status"):
                short = str(msg)[:70]
                w["lbl_status"].configure(text=f"Failed — {short}", text_color="#e74c3c")
        else:
            srv = data.get("server", "")
            ts  = data.get("generated_at_utc", "")
            if w.get("lbl_status"):
                w["lbl_status"].configure(
                    text=f"✓ Diagnostics complete — {srv}  ({ts})", text_color="#2ecc71",
                )

            # ── Render sections in friendly order ────────────────────────
            def _section(title: str) -> None:
                txt.insert("end", f"\n{'─' * 60}\n", "section")
                txt.insert("end", f"  {title}\n", "section")
                txt.insert("end", f"{'─' * 60}\n", "section")

            def _render(obj: Any, indent: int = 0) -> None:
                pad = "  " * indent
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if str(k).startswith("_"):
                            continue
                        if isinstance(v, (dict, list)):
                            txt.insert("end", f"{pad}{k}:\n", "key")
                            _render(v, indent + 1)
                        else:
                            sv = str(v)
                            ok_val  = v is True  or sv.lower() in ("ok", "true", "yes", "installed", "found", "active", "enabled")
                            err_val = v is False or sv.lower() in ("false", "no", "missing", "not installed", "not found", "failed", "inactive")
                            warn_val = sv.lower() in ("inactive", "disabled", "unknown")
                            vtag = "ok" if ok_val else "error" if err_val else "warn" if warn_val else "value"
                            txt.insert("end", f"{pad}{k}: ", "key")
                            txt.insert("end", f"{sv}\n", vtag)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (dict, list)):
                            _render(item, indent)
                        else:
                            txt.insert("end", f"{pad}• {item}\n", "value")
                else:
                    txt.insert("end", f"{pad}{obj}\n", "value")

            # Meta
            _section("System Info")
            _render(data.get("meta", {}), 1)

            # Calls
            _section("Active Calls")
            _render(data.get("calls", {}), 1)

            # Endpoints
            _section("Endpoints")
            ep = dict(data.get("endpoints", {}))
            ep.pop("registered_ids", None)  # skip the long list in main view
            _render(ep, 1)
            reg_ids = data.get("endpoints", {}).get("registered_ids", [])
            if reg_ids:
                txt.insert("end", "  registered_ids:\n", "key")
                for eid in reg_ids:
                    txt.insert("end", f"    • {eid}\n", "value")

            # Time conditions
            _section("Time Conditions")
            _render(data.get("time_conditions", {}), 1)

            # Services
            _section("Services")
            for svc in data.get("services", []):
                name  = svc.get("name", "?")
                state = svc.get("state", "?")
                en    = svc.get("enabled", "?")
                state_tag = "ok" if state == "active" else "error" if state == "failed" else "warn"
                txt.insert("end", f"  {name:<12}", "key")
                txt.insert("end", f"  {state:<10}", state_tag)
                txt.insert("end", f"  enabled={en}\n", "value")

            # System health (new section)
            sys_data = data.get("system", {})
            if sys_data:
                _section("System Health")
                disk = sys_data.get("disk", {})
                if disk:
                    pct_str = disk.get("use_pct", "")
                    try:
                        pct_num = int(pct_str.rstrip("%"))
                        disk_tag = "error" if pct_num >= 90 else "warn" if pct_num >= 75 else "ok"
                    except Exception:
                        disk_tag = "value"
                    txt.insert("end", "  Disk /: ", "key")
                    txt.insert("end", f"{disk.get('used','?')} / {disk.get('total','?')}  ({pct_str} used)  free={disk.get('free','?')}\n", disk_tag)

                mem = sys_data.get("memory", {})
                if mem:
                    total_mb = mem.get("total_mb", 0) or 1
                    used_mb  = mem.get("used_mb", 0)
                    avail_mb = mem.get("available_mb", used_mb)
                    pct_used = int((used_mb / total_mb) * 100) if total_mb else 0
                    mem_tag  = "error" if pct_used >= 90 else "warn" if pct_used >= 75 else "ok"
                    txt.insert("end", "  Memory:  ", "key")
                    txt.insert("end", f"{used_mb} MB used / {total_mb} MB total  ({pct_used}%)  avail={avail_mb} MB\n", mem_tag)

                load = sys_data.get("load", {})
                if load:
                    txt.insert("end", "  Load:    ", "key")
                    txt.insert("end", f"1m={load.get('1m','?')}  5m={load.get('5m','?')}  15m={load.get('15m','?')}\n", "value")

                f2b = sys_data.get("fail2ban", {})
                if f2b.get("available"):
                    banned = f2b.get("sshd_banned", 0)
                    ban_tag = "warn" if banned > 0 else "ok"
                    txt.insert("end", "  Fail2Ban:", "key")
                    txt.insert("end", f" sshd_banned={banned}  jails={f2b.get('jail_count','?')}\n", ban_tag)
                else:
                    txt.insert("end", "  Fail2Ban:", "key")
                    txt.insert("end", " not installed\n", "value")

                restart = sys_data.get("asterisk_last_restart")
                if restart:
                    txt.insert("end", "  Asterisk last restart: ", "key")
                    txt.insert("end", f"{restart}\n", "value")

            # Snapshot
            snap = data.get("snapshot", {})
            if snap:
                _section("Callflows Snapshot")
                _render(snap, 1)

        txt.see("1.0")
        txt.configure(state="disabled")

    # ── Quick actions ──────────────────────────────────────────────────────────

    def _on_sdiag_quick_action(self, action: str) -> None:
        _CONFIRM = {
            "restart_asterisk": "⚠ This will DROP all active calls.\nAre you sure you want to restart Asterisk?",
            "reload_freepbx":   "This will reload FreePBX configuration.\nContinue?",
            "clear_fail2ban":   "This will unban ALL currently blocked IPs.\nContinue?",
        }
        if action in _CONFIRM:
            if not messagebox.askyesno("Confirm Action", _CONFIRM[action]):
                return
        w = self._sdiag_w
        if w.get("inner_tabs"):
            try:
                w["inner_tabs"].set("Run Command")
            except Exception:
                pass
        server = w["server_entry"].get().strip()
        if not server:
            messagebox.showwarning("No Server", "Select a server from the picker first.")
            return
        cmd = self._QUICK_ACTION_CMDS.get(action, f"echo 'unknown action: {action}'")
        self._sdiag_append_cmd_output(f"\n# Quick Action: {action}\n$ {cmd}\n", "cmd_hdr")
        self._run_in_thread(
            self._do_sdiag_run_command,
            server=server,
            username=w["username_entry"].get().strip() or "123net",
            password=w["password_entry"].get().strip(),
            root_password=w["root_pw_entry"].get().strip(),
            command=cmd,
            as_root=True,
            timeout=max(60.0, float(w["timeout_entry"].get().strip() or "30")),
        )

    # ── Run Command tab methods ────────────────────────────────────────────────

    def _on_sdiag_cmd_run(self) -> None:
        w = self._sdiag_w
        cmd = w.get("cmd_var") and w["cmd_var"].get().strip()
        if not cmd:
            return
        server = w["server_entry"].get().strip()
        if not server:
            messagebox.showwarning("No Server", "Select a server from the picker first.")
            return
        as_root = bool(w.get("as_root_var") and w["as_root_var"].get())
        try:
            timeout = float(w["timeout_entry"].get().strip() or "30")
        except ValueError:
            timeout = 30.0
        self._sdiag_append_cmd_output(f"\n$ {cmd}\n", "cmd_hdr")
        self._run_in_thread(
            self._do_sdiag_run_command,
            server=server,
            username=w["username_entry"].get().strip() or "123net",
            password=w["password_entry"].get().strip(),
            root_password=w["root_pw_entry"].get().strip(),
            command=cmd,
            as_root=as_root,
            timeout=timeout,
        )

    def _do_sdiag_run_command(
        self, server: str, username: str, password: str,
        root_password: str, command: str, as_root: bool, timeout: float,
    ) -> None:
        w = self._sdiag_w
        btn = w.get("cmd_btn_run")
        self.after(0, lambda: btn and btn.configure(state="disabled", text="Running…"))
        try:
            result = _deploy_post("/api/diagnostics/run-command", json={
                "server": server, "username": username, "password": password,
                "root_password": root_password or password,
                "command": command, "as_root": as_root,
                "timeout_seconds": timeout,
            })
            self._ui_queue.put(("sdiag_cmd_result", result, None))
        except requests.HTTPError as exc:
            try:
                err_data = exc.response.json()
            except Exception:
                err_data = {"ok": False, "error": exc.response.text}
            self._ui_queue.put(("sdiag_cmd_result", err_data, str(exc)))
        except Exception as exc:
            self._ui_queue.put(("sdiag_cmd_result", {"ok": False, "error": str(exc)}, str(exc)))
        finally:
            self.after(0, lambda: btn and btn.configure(state="normal", text="▶  Run"))

    def _sdiag_append_cmd_output(self, text: str, tag: str = "value") -> None:
        w = self._sdiag_w
        txt = w.get("cmd_output")
        if not txt:
            return
        txt.configure(state="normal")
        txt.insert("end", text, tag)
        txt.see("end")
        txt.configure(state="disabled")

    def _display_sdiag_cmd_result(self, data: dict, error: str | None) -> None:
        w = self._sdiag_w
        txt = w.get("cmd_output")
        if not txt:
            return
        txt.configure(state="normal")
        if error or not data.get("ok", True):
            msg = data.get("error") or error or "Command failed"
            txt.insert("end", f"[ERROR] {msg}\n", "error")
        else:
            output = data.get("output", "")
            rc = data.get("rc", 0)
            if output:
                txt.insert("end", output + "\n", "value")
            rc_tag = "ok" if rc == 0 else "error"
            txt.insert("end", f"[exit {rc}]\n", rc_tag)
        txt.insert("end", "─" * 60 + "\n", "value")
        txt.see("end")
        txt.configure(state="disabled")

    # ── Auto-refresh ───────────────────────────────────────────────────────────

    def _on_sdiag_auto_refresh_toggle(self) -> None:
        w = self._sdiag_w
        enabled = w.get("auto_refresh_var") and w["auto_refresh_var"].get()
        after_id = w.pop("auto_refresh_after_id", None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        w["auto_refresh_after_id"] = None
        if enabled:
            self._on_sdiag_run()
            self._sdiag_schedule_auto_refresh()

    def _sdiag_schedule_auto_refresh(self) -> None:
        w = self._sdiag_w
        if not (w.get("auto_refresh_var") and w["auto_refresh_var"].get()):
            return
        try:
            interval = max(10, int(w["refresh_interval_var"].get())) * 1000
        except Exception:
            interval = 30_000
        w["auto_refresh_after_id"] = self.after(interval, self._sdiag_auto_refresh_run)

    def _sdiag_auto_refresh_run(self) -> None:
        w = self._sdiag_w
        if not (w.get("auto_refresh_var") and w["auto_refresh_var"].get()):
            return
        self._on_sdiag_run()
        self._sdiag_schedule_auto_refresh()

    # ── Live call count watcher ────────────────────────────────────────────────

    def _on_sdiag_watch_calls_toggle(self) -> None:
        w = self._sdiag_w
        if w.get("call_watch_active"):
            w["call_watch_active"] = False
            after_id = w.pop("call_watch_after_id", None)
            if after_id:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
            w["call_watch_after_id"] = None
            if w.get("watch_calls_btn"):
                w["watch_calls_btn"].configure(text="Watch", fg_color="#2d5016", hover_color="#3d6b20")
            if w.get("call_count_lbl"):
                w["call_count_lbl"].configure(text="—", text_color="#f39c12")
        else:
            server = w.get("server_entry") and w["server_entry"].get().strip()
            if not server:
                messagebox.showwarning("No Server", "Select a server first.")
                return
            w["call_watch_active"] = True
            if w.get("watch_calls_btn"):
                w["watch_calls_btn"].configure(text="Stop", fg_color="#5c1a1a", hover_color="#7a2222")
            self._do_sdiag_watch_calls_once()
            self._sdiag_schedule_watch_calls()

    def _sdiag_schedule_watch_calls(self) -> None:
        w = self._sdiag_w
        if not w.get("call_watch_active"):
            return
        w["call_watch_after_id"] = self.after(10_000, self._sdiag_watch_calls_tick)

    def _sdiag_watch_calls_tick(self) -> None:
        w = self._sdiag_w
        if not w.get("call_watch_active"):
            return
        self._do_sdiag_watch_calls_once()
        self._sdiag_schedule_watch_calls()

    def _do_sdiag_watch_calls_once(self) -> None:
        w = self._sdiag_w
        server = w.get("server_entry") and w["server_entry"].get().strip()
        if not server:
            return
        try:
            timeout = float(w["timeout_entry"].get().strip() or "15")
        except Exception:
            timeout = 15.0
        self._run_in_thread(
            self._fetch_sdiag_call_count,
            server=server,
            username=w["username_entry"].get().strip() or "123net",
            password=w["password_entry"].get().strip(),
            root_password=w["root_pw_entry"].get().strip(),
            timeout=timeout,
        )

    def _fetch_sdiag_call_count(
        self, server: str, username: str, password: str, root_password: str, timeout: float,
    ) -> None:
        try:
            data = _deploy_post("/api/diagnostics/run-command", json={
                "server": server, "username": username,
                "password": password, "root_password": root_password or password,
                "command": "asterisk -rx 'core show channels count' 2>/dev/null",
                "as_root": True, "timeout_seconds": timeout,
            })
            output = data.get("output", "")
            count: int | None = None
            for line in output.splitlines():
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    count = int(parts[0])
                    break
            self._ui_queue.put(("sdiag_call_count", count))
        except Exception:
            self._ui_queue.put(("sdiag_call_count", None))

    # ── Live log tail ──────────────────────────────────────────────────────────

    def _on_sdiag_tail_start(self) -> None:
        w = self._sdiag_w
        server = w["server_entry"].get().strip()
        if not server:
            messagebox.showwarning("No Server", "Select a server from the picker first.")
            return
        self._on_sdiag_tail_stop()
        stop_event = threading.Event()
        w["tail_stop_event"] = stop_event
        if w.get("tail_btn_start"):
            w["tail_btn_start"].configure(state="disabled")
        if w.get("tail_btn_stop"):
            w["tail_btn_stop"].configure(state="normal")
        if w.get("tail_status_lbl"):
            w["tail_status_lbl"].configure(text=f"Connecting to {server}…", text_color="#f39c12")
        thread = threading.Thread(
            target=self._do_sdiag_tail_stream,
            kwargs={
                "server": server,
                "username": w["username_entry"].get().strip() or "123net",
                "password": w["password_entry"].get().strip(),
                "root_password": w["root_pw_entry"].get().strip(),
                "log_path": w.get("log_path_var", tk.StringVar(value="/var/log/asterisk/full")).get().strip() or "/var/log/asterisk/full",
                "filter_pattern": w.get("log_filter_var", tk.StringVar()).get().strip(),
                "stop_event": stop_event,
            },
            daemon=True, name="sdiag-tail",
        )
        w["tail_thread"] = thread
        thread.start()

    def _on_sdiag_tail_stop(self) -> None:
        w = self._sdiag_w
        stop_evt = w.get("tail_stop_event")
        if stop_evt:
            stop_evt.set()
        w["tail_stop_event"] = None
        w["tail_thread"] = None
        if w.get("tail_btn_start"):
            w["tail_btn_start"].configure(state="normal")
        if w.get("tail_btn_stop"):
            w["tail_btn_stop"].configure(state="disabled")
        if w.get("tail_status_lbl"):
            w["tail_status_lbl"].configure(text="Stopped.", text_color="#7f8c8d")

    def _do_sdiag_tail_stream(
        self, server: str, username: str, password: str,
        root_password: str, log_path: str, filter_pattern: str,
        stop_event: threading.Event,
    ) -> None:
        url = f"{_deploy_active_url[0]}/api/diagnostics/tail-log"
        payload = {
            "server": server, "username": username, "password": password,
            "root_password": root_password or password,
            "log_path": log_path, "filter_pattern": filter_pattern,
            "timeout_seconds": 30.0,
        }
        try:
            self._ui_queue.put(("sdiag_tail_status", f"Streaming {log_path} from {server}…", "#2ecc71"))
            with requests.post(url, json=payload, stream=True, timeout=None) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if not raw_line:
                        continue
                    if raw_line.startswith("data: "):
                        try:
                            evt = json.loads(raw_line[6:])
                            if evt.get("heartbeat"):
                                continue
                            if evt.get("eof"):
                                break
                            if evt.get("error"):
                                self._ui_queue.put(("sdiag_tail_line", f"[ERROR] {evt['error']}"))
                                break
                            line = evt.get("line", "")
                            if line:
                                self._ui_queue.put(("sdiag_tail_line", line))
                        except json.JSONDecodeError:
                            pass
        except requests.HTTPError as exc:
            if not stop_event.is_set():
                self._ui_queue.put(("sdiag_tail_line", f"[HTTP ERROR] {exc}"))
        except Exception as exc:
            if not stop_event.is_set():
                self._ui_queue.put(("sdiag_tail_line", f"[ERROR] {exc}"))
        finally:
            if not stop_event.is_set():
                self._ui_queue.put(("sdiag_tail_status", "Connection closed.", "#e74c3c"))
            self._ui_queue.put(("sdiag_tail_done",))

    def _sdiag_append_log_line(self, line: str) -> None:
        w = self._sdiag_w
        txt = w.get("log_output")
        if not txt:
            return
        level_filter = w.get("log_level_var") and w["log_level_var"].get()
        if level_filter and level_filter != "All":
            if level_filter.upper() not in line.upper():
                return
        upper = line.upper()
        if "ERROR" in upper:
            tag = "log_error"
        elif "WARNING" in upper:
            tag = "log_warning"
        elif "NOTICE" in upper:
            tag = "log_notice"
        elif "VERBOSE" in upper or "VERB[" in upper:
            tag = "log_verbose"
        elif "DEBUG" in upper:
            tag = "log_debug"
        else:
            tag = "log_normal"
        txt.configure(state="normal")
        txt.insert("end", line + "\n", tag)
        if w.get("log_auto_scroll_var") and w["log_auto_scroll_var"].get():
            txt.see("end")
        # Bound memory: keep last 5000 lines
        try:
            line_count = int(txt.index("end-1c").split(".")[0])
            if line_count > 5000:
                txt.delete("1.0", f"{line_count - 4000}.0")
        except Exception:
            pass
        txt.configure(state="disabled")

    # ── Deploy background poll ────────────────────────────────────────────────

    def _deploy_poll_loop(self) -> None:
        last_list_t = 0.0
        last_connect_t = 0.0
        while not self._closing:
            now = time.time()

            # Poll active deploy job at 500 ms
            job = self._deploy_active_job
            if job and job.get("status") in ("queued", "running"):
                try:
                    data = _deploy_get(f"/api/jobs/{job['id']}")
                    self._ui_queue.put(("deploy_job_update", data["job"], data["tail"]))
                except Exception:
                    pass

            # Poll active remote-run job at 500 ms
            rjob = self._rrun_active_job
            if rjob and rjob.get("status") in ("queued", "running"):
                try:
                    data = _deploy_get(f"/api/jobs/{rjob['id']}")
                    self._ui_queue.put(("rrun_job_update", data["job"], data["tail"]))
                except Exception:
                    pass

            # Refresh job list every 4 s
            if now - last_list_t > 4.0:
                try:
                    jobs = _deploy_get("/api/jobs")
                    jobs_sorted = sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)
                    self._ui_queue.put(("deploy_jobs", jobs_sorted))
                    last_list_t = now
                    # Update UI if method changed (e.g. recovered after outage)
                    if not self._deploy_backend_ok:
                        self._deploy_conn_method = (
                            "direct" if _deploy_active_url[0] == _DEPLOY_DIRECT_URL else "tunnel"
                        )
                        self.after(0, self._update_deploy_conn_ui)
                    self._deploy_backend_ok = True
                except Exception:
                    last_list_t = now
                    was_ok = self._deploy_backend_ok
                    self._deploy_backend_ok = False
                    if was_ok:
                        # Just went offline — update UI immediately
                        self._deploy_conn_method = ""
                        self.after(0, self._update_deploy_conn_ui)
                    # Auto-reconnect every 15 s
                    if now - last_connect_t >= 15:
                        last_connect_t = now
                        threading.Thread(target=self._deploy_auto_connect, daemon=True,
                                         name="deploy-autoconn").start()

            time.sleep(0.5)

    # ── Generic helper ────────────────────────────────────────────────────────

    def _clear_text_widget(self, txt: Any) -> None:
        if not txt:
            return
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.configure(state="disabled")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = ScrapeManagerApp()
    app.after(200, app._process_ui_queue)
    app.mainloop()

if __name__ == "__main__":
    main()
