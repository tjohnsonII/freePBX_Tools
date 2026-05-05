#!/usr/bin/env python3
"""Scrape Manager GUI — desktop app to start, resume, monitor, and stop webscraper jobs.

Requirements:
    pip install customtkinter requests

Run:
    python scrape_gui.py
"""

from __future__ import annotations

import os
import queue
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
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat").start()
        self._log_file_pos = 0
        threading.Thread(target=self._tail_log_loop, daemon=True, name="log-tail").start()
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
        if self._server_proc and self._server_proc.poll() is None:
            try:
                self._server_proc.terminate()
                self._server_proc.wait(timeout=4)
            except Exception:
                try:
                    self._server_proc.kill()
                except Exception:
                    pass
        self.destroy()

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
            row, text="▶  Start", fg_color="#27ae60", hover_color="#1e8449",
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


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = ScrapeManagerApp()
    app.after(200, app._process_ui_queue)
    app.mainloop()

if __name__ == "__main__":
    main()
