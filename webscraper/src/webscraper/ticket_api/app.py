from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from webscraper.handles_loader import load_handles
from webscraper.lib.db_path import get_tickets_db_path
from webscraper.logging_config import LOG_DIR, setup_logging
from webscraper.paths import kb_dir

# CLIENT_MODE=1 → send all writes to a remote server via HTTP (no local SQLite).
# Leave unset (or 0) for normal local operation.
if os.getenv("CLIENT_MODE", "").strip() == "1":
    from webscraper.ticket_api import db_client as db  # type: ignore[no-redef]
else:
    from webscraper.ticket_api import db  # type: ignore[assignment]

# ── Constants ────────────────────────────────────────────────────────────────

CHROME_CUSTOMERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
NOC_TICKETS_BASE_URL = "https://noc-tickets.123.net"
_LOGIN_URL_MARKERS = ("login", "signin", "sign_in", "sso", "auth", "oauth", "keycloak", "saml")
TICKET_TABLE_ROW_XPATH = "//div[@id='slideid5']//table//tr[td[1]//a[contains(@href,'/ticket/')]]"
SELENIUM_LOGIN_TIMEOUT_SECONDS = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "600"))

HANDLE_RE = re.compile(r"^[A-Za-z0-9]+$")
LOCALHOST_ONLY = {"127.0.0.1", "::1"}
OUTPUT_ROOT = str((Path(__file__).resolve().parents[4] / "webscraper" / "var").resolve())

# Cancel events keyed by job_id; set() to request graceful stop after current handle
_SCRAPE_CANCEL_EVENTS: dict[str, threading.Event] = {}

# Pause events keyed by job_id; set() = paused, clear() = running
_SCRAPE_PAUSE_EVENTS: dict[str, threading.Event] = {}

TIMELINE_CATEGORIES: tuple[str, ...] = (
    "ticket_opened",
    "follow_up",
    "phone_replacement",
    "provisioning_change",
    "queue_change",
    "voicemail_issue",
    "training_provided",
    "awaiting_customer",
    "resolved",
)

LOGGER = setup_logging("ticket_api")

# ── DB / time helpers ────────────────────────────────────────────────────────


def db_path() -> str:
    return get_tickets_db_path()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_event(
    level: str,
    message: str,
    *,
    handle: str | None = None,
    job_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    ts = _iso_now()
    LOGGER.info("[%s] %s", ts, message)
    try:
        db.add_event(db_path(), ts, level, handle, message, {"job_id": job_id, **(meta or {})})
        if job_id:
            db.add_scrape_event(db_path(), job_id, ts, level, "scrape.progress", message, {"handle": handle, **(meta or {})})
    except Exception as _exc:
        LOGGER.warning("append_event_failed msg=%s error=%s", message[:80], _exc)


def _normalize_handle(handle: str) -> str:
    normalized = (handle or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="handle is required")
    if not HANDLE_RE.match(normalized):
        raise HTTPException(status_code=400, detail="handle must be alphanumeric")
    return normalized


def _is_localhost_request(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in LOCALHOST_ONLY


# ── Multipart dependency check ───────────────────────────────────────────────


def _has_python_multipart() -> bool:
    return importlib.util.find_spec("multipart") is not None


def _missing_python_multipart_message() -> str:
    return f"Missing dependency python-multipart. Install: {sys.executable} -m pip install python-multipart"


# ── Scrape job helpers ────────────────────────────────────────────────────────


def _load_scrape_handles() -> list[str]:
    # File-based handles (CSV / txt — may be empty if no file is present)
    file_handles = [str(h).strip().upper() for h in load_handles() if str(h).strip()]

    # VPBX-based handles from the database (local SQLite or remote server via db_client).
    # These are authoritative — any handle on vpbx.cgi is automatically included here
    # after a VPBX scrape, so the ticket scraper stays in sync without manual CSV updates.
    vpbx_handles: list[str] = []
    try:
        vpbx_records = db.list_vpbx_records(db_path())
        vpbx_handles = [
            r["handle"].strip().upper()
            for r in vpbx_records
            if (r.get("handle") or "").strip()
        ]
    except Exception:
        pass

    deduped = sorted(set(file_handles) | set(vpbx_handles))
    LOGGER.info(
        "scrape_handles_loaded count=%s (file=%s vpbx_db=%s)",
        len(deduped), len(file_handles), len(vpbx_handles),
    )
    return deduped


# Backward-compat alias
_load_selenium_fallback_handles = _load_scrape_handles


def _scrape_search_string(handle: str) -> str:
    return f"{handle}:company_data:handle:{handle}"


# Backward-compat alias
_selenium_fallback_search_string = _scrape_search_string


def _update_scrape_job(
    *,
    job_id: str,
    status: str,
    completed: int,
    total: int,
    started_utc: str | None = None,
    finished_utc: str | None = None,
    error_message: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    db.update_scrape_job(
        db_path(),
        job_id,
        status=status,
        progress_completed=completed,
        progress_total=total,
        started_utc=started_utc,
        finished_utc=finished_utc,
        error_message=error_message,
        result=result,
    )


# Backward-compat alias
_update_selenium_fallback_job = _update_scrape_job


def _scrape_emit(
    job_id: str,
    message: str,
    *,
    handle: str | None = None,
    event: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    try:
        _append_event("info", message, handle=handle, job_id=job_id, meta={"event": event or "progress", **(data or {})})
    except Exception as _emit_exc:
        LOGGER.warning("scrape_emit_failed event=%s error=%s", event or "progress", _emit_exc)


# Backward-compat alias
_selenium_fallback_emit = _scrape_emit


def _is_login_page(driver: object) -> bool:
    """Return True if the browser is currently showing a login / SSO page."""
    url = (getattr(driver, "current_url", None) or "").lower()
    if any(m in url for m in _LOGIN_URL_MARKERS):
        return True
    try:
        src = (getattr(driver, "page_source", None) or "").lower()
        return (
            'type="password"' in src
            and ("sign in" in src or "log in" in src or "username" in src or "login" in src)
        )
    except Exception:
        return False


def _wait_for_domain_access(
    driver: object,
    probe_url: str,
    *,
    timeout_seconds: int = 300,
    poll_frequency: float = 2.0,
    emit_fn=None,
    label: str = "",
) -> None:
    """Navigate to *probe_url* and wait until the page is NOT a login page.

    With SSO this usually returns immediately after the first poll.  If a
    second login is required the user can complete it manually in Chrome.
    """
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(probe_url)  # type: ignore[attr-defined]
    if emit_fn:
        emit_fn(f"waiting_for_access {label or probe_url}")

    WebDriverWait(driver, timeout_seconds, poll_frequency=poll_frequency).until(
        lambda d: not _is_login_page(d)
    )
    if emit_fn:
        emit_fn(f"access_confirmed {label or probe_url}")


def _scrape_ticket_detail(driver: object, ticket_url: str, *, wait_timeout: int = 15, job_id: str | None = None) -> dict[str, Any]:
    """Open a single ticket detail page and scrape every visible field.

    Returns a dict with:
      page_title   – browser tab title
      fields       – {normalised_label: value} for every labeled table row
      notes        – all textarea content joined (internal notes / next-action block)
      scrape_error – None on success, error string if the page failed
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    detail: dict[str, Any] = {
        "ticket_url": ticket_url,
        "page_title": "",
        "fields": {},
        "notes": None,
        "scrape_error": None,
    }
    try:
        driver.get(ticket_url)  # type: ignore[attr-defined]
        WebDriverWait(driver, wait_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        if _is_login_page(driver):
            # noc-tickets session expired mid-scrape — wait for the user to re-authenticate.
            # We must wait until Chrome is on noc-tickets.123.net AND not on a login page,
            # not just any non-login page (e.g. customers.cgi), to avoid a tight loop where
            # the wait fires on customers.cgi and we immediately get redirected to Keycloak again.
            LOGGER.warning(
                "ticket_detail_login_redirect url=%s current_url=%s — pausing for re-auth",
                ticket_url, driver.current_url,  # type: ignore[attr-defined]
            )
            if job_id:
                _scrape_emit(job_id, "waiting_for_noc_tickets_reauth", event="waiting_for_noc_tickets_login")
            try:
                reauth_wait = WebDriverWait(driver, SELENIUM_LOGIN_TIMEOUT_SECONDS, poll_frequency=3.0)
                reauth_wait.until(
                    lambda d: "noc-tickets.123.net" in (d.current_url or "").lower()
                    and not _is_login_page(d)
                )
                LOGGER.info("ticket_detail_reauth_ok url=%s", ticket_url)
                if job_id:
                    _scrape_emit(job_id, "noc_tickets_reauth_confirmed", event="noc_tickets_access_confirmed")
                # Re-navigate to the ticket now that auth is restored
                driver.get(ticket_url)  # type: ignore[attr-defined]
                WebDriverWait(driver, wait_timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                if _is_login_page(driver):
                    raise Exception("Still on login page after re-auth")
            except Exception as reauth_exc:
                detail["scrape_error"] = (
                    f"Re-authentication failed or timed out: {reauth_exc}"
                )
                LOGGER.warning("ticket_detail_reauth_failed url=%s error=%s", ticket_url, reauth_exc)
                return detail
        detail["page_title"] = (driver.title or "").strip()  # type: ignore[attr-defined]

        fields: dict[str, str] = {}
        rows = driver.find_elements(By.XPATH, "//table//tr")  # type: ignore[attr-defined]
        for row in rows:
            cells = row.find_elements(By.XPATH, ".//td | .//th")
            if len(cells) < 2:
                continue
            raw_label = (cells[0].text or "").strip().rstrip(":").strip()
            if not raw_label or len(raw_label) > 80:
                continue
            value = ""
            try:
                inputs = cells[1].find_elements(
                    By.XPATH, ".//input[@type!='hidden'] | .//select | .//textarea"
                )
                if inputs:
                    el = inputs[0]
                    tag = el.tag_name.lower()
                    if tag == "select":
                        try:
                            value = Select(el).first_selected_option.text.strip()
                        except Exception:
                            value = (el.text or "").strip()
                    elif tag == "input":
                        itype = (el.get_attribute("type") or "").lower()
                        if itype == "checkbox":
                            value = "yes" if el.is_selected() else "no"
                        else:
                            value = (el.get_attribute("value") or "").strip()
                    else:  # textarea
                        value = (el.get_attribute("value") or el.text or "").strip()
                else:
                    value = (cells[1].text or "").strip()
            except Exception:
                value = (cells[1].text or "").strip()
            key = re.sub(r"[^a-z0-9]+", "_", raw_label.lower()).strip("_")
            if key:
                fields[key] = value
        detail["fields"] = fields

        notes_parts: list[str] = []
        for ta in driver.find_elements(By.XPATH, "//textarea"):  # type: ignore[attr-defined]
            content = (ta.get_attribute("value") or ta.text or "").strip()
            if content:
                notes_parts.append(content)
        if notes_parts:
            detail["notes"] = "\n\n---\n\n".join(notes_parts)

    except Exception as exc:
        detail["scrape_error"] = str(exc)
        LOGGER.warning("ticket_detail_scrape_failed url=%s error=%s", ticket_url, exc)

    return detail


# ── Main scrape job ───────────────────────────────────────────────────────────


def _run_scrape_job(
    job_id: str,
    handles: list[str],
    login_timeout_seconds: int,
    resume_from_handle: str | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
) -> None:
    from selenium import webdriver
    from selenium.common.exceptions import InvalidSessionIdException, TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.options import Options
    from webscraper.auth.session import selenium_driver_to_requests_session, summarize_driver_cookies

    started_utc = _iso_now()
    result: dict[str, Any] = {
        "status_message": "launched_browser",
        "current_handle": None,
        "completed_handles": 0,
        "total_handles": len(handles),
        "ticket_count": 0,
        "handle_summaries": [],
        "output_files": {},
    }
    _update_scrape_job(
        job_id=job_id, status="running", completed=0, total=len(handles),
        started_utc=started_utc, result=result,
    )

    _is_windows = os.name == "nt"

    options = Options()
    if _is_windows:
        # Explicit binary candidates for Windows (Selenium can't always find Chrome in PATH)
        for candidate in (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ):
            if os.path.isfile(candidate):
                options.binary_location = candidate
                break
    else:
        for candidate in ("/opt/google/chrome/chrome", "/opt/google/chrome/google-chrome", "/usr/bin/google-chrome-stable"):
            if os.path.isfile(candidate):
                options.binary_location = candidate
                break
        # Linux-only flags (sandboxing, shared-memory, GPU workarounds)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

    options.add_argument("--start-maximized")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    # Use the persistent Chrome profile so saved cookies survive across scrape runs
    _chrome_profile_dir = (
        os.environ.get("WEBSCRAPER_CHROME_PROFILE_DIR")
        or os.environ.get("CHROME_USER_DATA_DIR")
        or str(Path(__file__).resolve().parents[4] / "webscraper" / "var" / "chrome-profile")
    )
    options.add_argument(f"--user-data-dir={_chrome_profile_dir}")
    options.add_argument("--profile-directory=Default")
    # Remove stale SingletonLock so Chrome doesn't exit immediately on startup
    _singleton_lock = Path(_chrome_profile_dir) / "SingletonLock"
    if _singleton_lock.exists() or _singleton_lock.is_symlink():
        try:
            _singleton_lock.unlink()
        except Exception:
            pass

    if _is_windows:
        # On Windows, skip the bundled chromedriver and let Selenium Manager
        # auto-download the correct version for the installed Chrome.
        # Chrome auto-updates frequently and the bundled exe goes stale quickly.
        _explicit_driver = os.getenv("WEBSCRAPER_CHROMEDRIVER_PATH", "")
        chromedriver_path = _explicit_driver if _explicit_driver and os.path.isfile(_explicit_driver) else None
    else:
        _chromedriver_candidates = [
            os.getenv("WEBSCRAPER_CHROMEDRIVER_PATH", ""),
            "/usr/local/bin/chromedriver",
            "/usr/bin/chromedriver",
            str(Path(__file__).resolve().parents[4] / "webscraper" / "chromedriver-win64" / "chromedriver-win64" / "chromedriver.exe"),
        ]
        chromedriver_path = next((p for p in _chromedriver_candidates if p and os.path.isfile(p)), None)

    if not _is_windows:
        os.environ.setdefault("DISPLAY", ":99")
    _display = os.environ.get("DISPLAY", "")
    _login_instruction = (
        "Log in in the Chrome window that just opened on your desktop. "
        "Do not use any other browser window."
        if _is_windows
        else (
            f"Connect via VNC to display {_display} and log in in the Chrome window "
            f"that opened automatically. Do not use any other browser or Chrome instance."
        )
    )
    driver = None
    scraped_rows: list[dict[str, str]] = []
    handle_summaries: list[dict[str, Any]] = []
    try:
        _scrape_emit(job_id, "launched_browser", event="launched_browser")
        from selenium.webdriver.chrome.service import Service as ChromeService
        svc = ChromeService(chromedriver_path) if chromedriver_path else None
        driver = webdriver.Chrome(service=svc, options=options) if svc else webdriver.Chrome(options=options)
        driver.get(CHROME_CUSTOMERS_URL)
        _scrape_emit(
            job_id,
            f"waiting_for_login — {_login_instruction}",
            event="waiting_for_login",
            data={
                "timeout_seconds": login_timeout_seconds,
                "display": _display or "desktop",
                "target_url": CHROME_CUSTOMERS_URL,
                "instruction": _login_instruction,
            },
        )

        login_wait = WebDriverWait(driver, login_timeout_seconds, poll_frequency=3.0)
        login_wait.until(
            lambda d: "secure.123.net" in (d.current_url or "").lower()
            and not _is_login_page(d)
        )
        _scrape_emit(job_id, "login_detected", event="login_detected")
        time.sleep(2)  # brief pause so the page settles before moving on
        cookie_summary = summarize_driver_cookies(driver, domains=["secure.123.net", ".123.net"])
        LOGGER.info(
            "scrape_cookie_count job_id=%s count=%s domains=%s",
            job_id, cookie_summary.get("count", 0), cookie_summary.get("domains", []),
        )
        _ = selenium_driver_to_requests_session(driver, base_url=CHROME_CUSTOMERS_URL)

        # ── Authenticate noc-tickets.123.net in the same window ─────────────────
        # Navigate the main window to noc-tickets, wait for the user to complete
        # the Keycloak login, then navigate back to customers.cgi.  Using a
        # separate tab causes InvalidSessionIdException when the SSO redirect
        # chain interferes with the ChromeDriver session.
        LOGGER.info("scrape_checking_noc_tickets_access job_id=%s", job_id)
        _scrape_emit(
            job_id,
            f"waiting_for_noc_tickets_login — Chrome is now navigating to noc-tickets.123.net "
            f"for a second login (Keycloak). Complete that login and Chrome will automatically "
            f"return to the customers page to begin scraping. You have {login_timeout_seconds} seconds.",
            event="waiting_for_noc_tickets_login",
            data={"url": NOC_TICKETS_BASE_URL, "timeout_seconds": login_timeout_seconds},
        )
        time.sleep(3)  # give the user a moment to read the message before Chrome navigates
        try:
            _wait_for_domain_access(
                driver,
                NOC_TICKETS_BASE_URL,
                timeout_seconds=login_timeout_seconds,
                poll_frequency=3.0,
                emit_fn=lambda msg: _scrape_emit(job_id, msg, event="noc_tickets_login_wait"),
                label="noc-tickets.123.net",
            )
            _scrape_emit(job_id, "noc_tickets_access_confirmed", event="noc_tickets_access_confirmed")
            LOGGER.info("scrape_noc_tickets_access_ok job_id=%s", job_id)
        except Exception as _noc_exc:
            LOGGER.warning("scrape_noc_tickets_check_skipped job_id=%s reason=%s", job_id, _noc_exc)
            _scrape_emit(job_id, f"noc_tickets_check_skipped: {_noc_exc}", event="noc_tickets_skipped")

        # Navigate back to customers.cgi and confirm the search box is ready.
        driver.get(CHROME_CUSTOMERS_URL)
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#customers"))
        )

        run_output_dir = kb_dir()
        seen_tickets: set[tuple[str, str, str]] = set()

        # Stable output paths — overwritten in-place after every handle
        summary_path = run_output_dir / "handle_summary.json"
        tickets_path = run_output_dir / "ticket_urls.json"
        details_path = run_output_dir / "ticket_details.json"
        state_path = run_output_dir / "scrape_state.json"

        # Resume: skip handles before (and including) the given handle.
        # resume_from_handle is always passed explicitly by the UI (from GET /api/scrape/state).
        # "Start Scrape" passes None → always a fresh start, no auto-read of state file.
        skip_until: str | None = resume_from_handle
        if skip_until:
            _scrape_emit(job_id, f"resuming_from {skip_until}", event="resuming_from",
                         data={"handle": skip_until})
            LOGGER.info("scrape_resuming job_id=%s from_handle=%s", job_id, skip_until)

        skipping = skip_until is not None

        def _flush_progress(last_completed: str | None = None) -> None:
            """Write current scraped data to disk so nothing is lost on interruption."""
            try:
                summary_path.write_text(
                    json.dumps(handle_summaries, indent=2, sort_keys=True), encoding="utf-8"
                )
                tickets_path.write_text(
                    json.dumps(scraped_rows, indent=2, sort_keys=True), encoding="utf-8"
                )
                flat_details = [
                    {**{k: v for k, v in row.items() if k != "detail"}, **(row.get("detail") or {})}
                    for row in scraped_rows
                ]
                details_path.write_text(
                    json.dumps(flat_details, indent=2, sort_keys=True), encoding="utf-8"
                )
                if last_completed:
                    state_path.write_text(
                        json.dumps(
                            {"last_completed_handle": last_completed, "updated_utc": _iso_now()},
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
            except Exception as flush_exc:
                LOGGER.warning("scrape_flush_failed error=%s", flush_exc)

        handle_list = list(handles)
        browser_crash_count = 0
        MAX_BROWSER_CRASHES = 3
        crash_retried: set[str] = set()
        hi = 0  # 0-based handle index
        _retry_after_crash = False  # set True when we restart browser; cleared each iteration

        _heartbeat: Any = None
        if os.getenv("CLIENT_MODE", "").strip() == "1":
            from webscraper.heartbeat import HeartbeatThread
            _heartbeat = HeartbeatThread()
            _heartbeat.update(status="scraping", job_id=job_id, handles_total=len(handle_list))
            _heartbeat.start()

        while hi < len(handle_list):
            if cancel_event is not None and cancel_event.is_set():
                result["status_message"] = "cancelled"
                _update_scrape_job(
                    job_id=job_id, status="cancelled",
                    completed=int(result.get("completed_handles") or 0),
                    total=len(handles), finished_utc=_iso_now(), result=result,
                )
                _scrape_emit(job_id, "cancelled", event="cancelled")
                return

            # Pause: block here between handles until unpaused or cancelled
            if pause_event is not None and pause_event.is_set():
                _scrape_emit(job_id, "paused — waiting for resume", event="paused")
                _update_scrape_job(
                    job_id=job_id, status="paused",
                    completed=int(result.get("completed_handles") or 0),
                    total=len(handles), result=result,
                )
                while pause_event.is_set():
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    time.sleep(0.5)
                if cancel_event is None or not cancel_event.is_set():
                    _scrape_emit(job_id, "resumed", event="resumed")
                    _update_scrape_job(
                        job_id=job_id, status="running",
                        completed=int(result.get("completed_handles") or 0),
                        total=len(handles), result=result,
                    )

            _retry_after_crash = False
            handle = handle_list[hi]
            idx = hi + 1  # 1-based for display/progress

            # Resume: skip handles before (and including) the resume point silently.
            # We do NOT emit a per-handle event here — with hundreds of handles to
            # skip and each emit making a remote network call, this would add
            # minutes of dead time before scraping starts.
            if skipping:
                if handle == skip_until:
                    skipping = False
                    _scrape_emit(job_id, f"resumed_at {handle}", handle=handle,
                                 event="resumed_at")
                hi += 1
                continue

            if _heartbeat is not None:
                _heartbeat.update(
                    current_handle=handle,
                    handles_done=hi,
                    handles_total=len(handle_list),
                    status="scraping",
                    job_id=job_id,
                )

            search_string = _scrape_search_string(handle)
            result.update({
                "status_message": f"scraping_handle {handle}",
                "current_handle": handle,
                "completed_handles": idx - 1,
            })
            _update_scrape_job(job_id=job_id, status="running", completed=idx - 1,
                               total=len(handle_list), result=result)
            _scrape_emit(job_id, f"scraping_handle {handle}", handle=handle,
                         event="scraping_handle", data={"index": idx, "total": len(handles)})

            handle_summary: dict[str, Any] = {
                "company_handle": handle,
                "search_string": search_string,
                "verified_handle": None,
                "ticket_count": 0,
                "status": "ok",
            }
            try:
                driver.get(f"{CHROME_CUSTOMERS_URL}?customer={quote_plus(search_string)}")
                wait = WebDriverWait(driver, 20)
                search_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#customers"))
                )
                search_input.click()
                search_input.send_keys(Keys.CONTROL + "a")
                search_input.send_keys(Keys.DELETE)
                search_input.send_keys(search_string)
                search_buttons = driver.find_elements(
                    By.XPATH,
                    "//input[@type='submit' and (contains(@value,'Search') or contains(@name,'search'))]",
                )
                if search_buttons:
                    search_buttons[0].click()
                else:
                    search_input.send_keys(Keys.ENTER)
                _scrape_emit(job_id, f"search_submitted {handle}", handle=handle,
                             event="search_submitted")

                verified_cell = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//th[normalize-space()='Company Handle:']/following-sibling::td[1]")
                    )
                )
                verified_handle = (verified_cell.text or "").strip().upper()
                handle_summary["verified_handle"] = verified_handle
                if verified_handle != handle:
                    mismatch_msg = f"Expected {handle} but found {verified_handle}"
                    handle_summary["status"] = "handle_mismatch"
                    handle_summary["error"] = mismatch_msg
                    handle_summaries.append(handle_summary)
                    _scrape_emit(job_id, f"handle_mismatch {handle} {mismatch_msg}", handle=handle,
                                 event="handle_mismatch")
                    hi += 1  # must advance before continue in a while loop
                    continue

                _scrape_emit(job_id, f"handle_verified {handle}", handle=handle,
                             event="handle_verified")
                toggle = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//a[contains(@class,'show_hide') and normalize-space()='Show/Hide Trouble Ticket Data']")
                    )
                )
                toggle.click()
                _scrape_emit(job_id, f"toggle_clicked {handle} — waiting for ticket table to load",
                             handle=handle, event="toggle_clicked")
                # Wait for #slideid5 to become visible — large handles (I11=11k rows) can take minutes
                WebDriverWait(driver, 300).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#slideid5"))
                )
                _scrape_emit(job_id, f"ticket_table_visible {handle}", handle=handle,
                             event="ticket_table_visible")

                rows = driver.find_elements(By.XPATH, TICKET_TABLE_ROW_XPATH)
                handle_tickets: list[dict[str, str]] = []
                for row in rows:
                    anchors = row.find_elements(By.XPATH, ".//td[1]//a[contains(@href,'/ticket/')]")
                    if not anchors:
                        continue
                    anchor = anchors[0]
                    href = (anchor.get_attribute("href") or "").strip()
                    label = (anchor.text or "").strip()
                    if "/new_ticket" in href or "Create Non-Circuit Ticket" in label or "Go To Trouble Ticket Script" in label:
                        continue
                    ticket_row = {
                        "company_handle": handle,
                        "ticket_id": label,
                        "ticket_url": href,
                        "subject": (row.find_element(By.XPATH, ".//td[2]").text or "").strip(),
                        "status": (row.find_element(By.XPATH, ".//td[3]").text or "").strip(),
                        "priority": (row.find_element(By.XPATH, ".//td[4]").text or "").strip(),
                        "created_on": (row.find_element(By.XPATH, ".//td[5]").text or "").strip(),
                    }
                    key = (handle, ticket_row["ticket_id"], ticket_row["ticket_url"])
                    if key in seen_tickets:
                        continue
                    seen_tickets.add(key)
                    handle_tickets.append(ticket_row)
                    scraped_rows.append(ticket_row)

                handle_summary["ticket_count"] = len(handle_tickets)
                first_five = [t["ticket_id"] for t in handle_tickets[:5]]
                _scrape_emit(
                    job_id,
                    f"scraped_tickets {handle} count={len(handle_tickets)}",
                    handle=handle,
                    event="scraped_tickets",
                    data={"count": len(handle_tickets), "first_ticket_ids": first_five},
                )
                LOGGER.info(
                    "scrape_ticket_rows handle=%s rows=%s first5=%s",
                    handle, len(handle_tickets), first_five,
                )

                # ── Open each ticket URL and scrape full detail ───────────────
                detail_errors = 0
                for tidx, ticket_row in enumerate(handle_tickets, start=1):
                    t_url = ticket_row.get("ticket_url", "")
                    if not t_url:
                        continue
                    _scrape_emit(
                        job_id,
                        f"scraping_ticket_detail {handle} {ticket_row['ticket_id']} ({tidx}/{len(handle_tickets)})",
                        handle=handle,
                        event="scraping_ticket_detail",
                        data={"ticket_id": ticket_row["ticket_id"], "index": tidx,
                              "total": len(handle_tickets)},
                    )
                    detail = _scrape_ticket_detail(driver, t_url, job_id=job_id)
                    ticket_row["detail"] = detail
                    if detail.get("scrape_error"):
                        detail_errors += 1
                        LOGGER.warning(
                            "ticket_detail_error handle=%s ticket=%s error=%s",
                            handle, ticket_row["ticket_id"], detail["scrape_error"],
                        )
                    else:
                        LOGGER.info(
                            "ticket_detail_ok handle=%s ticket=%s title=%r fields=%s",
                            handle, ticket_row["ticket_id"], detail.get("page_title"),
                            list(detail.get("fields", {}).keys()),
                        )

                _scrape_emit(
                    job_id,
                    f"ticket_details_complete {handle} scraped={len(handle_tickets) - detail_errors} errors={detail_errors}",
                    handle=handle,
                    event="ticket_details_complete",
                    data={"scraped": len(handle_tickets) - detail_errors, "errors": detail_errors},
                )
                handle_summary["detail_errors"] = detail_errors
                handle_summaries.append(handle_summary)

                # Persist scraped tickets to SQLite so KB search works
                try:
                    db.upsert_tickets_batch(db_path(), handle, handle_tickets)
                    db.update_handle_progress(
                        db_path(), handle,
                        status="ok",
                        last_updated_utc=_iso_now(),
                        ticket_count=len(handle_tickets),
                    )
                except Exception as db_exc:
                    LOGGER.warning("scrape_db_write_failed handle=%s error=%s", handle, db_exc)

            except (InvalidSessionIdException, WebDriverException, ConnectionError, OSError) as _wde:
                # Catch Selenium exceptions AND low-level connection errors (RemoteDisconnected,
                # ConnectionAbortedError, etc.) that indicate the Chrome process died.
                # Explicitly exclude HTTP-level errors (4xx/5xx from the remote ingest server)
                # — those are not Chrome crashes and should not trigger a browser restart.
                import requests as _requests_mod
                if isinstance(_wde, _requests_mod.exceptions.RequestException):
                    LOGGER.warning("scrape_remote_http_error handle=%s error=%s", handle, _wde)
                    hi += 1
                    continue
                crash_exc = _wde
                _msg = str(_wde).lower()
                _is_crash = (
                    isinstance(_wde, (InvalidSessionIdException, ConnectionError, OSError))
                    or "invalid session" in _msg
                    or "session deleted" in _msg
                    or "connection aborted" in _msg
                    or "remotedisconnected" in _msg
                    or "remote end closed" in _msg
                    or "chrome not reachable" in _msg
                )
                if not _is_crash:
                    # Non-crash WebDriverException — treat as normal handle failure
                    handle_summary["status"] = "failed"
                    handle_summary["error"] = str(crash_exc)
                    handle_summaries.append(handle_summary)
                    LOGGER.exception(
                        "scrape_handle_exception job_id=%s handle=%s error=%s",
                        job_id, handle, crash_exc,
                    )
                    _scrape_emit(job_id, f"handle_exception {handle}: {crash_exc}", handle=handle,
                                 event="handle_exception")
                else:
                    LOGGER.error(
                        "scrape_browser_crash job_id=%s handle=%s crash_count=%s error=%s",
                        job_id, handle, browser_crash_count, crash_exc,
                    )
                    if browser_crash_count < MAX_BROWSER_CRASHES and handle not in crash_retried:
                        crash_retried.add(handle)
                        browser_crash_count += 1
                        _scrape_emit(
                            job_id,
                            f"browser_crashed_restarting attempt={browser_crash_count}",
                            handle=handle,
                            event="browser_crashed",
                            data={"attempt": browser_crash_count},
                        )
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = webdriver.Chrome(service=svc, options=options) if svc else webdriver.Chrome(options=options)
                        driver.get(CHROME_CUSTOMERS_URL)
                        _scrape_emit(job_id, "waiting_for_login_after_crash", event="waiting_for_login",
                                     data={"timeout_seconds": login_timeout_seconds})
                        restart_wait = WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0)
                        restart_wait.until(
                            lambda d: "secure.123.net" in (d.current_url or "").lower()
                            and (
                                len(d.find_elements(By.CSS_SELECTOR, "#customers")) > 0
                                or len(d.find_elements(By.XPATH, "//th[normalize-space()='Company Handle:']")) > 0
                            )
                        )
                        _scrape_emit(job_id, "browser_restarted_login_detected", event="browser_restarted")
                        LOGGER.info("scrape_browser_restarted job_id=%s attempt=%s", job_id, browser_crash_count)
                        _retry_after_crash = True
                        # Retry this handle — do NOT increment hi
                        continue
                    # Exhausted retries: record failure and move on
                    handle_summary["status"] = "failed"
                    handle_summary["error"] = str(crash_exc)
                    handle_summaries.append(handle_summary)
                    _scrape_emit(job_id, f"handle_exception {handle}: {crash_exc}", handle=handle,
                                 event="handle_exception")
            except Exception as handle_exc:
                handle_summary["status"] = "failed"
                handle_summary["error"] = str(handle_exc)
                handle_summaries.append(handle_summary)
                LOGGER.exception(
                    "scrape_handle_exception job_id=%s handle=%s error=%s",
                    job_id, handle, handle_exc,
                )
                _scrape_emit(job_id, f"handle_exception {handle}: {handle_exc}", handle=handle,
                             event="handle_exception")
            finally:
                result.update({
                    "status_message": f"scraped_tickets {handle} count={handle_summary.get('ticket_count', 0)}",
                    "completed_handles": idx,
                    "current_handle": handle if hi + 1 < len(handle_list) else None,
                    "ticket_count": len(scraped_rows),
                    "handle_summaries": handle_summaries,
                    "output_dir": str(run_output_dir.resolve()),
                    "output_files": {
                        "handle_summary": str(summary_path.resolve()),
                        "tickets": str(tickets_path.resolve()),
                        "ticket_details": str(details_path.resolve()),
                    },
                })
                if not _retry_after_crash:
                    _flush_progress(last_completed=handle)
                else:
                    _flush_progress()  # don't advance last_completed; we're retrying
                _update_scrape_job(
                    job_id=job_id, status="running", completed=idx,
                    total=len(handle_list), result=result,
                )
            hi += 1

        _flush_progress()
        LOGGER.info("scrape_output summary=%s tickets=%s details=%s",
                    summary_path, tickets_path, details_path)

        result.update({
            "status_message": "completed",
            "current_handle": None,
            "completed_handles": len(handles),
            "ticket_count": len(scraped_rows),
            "handle_summaries": handle_summaries,
            "output_dir": str(run_output_dir.resolve()),
            "output_files": {
                "handle_summary": str(summary_path.resolve()),
                "tickets": str(tickets_path.resolve()),
                "ticket_details": str(details_path.resolve()),
            },
            "cookie_count": int(cookie_summary.get("count", 0)),
        })
        _update_scrape_job(
            job_id=job_id, status="completed", completed=len(handles),
            total=len(handles), finished_utc=_iso_now(), result=result,
        )
        _scrape_emit(job_id, "completed", event="completed",
                     data={"tickets": len(scraped_rows), "handles": len(handles)})

    except TimeoutException as exc:
        LOGGER.exception("scrape_login_timeout job_id=%s error=%s", job_id, exc)
        result["status_message"] = "failed"
        result["error"] = f"Manual login timeout after {login_timeout_seconds} seconds"
        _update_scrape_job(
            job_id=job_id, status="failed",
            completed=int(result.get("completed_handles") or 0),
            total=len(handles), finished_utc=_iso_now(),
            error_message=result["error"], result=result,
        )
        _scrape_emit(job_id, "failed", event="failed", data={"error": result["error"]})
    except Exception as exc:
        LOGGER.exception("scrape_job_error job_id=%s error=%s", job_id, exc)
        result["status_message"] = "failed"
        result["error"] = str(exc)
        _update_scrape_job(
            job_id=job_id, status="failed",
            completed=int(result.get("completed_handles") or 0),
            total=len(handles), finished_utc=_iso_now(),
            error_message=str(exc), result=result,
        )
        _scrape_emit(job_id, "failed", event="failed", data={"error": str(exc)})
    finally:
        _SCRAPE_CANCEL_EVENTS.pop(job_id, None)
        if _heartbeat is not None:
            _heartbeat.update(status="idle", job_id=None, current_handle=None)
            _heartbeat.stop()
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                LOGGER.warning("scrape_driver_quit_failed job_id=%s", job_id)


# Backward-compat alias
_run_selenium_fallback_scrape_job = _run_scrape_job


# ── Timeline helpers ──────────────────────────────────────────────────────────


def _extract_event_category(raw_text: str) -> tuple[str, float]:
    text = raw_text.lower()
    rules: list[tuple[str, tuple[str, ...], float]] = [
        ("phone_replacement", ("replace phone", "phone replacement", "rma", "replaced handset"), 0.9),
        ("provisioning_change", ("provision", "template change", "configuration update", "reprovision"), 0.8),
        ("queue_change", ("queue", "ring group", "call routing", "acd"), 0.75),
        ("voicemail_issue", ("voicemail", "vm issue", "mailbox"), 0.85),
        ("training_provided", ("training", "walked through", "explained to customer"), 0.75),
        ("awaiting_customer", ("awaiting customer", "waiting on customer", "pending customer"), 0.8),
        ("resolved", ("resolved", "closed", "fixed", "completed"), 0.9),
        ("follow_up", ("follow up", "follow-up", "called customer", "emailed customer"), 0.7),
    ]
    for category, needles, confidence in rules:
        if any(needle in text for needle in needles):
            return category, confidence
    if any(needle in text for needle in ("opened", "new ticket", "created")):
        return "ticket_opened", 0.7
    return "follow_up", 0.5


def _build_handle_timeline(
    handle: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tickets_payload = db.list_tickets(db_path(), handle=handle, page=1, page_size=1000, sort="oldest")
    ticket_rows = tickets_payload.get("items") if isinstance(tickets_payload, dict) else []
    events: list[dict[str, Any]] = []
    for row in ticket_rows:
        ticket_id = str(row.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        parts = [
            str(row.get("title") or ""), str(row.get("subject") or ""),
            str(row.get("status") or ""), str(row.get("raw_json") or ""),
        ]
        raw_text = " | ".join(part for part in parts if part).strip()
        category, confidence = _extract_event_category(raw_text)
        event_time = row.get("updated_utc") or row.get("created_utc") or row.get("opened_utc") or _iso_now()
        summary = str(row.get("title") or row.get("subject") or f"Ticket {ticket_id}")
        events.append({
            "handle": handle, "ticket_id": ticket_id, "category": category,
            "event_utc": event_time, "summary": summary,
            "raw_source_text": raw_text, "confidence": confidence,
        })
        if category != "ticket_opened":
            events.append({
                "handle": handle, "ticket_id": ticket_id, "category": "ticket_opened",
                "event_utc": row.get("created_utc") or event_time,
                "summary": f"Ticket opened: {summary}",
                "raw_source_text": raw_text, "confidence": 0.6,
            })

    timeline_rows = [
        {
            "event_utc": event.get("event_utc"),
            "category": event.get("category"),
            "title": str(event.get("summary") or ""),
            "details": event.get("raw_source_text"),
            "ticket_id": event.get("ticket_id"),
            "source_event_id": None,
        }
        for event in sorted(events, key=lambda item: str(item.get("event_utc") or ""))
    ]
    pattern_counts: dict[str, dict[str, Any]] = {}
    for event in events:
        category = str(event.get("category") or "follow_up")
        bucket = pattern_counts.setdefault(
            category, {"pattern": category, "count": 0, "last_seen_utc": None}
        )
        bucket["count"] += 1
        bucket["last_seen_utc"] = event.get("event_utc")
    patterns = sorted(
        pattern_counts.values(), key=lambda item: int(item.get("count") or 0), reverse=True
    )
    return events, timeline_rows, patterns


# ── Log API helpers ───────────────────────────────────────────────────────────


def _log_api_enabled() -> bool:
    raw = os.getenv("WEBSCRAPER_LOGS_ENABLED")
    if raw is None:
        raw = os.getenv("SCRAPER_ENABLE_LOG_API")
    if raw is not None:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    env_name = (
        os.getenv("ENV") or os.getenv("APP_ENV") or os.getenv("PYTHON_ENV") or "dev"
    ).strip().lower()
    return env_name in {"dev", "development", "local", "test"}


def _ensure_log_api_enabled(request: Request) -> None:
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    if not _log_api_enabled():
        raise HTTPException(
            status_code=403,
            detail={"error": "logs_disabled", "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"},
        )


def _resolve_log_file(name: str) -> Path:
    candidate = (LOG_DIR / name).resolve()
    if candidate.parent != LOG_DIR or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    return candidate


def _tail_file(path: Path, lines: int) -> list[str]:
    if lines <= 0:
        return []
    chunk_size = 8192
    data = bytearray()
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        file_size = fh.tell()
        while file_size > 0 and data.count(b"\n") <= lines:
            read_size = min(chunk_size, file_size)
            file_size -= read_size
            fh.seek(file_size)
            data = fh.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-lines:]


# ── Startup ───────────────────────────────────────────────────────────────────


def _startup_bootstrap() -> None:
    _client_mode = os.getenv("CLIENT_MODE", "").strip() == "1"
    if _client_mode:
        server = os.getenv("INGEST_SERVER_URL", "http://127.0.0.1:8788")
        LOGGER.info("startup CLIENT_MODE=1 ingest_server=%s", server)
    else:
        db.ensure_indexes(db_path())
        handles = load_handles()
        if handles:
            for handle in handles:
                db.ensure_handle_row(db_path(), handle)
        # Reap jobs left in running/queued state from a previous crashed session
        try:
            import sqlite3 as _sqlite3
            con = _sqlite3.connect(db_path())
            cur = con.execute(
                "UPDATE scrape_jobs SET status='failed', finished_utc=datetime('now')"
                " WHERE status IN ('running','queued')"
            )
            if cur.rowcount:
                LOGGER.warning("startup: reaped %d stale running/queued jobs", cur.rowcount)
            con.commit()
            con.close()
        except Exception as exc:
            LOGGER.warning("startup: could not reap stale jobs: %s", exc)
        stats = db.get_stats(db_path())
        LOGGER.info("startup db_path=%s handles=%s tickets=%s",
                    db_path(), stats.get("total_handles"), stats.get("total_tickets"))
    if not _has_python_multipart():
        LOGGER.warning(_missing_python_multipart_message())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup_bootstrap()
    yield


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Ticket History API", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register ingest routes so remote clients can POST scraped data to this server.
# Protected by X-Ingest-Key header (INGEST_API_KEY env var); localhost-only fallback.
from webscraper.ticket_api import ingest_routes as _ingest_routes  # noqa: E402
_ingest_routes.register(app, db, db_path)


@app.middleware("http")
async def request_context(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        LOGGER.info("request method=%s path=%s status=%s ms=%s",
                    request.method, request.url.path, response.status_code, duration_ms)
        return response
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        LOGGER.exception("request_failed method=%s path=%s ms=%s",
                         request.method, request.url.path, duration_ms)
        raise


# ── Pydantic models ───────────────────────────────────────────────────────────


class ScrapeStartRequest(BaseModel):
    resume_from_handle: str | None = None


class CancelScrapeRequest(BaseModel):
    job_id: str | None = None


# ── Job conversion helper ─────────────────────────────────────────────────────


def _job_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Map a scrape_jobs DB row to the API Job shape expected by the dashboard."""
    # In CLIENT_MODE=1, db_client proxies to the remote server which already
    # returns shaped data (current_state, records_found, etc.).  Pass it through
    # rather than re-mapping raw DB field names that don't exist on the response.
    if "current_state" in row:
        return row
    result = row.get("result") or {}
    return {
        "job_id": row.get("job_id", ""),
        "created_at": row.get("created_utc", ""),
        "started_at": row.get("started_utc"),
        "completed_at": row.get("finished_utc"),
        "current_state": row.get("status", "unknown"),
        "current_step": result.get("status_message", row.get("status", "unknown")),
        "records_found": int(row.get("progress_total") or 0),
        "records_written": int(row.get("progress_completed") or 0),
        "error_message": row.get("error_message"),
    }


# ── Session validity check ────────────────────────────────────────────────────

def _check_saved_session() -> dict[str, object]:
    """Return {valid, message} by probing secure.123.net with saved profile cookies."""
    import sqlite3 as _sqlite3
    import http.cookiejar as _cookiejar
    import urllib.request as _urllib_request

    profile_dir = os.environ.get("WEBSCRAPER_CHROME_PROFILE_DIR", "").strip()
    if not profile_dir:
        return {"valid": None, "message": "No Chrome profile configured — manual login required"}

    profile_path = (Path(profile_dir) if os.path.isabs(profile_dir)
                    else Path(__file__).resolve().parents[5] / profile_dir)
    cookie_db = profile_path / "Default" / "Cookies"
    if not cookie_db.exists():
        return {"valid": False, "message": "No saved session — trigger a scrape job and log in when Chrome opens"}

    try:
        # Copy to temp file (Chrome may lock the original)
        import shutil, tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(cookie_db, tmp_path)

        jar = _cookiejar.CookieJar()
        conn = _sqlite3.connect(tmp_path)
        rows = conn.execute(
            "SELECT host_key, name, value, path, expires_utc, is_secure FROM cookies "
            "WHERE host_key LIKE '%123.net%'"
        ).fetchall()
        conn.close()
        os.unlink(tmp_path)

        if not rows:
            return {"valid": False, "message": "No 123.net cookies in saved profile — run auth_session.sh"}

        # Quick HTTP probe using saved cookies
        opener = _urllib_request.build_opener(_urllib_request.HTTPCookieProcessor(jar))
        for host, name, value, path, _, secure in rows:
            ck = _cookiejar.Cookie(
                version=0, name=name, value=value, port=None, port_specified=False,
                domain=host.lstrip("."), domain_specified=True,
                domain_initial_dot=host.startswith("."),
                path=path, path_specified=True, secure=bool(secure),
                expires=None, discard=True, comment=None, comment_url=None, rest={},
            )
            jar.set_cookie(ck)

        req = _urllib_request.Request(
            "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp = opener.open(req, timeout=10)
        final_url = resp.geturl()
        if "secure.123.net" in final_url and "customers" in final_url:
            return {"valid": True, "message": "Session is active"}
        return {"valid": False, "message": f"Session redirected to {final_url} — re-auth required"}
    except Exception as exc:
        return {"valid": False, "message": f"Session check failed: {exc}"}


@app.get("/api/scrape/check-auth")
def api_check_auth():
    """Check whether the saved Chrome profile has a valid 123.net session."""
    return _check_saved_session()


# ── Scrape control endpoints ──────────────────────────────────────────────────


@app.post("/api/scrape/start")
def api_scrape_start_selenium(payload: ScrapeStartRequest | None = None):
    """Start (or resume) a Selenium scrape job.

    Accepts optional ``resume_from_handle`` to skip all handles up to and
    including the given handle.  If omitted, ``var/kb/scrape_state.json`` is
    checked automatically for the last completed handle.
    """
    handles = _load_scrape_handles()
    if not handles:
        raise HTTPException(status_code=400, detail="No handles available to scrape")
    resume = (payload.resume_from_handle if payload else None)
    now = _iso_now()
    job_id = str(uuid.uuid4())
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=None,
        mode="scrape",
        ticket_limit=None,
        status="queued",
        created_utc=now,
        handles=handles,
    )
    _append_event("info", "scrape_queued", job_id=job_id,
                  meta={"event": "queued", "handles": len(handles), "resume_from": resume})
    cancel_event = threading.Event()
    pause_event = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id] = pause_event
    threading.Thread(
        target=_run_scrape_job,
        kwargs={
            "job_id": job_id,
            "handles": handles,
            "login_timeout_seconds": SELENIUM_LOGIN_TIMEOUT_SECONDS,
            "resume_from_handle": resume,
            "cancel_event": cancel_event,
            "pause_event": pause_event,
        },
        daemon=True,
    ).start()
    return {
        "queued": True,
        "job_id": job_id,
        "handles_total": len(handles),
        "status": "queued",
        "resume_from_handle": resume,
    }


@app.post("/api/scrape/selenium_fallback")
def api_scrape_selenium_fallback():
    """Alias for /api/scrape/start kept for backward compatibility."""
    return api_scrape_start_selenium(None)


@app.get("/api/scrape/state")
def api_scrape_state():
    """Return the last completed handle and timestamp from var/kb/scrape_state.json."""
    state_path = kb_dir() / "scrape_state.json"
    if not state_path.exists():
        return {"last_completed_handle": None, "updated_utc": None}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read scrape state: {exc}") from exc


@app.post("/api/scrape/pause")
def api_scrape_pause(payload: CancelScrapeRequest | None = None):
    """Pause a running scrape job between handles."""
    job_id = payload.job_id if payload else None
    if job_id is None:
        rows = db.list_scrape_jobs(db_path(), limit=10)
        active = next((r for r in rows if (r.get("status") or "") in ("running", "queued")), None)
        if active is None:
            raise HTTPException(status_code=404, detail="No active scrape job found")
        job_id = active["job_id"]
    event = _SCRAPE_PAUSE_EVENTS.get(job_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No pausable job with id={job_id}")
    event.set()
    return {"job_id": job_id, "paused": True, "message": "Pause requested — job will pause after current handle."}


@app.post("/api/scrape/resume")
def api_scrape_resume(payload: CancelScrapeRequest | None = None):
    """Resume a paused scrape job."""
    job_id = payload.job_id if payload else None
    if job_id is None:
        rows = db.list_scrape_jobs(db_path(), limit=10)
        paused = next((r for r in rows if (r.get("status") or "") == "paused"), None)
        if paused is None:
            raise HTTPException(status_code=404, detail="No paused scrape job found")
        job_id = paused["job_id"]
    event = _SCRAPE_PAUSE_EVENTS.get(job_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No job with id={job_id}")
    event.clear()
    return {"job_id": job_id, "paused": False, "message": "Job resumed."}


@app.post("/api/scrape/smoke_test")
def api_scrape_smoke_test():
    """Run a quick end-to-end test scraping only the first 2 handles."""
    all_handles = _load_scrape_handles()
    if not all_handles:
        raise HTTPException(status_code=400, detail="No handles available to scrape")
    handles = all_handles[:2]
    now = _iso_now()
    job_id = str(uuid.uuid4())
    db.create_scrape_job(
        db_path(), job_id=job_id, handle=None, mode="smoke_test",
        ticket_limit=None, status="queued", created_utc=now, handles=handles,
    )
    _append_event("info", "smoke_test_queued", job_id=job_id,
                  meta={"event": "queued", "handles": len(handles)})
    cancel_event = threading.Event()
    pause_event = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id] = pause_event
    threading.Thread(
        target=_run_scrape_job,
        kwargs={
            "job_id": job_id,
            "handles": handles,
            "login_timeout_seconds": SELENIUM_LOGIN_TIMEOUT_SECONDS,
            "resume_from_handle": None,
            "cancel_event": cancel_event,
            "pause_event": pause_event,
        },
        daemon=True,
    ).start()
    return {"queued": True, "job_id": job_id, "handles_total": len(handles),
            "status": "queued", "mode": "smoke_test"}


@app.get("/api/doctor")
def api_doctor():
    """Run connectivity and environment checks, return a summary of pass/fail."""
    import requests as _req
    checks: dict[str, dict] = {}

    # VPN
    try:
        from webscraper.heartbeat import detect_vpn
        vpn_ok, vpn_ip = detect_vpn()
    except Exception:
        vpn_ok, vpn_ip = False, None
    checks["vpn"] = {
        "ok": vpn_ok,
        "detail": f"Connected — {vpn_ip}" if vpn_ok else "Not connected",
    }

    # Remote ingest server
    server = os.getenv("INGEST_SERVER_URL", "").rstrip("/")
    if server:
        try:
            r = _req.get(f"{server}/api/health", timeout=6)
            checks["remote_server"] = {"ok": r.ok, "detail": f"HTTP {r.status_code} — {server}"}
        except Exception as exc:
            checks["remote_server"] = {"ok": False, "detail": f"Unreachable — {exc}"}
    else:
        checks["remote_server"] = {"ok": False, "detail": "INGEST_SERVER_URL not set in .env"}

    # Chrome binary
    _is_windows = os.name == "nt"
    chrome_candidates = (
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ] if _is_windows else [
            "/opt/google/chrome/chrome",
            "/opt/google/chrome/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]
    )
    chrome_path = next((p for p in chrome_candidates if os.path.isfile(p)), None)
    checks["chrome"] = {
        "ok": bool(chrome_path),
        "detail": f"Found — {chrome_path}" if chrome_path else "Not found in standard locations",
    }

    # Chrome profile directory
    profile_dir = (
        os.environ.get("WEBSCRAPER_CHROME_PROFILE_DIR")
        or os.environ.get("CHROME_USER_DATA_DIR")
        or str(Path(__file__).resolve().parents[4] / "webscraper" / "var" / "chrome-profile")
    )
    profile_ok = os.path.isdir(profile_dir)
    checks["chrome_profile"] = {
        "ok": profile_ok,
        "detail": f"{'Exists' if profile_ok else 'Missing'} — {profile_dir}",
    }

    # Handle list
    try:
        handles = _load_scrape_handles()
        checks["handles"] = {"ok": bool(handles), "detail": f"{len(handles)} handles loaded"}
    except Exception as exc:
        checks["handles"] = {"ok": False, "detail": f"Load failed — {exc}"}

    # CLIENT_MODE env
    client_mode = os.getenv("CLIENT_MODE", "").strip() == "1"
    checks["client_mode"] = {
        "ok": client_mode,
        "detail": "CLIENT_MODE=1 — writes routed to remote server" if client_mode else "CLIENT_MODE not set — writing locally",
    }

    overall_ok = all(v["ok"] for v in checks.values())
    return {"ok": overall_ok, "checks": checks}


@app.post("/api/scrape/cancel")
def api_scrape_cancel(payload: CancelScrapeRequest | None = None):
    """Request graceful cancellation of a running scrape job.

    The job will stop after it finishes the current handle. If ``job_id`` is
    omitted the most-recent running or queued job is targeted.
    """
    job_id = payload.job_id if payload else None
    if job_id is None:
        rows = db.list_scrape_jobs(db_path(), limit=10)
        active = next(
            (r for r in rows if (r.get("status") or "") in ("running", "queued")), None
        )
        if active is None:
            raise HTTPException(status_code=404, detail="No active scrape job found")
        job_id = active["job_id"]

    event = _SCRAPE_CANCEL_EVENTS.get(job_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No cancellable job with id={job_id}")
    event.set()
    _scrape_emit(job_id, "cancel_requested", event="cancel_requested")
    return {"job_id": job_id, "message": "Cancellation requested — job will stop after current handle."}


# ── Job status endpoints ──────────────────────────────────────────────────────


@app.get("/api/jobs")
def api_jobs():
    rows = db.list_scrape_jobs(db_path(), limit=20)
    return {"items": [_job_row_to_api(r) for r in rows]}


@app.get("/api/jobs/{job_id}/events")
def api_scrape_job_events(job_id: str, limit: int = Query(default=50, ge=1, le=500)):
    """Return the last *limit* events for a scrape job as JSON (non-streaming)."""
    rows = db.get_scrape_events(db_path(), job_id, limit=limit)
    return {"job_id": job_id, "events": rows}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    row = db.get_scrape_job(db_path(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_row_to_api(row)


@app.get("/jobs/{job_id}")
def job_status_alias(job_id: str):
    """Alias used by the Next.js proxy route /api/jobs/status/[jobId]."""
    row = db.get_scrape_job(db_path(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_row_to_api(row)


# ── Client heartbeat ─────────────────────────────────────────────────────────


class _ClientHeartbeatRequest(BaseModel):
    client_id: str
    status: str = "idle"
    vpn_connected: bool = False
    vpn_ip: str | None = None
    job_id: str | None = None
    current_handle: str | None = None
    handles_done: int | None = None
    handles_total: int | None = None


@app.post("/api/client/heartbeat")
def api_client_heartbeat(body: _ClientHeartbeatRequest):
    """Receive a heartbeat from a scraper client (GUI app on a laptop)."""
    ts = _iso_now()
    db.upsert_client_heartbeat(
        db_path(),
        client_id=body.client_id,
        status=body.status,
        vpn_connected=body.vpn_connected,
        vpn_ip=body.vpn_ip,
        job_id=body.job_id,
        current_handle=body.current_handle,
        handles_done=body.handles_done,
        handles_total=body.handles_total,
        ts_utc=ts,
    )
    return {"ok": True, "ts": ts}


@app.get("/api/clients")
def api_clients():
    """Return all known scraper clients and their latest heartbeat state."""
    rows = db.list_client_heartbeats(db_path())
    return {"items": rows}


# ── System / health ───────────────────────────────────────────────────────────


@app.get("/api/system/status")
def api_system_status():
    stats = db.get_stats(db_path())
    login_required = False
    try:
        latest_job = db.get_latest_scrape_job(db_path())
        if latest_job and latest_job.get("status") in ("running", "queued"):
            events = db.get_scrape_events(db_path(), latest_job["job_id"], limit=30)
            wait_idx = -1
            login_idx = -1
            for i, ev in enumerate(events):
                ev_name = (ev.get("data") or {}).get("event")
                if ev_name == "waiting_for_login":
                    wait_idx = i
                elif ev_name == "login_detected":
                    login_idx = i
            login_required = wait_idx > login_idx
    except Exception:
        pass
    return {
        "backend_health": "ok",
        "browser_status": "n/a",
        "auth_status": "n/a",
        "state": "idle",
        "login_required": login_required,
        "db_counts": {
            "tickets": int(stats.get("total_tickets", 0)),
            "handles": int(stats.get("total_handles", 0)),
        },
        "last_error": None,
    }


@app.get("/api/db/status")
def api_db_status():
    stats = db.get_stats(db_path())
    return {
        "tickets": int(stats.get("total_tickets", 0)),
        "handles": int(stats.get("total_handles", 0)),
    }


@app.get("/api/health")
@app.get("/health")
def api_health():
    stats = db.get_stats(db_path())
    return {
        "ok": True,
        "status": "ok",
        "version": app.version,
        "db_path": db_path(),
        "db_exists": Path(db_path()).exists(),
        "total_handles": int(stats.get("total_handles", 0)),
        "total_tickets": int(stats.get("total_tickets", 0)),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ── Handle / ticket data endpoints ────────────────────────────────────────────


@app.get("/api/handles")
@app.get("/handles")
def api_handles(
    q: str = "",
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = 0,
):
    items = db.list_handles(db_path(), q=q, limit=limit, offset=offset)
    return {"items": sorted(
        items,
        key=lambda item: item.get("last_updated_utc") or item.get("finished_utc") or "",
        reverse=True,
    )}


@app.get("/api/handles/summary")
def api_handles_summary(
    q: str = "",
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return db.list_handles_summary(db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    items = db.list_handle_names(db_path(), q=q, limit=limit)
    return {"items": items, "count": len(items)}


@app.get("/api/handles/{handle}/latest")
def api_handle_latest(handle: str):
    row = db.get_handle_latest(db_path(), handle)
    if not row:
        raise HTTPException(status_code=404, detail="Handle not found")
    return row


@app.get("/api/handles/{handle}/tickets")
def api_handle_tickets(handle: str, limit: int = 50, status: str = "any"):
    return db.list_tickets(db_path(), handle=handle, page=1, page_size=limit, status=status)


@app.get("/api/tickets")
def api_tickets(
    handle: str | None = None,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    pageSize: int = 50,
):
    return db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=pageSize)


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row["artifacts"] = db.get_artifacts(db_path(), row["ticket_id"], row["handle"])
    return row


@app.get("/api/kb/tickets")
def api_kb_tickets(
    q: str | None = None,
    handle: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    """Search KB tickets. Full-text search includes ticket notes stored in raw_json."""
    result = db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=page_size)
    items = []
    for ticket in result["items"]:
        notes_preview: str | None = None
        raw = ticket.get("raw_json")
        if raw:
            try:
                parsed = json.loads(raw)
                notes = parsed.get("detail", {}).get("notes") or parsed.get("notes")
                if notes:
                    notes_preview = str(notes)[:300]
            except Exception:
                pass
        items.append({**ticket, "notes_preview": notes_preview})
    return {**result, "items": items}


@app.get("/api/kb/tickets/{ticket_id}")
def api_kb_ticket(ticket_id: str, handle: str | None = None):
    """Return a single KB ticket with full detail and parsed notes."""
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    detail: dict[str, Any] = {}
    raw = row.get("raw_json")
    if raw:
        try:
            parsed = json.loads(raw)
            detail = parsed.get("detail") or {}
        except Exception:
            pass
    return {**row, "detail": detail, "notes": detail.get("notes"), "fields": detail.get("fields", {})}


@app.get("/api/kb/handles")
def api_kb_handles(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    """Return KB handle summary sorted by last scraped date."""
    rows = db.list_handles_summary(db_path(), q=q, limit=limit)
    return {"items": sorted(rows, key=lambda r: r.get("updated_latest_utc") or r.get("last_scrape_utc") or "", reverse=True)}


@app.get("/api/kb/export")
def api_kb_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    handle: str | None = None,
    q: str | None = None,
    status: str | None = None,
):
    """Bulk export of KB tickets as JSON or CSV."""
    result = db.list_tickets(db_path(), handle=handle, q=q, status=status, page=1, page_size=10000)
    items = result["items"]
    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        fields = ["ticket_id", "handle", "subject", "status", "created_utc", "updated_utc", "ticket_url"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow({k: item.get(k, "") for k in fields})
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=kb_tickets.csv"},
        )
    return {"items": items, "total": result["totalCount"]}


@app.get("/api/artifacts")
def api_artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


@app.get("/api/events/latest")
def api_events_latest(
    limit: int = Query(default=50, ge=1, le=500),
    job_id: str | None = None,
):
    items = db.get_latest_events(db_path(), limit=limit)
    if job_id:
        items = [item for item in items if (item.get("meta") or {}).get("job_id") == job_id]
        items = items[:limit]
    return {
        "items": [
            {
                "id": item.get("id"),
                "ts": item.get("created_utc"),
                "level": item.get("level"),
                "handle": item.get("handle"),
                "message": item.get("message"),
                "meta": item.get("meta"),
            }
            for item in items
        ]
    }


@app.get("/companies/{handle}")
def company_detail(handle: str):
    normalized = _normalize_handle(handle)
    company = db.get_company(db_path(), normalized) or {"handle": normalized}
    latest = db.get_handle_latest(db_path(), normalized) or {}
    return {"company": company, "latest": latest}


@app.get("/companies/{handle}/tickets")
def company_tickets(handle: str, limit: int = Query(default=200, ge=1, le=1000)):
    normalized = _normalize_handle(handle)
    return db.list_tickets(db_path(), handle=normalized, page=1, page_size=limit)


@app.get("/companies/{handle}/timeline")
def company_timeline(handle: str, limit: int = Query(default=500, ge=1, le=5000)):
    normalized = _normalize_handle(handle)
    rows = db.get_company_timeline(db_path(), normalized, limit=limit)
    return {"handle": normalized, "items": rows}


@app.post("/jobs/build-timeline")
def jobs_build_timeline(payload: dict[str, Any]):
    handle = _normalize_handle(str(payload.get("handle") or ""))
    now = _iso_now()
    events, timeline_rows, patterns = _build_handle_timeline(handle)
    db.upsert_company(db_path(), handle=handle, now_utc=now)
    event_count = db.replace_ticket_events(db_path(), handle, events, now)
    timeline_count = db.replace_company_timeline(db_path(), handle, timeline_rows, now)
    pattern_count = db.replace_resolution_patterns(db_path(), handle, patterns, now)
    return {
        "ok": True,
        "handle": handle,
        "ticket_events_written": event_count,
        "timeline_rows_written": timeline_count,
        "resolution_patterns_written": pattern_count,
        "categories": list(TIMELINE_CATEGORIES),
    }


@app.get("/api/companies/{handle}")
def api_company_detail(handle: str):
    return company_detail(handle)


@app.get("/api/companies/{handle}/tickets")
def api_company_tickets(handle: str, limit: int = Query(default=200, ge=1, le=1000)):
    return company_tickets(handle, limit=limit)


@app.get("/api/companies/{handle}/timeline")
def api_company_timeline(handle: str, limit: int = Query(default=200, ge=1, le=5000)):
    return company_timeline(handle, limit=limit)


@app.post("/api/jobs/build-timeline")
def api_jobs_build_timeline(payload: dict[str, Any]):
    return jobs_build_timeline(payload)


# ── Log API endpoints ─────────────────────────────────────────────────────────


@app.get("/api/logs/enabled")
def api_logs_enabled(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    return {"enabled": _log_api_enabled(), "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"}


@app.get("/api/logs/list")
def api_logs_list(request: Request):
    _ensure_log_api_enabled(request)
    items: list[dict[str, Any]] = []
    for path in sorted(LOG_DIR.glob("*.log*")):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append({
            "name": path.name,
            "size": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return {"items": items}


@app.get("/api/logs/tail")
def api_logs_tail(
    request: Request,
    name: str = Query(...),
    lines: int = Query(2000, ge=1, le=5000),
):
    _ensure_log_api_enabled(request)
    log_file = _resolve_log_file(name)
    rows = _tail_file(log_file, lines)
    return {"name": log_file.name, "lines": rows}


# ── Handle management endpoints ──────────────────────────────────────────────


class HandleAddRequest(BaseModel):
    handle: str


@app.post("/api/handles")
def api_handle_add(payload: HandleAddRequest, request: Request):
    """Add a new handle to the knowledge base."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Handle management is localhost-only")
    handle = _normalize_handle(payload.handle)
    db.ensure_handle_row(db_path(), handle)
    _append_event("info", f"handle_added handle={handle}")
    return {"handle": handle, "status": "added"}


@app.delete("/api/handles/{handle}")
def api_handle_delete(handle: str, request: Request):
    """Remove a handle and all its tickets from the knowledge base."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Handle management is localhost-only")
    handle = _normalize_handle(handle)
    deleted = db.delete_handle(db_path(), handle)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Handle {handle!r} not found")
    _append_event("info", f"handle_deleted handle={handle}")
    return {"handle": handle, "status": "deleted"}


# ── NOC Queue endpoints ───────────────────────────────────────────────────────


@app.get("/api/noc-queue/records")
def api_noc_queue_records(view: str | None = Query(None)):
    """Return cached NOC queue tickets. Optionally filter by view: hosted|noc|all|local."""
    db.ensure_indexes(db_path())
    return {"items": db.list_noc_queue_tickets(db_path(), view=view)}


class _NocQueueRefreshBody(BaseModel):
    view: str | None = None  # hosted | noc | all | local — omit to scrape all


@app.post("/api/noc-queue/refresh")
def api_noc_queue_refresh(body: _NocQueueRefreshBody, request: Request):
    """Start a background Selenium job to scrape NOC queue views. Returns job_id.

    Pass {"view": "hosted"} (etc.) to scrape a single view; omit for all views.
    """
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="NOC queue refresh is localhost-only")

    view_key = body.view or None
    mode = f"noc_queue:{view_key}" if view_key else "noc_queue"

    job_id = str(uuid.uuid4())
    now = _iso_now()
    db.ensure_indexes(db_path())
    db.create_scrape_job(
        db_path(), job_id=job_id, handle=None, mode=mode,
        ticket_limit=None, status="queued", created_utc=now,
    )
    _append_event("info", f"noc_queue_refresh_queued view={view_key or 'all'}", job_id=job_id)

    cancel_event = threading.Event()
    pause_event  = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id]  = pause_event

    def _run() -> None:
        from webscraper.noc_queue.scraper import fetch_noc_queues  # noqa: PLC0415

        login_timeout = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "300"))

        def _emit(msg: str) -> None:
            _append_event("info", f"noc_queue:{msg}", job_id=job_id)

        try:
            if cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                   finished_utc=_iso_now())
                _append_event("info", "noc_queue_cancelled_before_start", job_id=job_id)
                return
            # Honour pause before launching Chrome
            while pause_event.is_set():
                if cancel_event.is_set():
                    _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                       finished_utc=_iso_now())
                    return
                time.sleep(0.5)
            _update_scrape_job(job_id=job_id, status="running", completed=0, total=1,
                               started_utc=_iso_now())
            records = fetch_noc_queues(
                view_key=view_key,
                login_timeout_seconds=login_timeout,
                emit_fn=_emit,
            )
            finished = _iso_now()
            db.upsert_noc_queue_tickets(db_path(), records, finished)
            _update_scrape_job(job_id=job_id, status="done", completed=1, total=1,
                               finished_utc=finished,
                               result={"noc_queue_count": len(records)})
            _append_event("info", f"noc_queue_refresh_done count={len(records)}", job_id=job_id)
        except Exception as exc:
            LOGGER.exception("noc_queue_refresh_failed job_id=%s", job_id)
            _update_scrape_job(job_id=job_id, status="error", completed=0, total=1,
                               finished_utc=_iso_now(), error_message=str(exc))
        finally:
            _SCRAPE_CANCEL_EVENTS.pop(job_id, None)
            _SCRAPE_PAUSE_EVENTS.pop(job_id, None)

    threading.Thread(target=_run, daemon=True, name=f"noc-queue-{job_id[:8]}").start()
    return {"job_id": job_id, "status": "queued"}


# ── VPBX endpoints ───────────────────────────────────────────────────────────


@app.get("/api/vpbx/records")
def api_vpbx_records():
    """Return cached VPBX records from the database (no live scrape)."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_records(db_path())}


@app.post("/api/vpbx/refresh")
def api_vpbx_refresh(request: Request):
    """Start a background Selenium job to scrape vpbx.cgi. Returns job_id immediately."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="VPBX refresh is localhost-only")

    job_id = str(uuid.uuid4())
    now = _iso_now()
    db.ensure_indexes(db_path())
    db.create_scrape_job(
        db_path(), job_id=job_id, handle=None, mode="vpbx",
        ticket_limit=None, status="queued", created_utc=now,
    )
    _append_event("info", "vpbx_refresh_queued", job_id=job_id)

    cancel_event = threading.Event()
    pause_event  = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id]  = pause_event

    def _run() -> None:
        from webscraper.vpbx.handles import fetch_handles_selenium  # noqa: PLC0415

        base_url = (os.getenv("WEBSCRAPER_BASE_URL") or "https://secure.123.net").rstrip("/")
        login_timeout = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "300"))

        def _emit(msg: str) -> None:
            _append_event("info", f"vpbx:{msg}", job_id=job_id)

        try:
            if cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                   finished_utc=_iso_now())
                _append_event("info", "vpbx_cancelled_before_start", job_id=job_id)
                return
            while pause_event.is_set():
                if cancel_event.is_set():
                    _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                       finished_utc=_iso_now())
                    return
                time.sleep(0.5)
            _update_scrape_job(job_id=job_id, status="running", completed=0, total=1,
                               started_utc=_iso_now())
            records = fetch_handles_selenium(base_url, login_timeout_seconds=login_timeout,
                                             emit_fn=_emit)
            finished = _iso_now()
            db.upsert_vpbx_records(db_path(), records, finished)

            # Sync newly discovered handles into the handles table so the ticket
            # scraper automatically covers any handle that appears on vpbx.cgi.
            # upsert_discovered_handles is INSERT OR IGNORE / ON CONFLICT UPDATE —
            # existing handles are untouched; new ones are added.
            new_in_handles = db.upsert_discovered_handles(db_path(), records)
            _append_event("info", f"vpbx_handles_synced new={new_in_handles} total={len(records)}", job_id=job_id)

            _update_scrape_job(job_id=job_id, status="done", completed=1, total=1,
                               finished_utc=finished,
                               result={"vpbx_count": len(records), "handles_synced": new_in_handles})
            _append_event("info", f"vpbx_refresh_done count={len(records)}", job_id=job_id)
        except Exception as exc:
            LOGGER.exception("vpbx_refresh_failed job_id=%s", job_id)
            _update_scrape_job(job_id=job_id, status="error", completed=0, total=1,
                               finished_utc=_iso_now(), error_message=str(exc))
        finally:
            _SCRAPE_CANCEL_EVENTS.pop(job_id, None)
            _SCRAPE_PAUSE_EVENTS.pop(job_id, None)

    threading.Thread(target=_run, daemon=True, name=f"vpbx-refresh-{job_id[:8]}").start()
    return {"job_id": job_id, "status": "queued"}


class _VpbxDeviceConfigsRefreshBody(BaseModel):
    handles: list[str] | None = None  # limit to specific handles; omit for all
    force: bool = False               # True → ignore existing data, re-scrape everything
    incomplete_only: bool = False     # True → re-scrape devices with blank/single-line view_config


@app.get("/api/vpbx/device-configs")
def api_vpbx_device_configs(handle: str | None = Query(None)):
    """Return cached VPBX device configs. Filter by handle= to narrow results."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_device_configs(db_path(), handle=handle)}


class _SidecarSaveBody(BaseModel):
    vpbx_id: str
    sidecar_config: str  # full sidecar config text; pass "" to clear


@app.put("/api/vpbx/device-configs/{device_id}/sidecar")
def api_vpbx_save_sidecar(device_id: str, body: _SidecarSaveBody, request: Request):
    """Save or update the sidecar_config for a specific device.

    Only touches the sidecar_config column — never overwrites scraped data.
    Returns 404 if the device_id + vpbx_id combination doesn't exist yet.
    """
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Sidecar save is localhost-only")
    db.ensure_indexes(db_path())
    updated = db.save_sidecar_config(db_path(), device_id, body.vpbx_id, body.sidecar_config)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device {device_id}/{body.vpbx_id} not found")
    return {"status": "saved", "device_id": device_id, "vpbx_id": body.vpbx_id,
            "sidecar_length": len(body.sidecar_config)}


@app.post("/api/vpbx/device-configs/refresh")
def api_vpbx_device_configs_refresh(body: _VpbxDeviceConfigsRefreshBody, request: Request):
    """Start a Selenium job to scrape bulk device configs from vpbx.cgi.

    Navigation: vpbx.cgi → vpbx_detail per handle → edit_device per phone → Bulk Attribute Edit.
    Pass {"handles": ["ACG"]} to limit to one handle; omit for all.
    """
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="VPBX device config refresh is localhost-only")

    handles = [h.upper() for h in body.handles] if body.handles else None
    mode = f"vpbx_device_configs:{','.join(handles)}" if handles else "vpbx_device_configs"

    job_id = str(uuid.uuid4())
    now = _iso_now()
    db.ensure_indexes(db_path())
    db.create_scrape_job(
        db_path(), job_id=job_id, handle=None, mode=mode,
        ticket_limit=None, status="queued", created_utc=now,
    )
    _append_event("info", f"vpbx_device_configs_refresh_queued handles={handles or 'all'}", job_id=job_id)

    cancel_event = threading.Event()
    pause_event  = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id]  = pause_event

    def _run() -> None:
        from webscraper.vpbx.device_configs import fetch_device_configs  # noqa: PLC0415

        base_url = (os.getenv("WEBSCRAPER_BASE_URL") or "https://secure.123.net").rstrip("/")
        login_timeout = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "300"))

        def _emit(msg: str) -> None:
            _append_event("info", f"vpbx_device_configs:{msg}", job_id=job_id)

        # Build device-level existing config dict for comparison inside fetch_device_configs.
        # Keyed by (device_id, vpbx_id) → concatenation of all four stored config fields.
        # force=True: pass empty dict so every device is treated as new — no skipping.
        # incomplete_only=True: only treat devices with good multi-line configs as "existing";
        #   devices with blank or single-line view_config are treated as new (forced re-scrape).
        _KNOWN_PLACEHOLDERS = {"place holder text", "placeholder text", "placeholder"}

        def _is_incomplete(r: dict) -> bool:
            """Return True if this stored device has no usable config data.

            Considers a device incomplete if:
            - view_config is empty or a single line (no newline), AND
            - bulk_config is empty, a single line, or a known FreePBX placeholder, AND
            - arbitrary_attributes is empty.
            """
            vc = (r.get("view_config") or "").strip()
            bc = (r.get("bulk_config") or "").strip()
            aa = (r.get("arbitrary_attributes") or "").strip()
            vc_ok = bool(vc and "\n" in vc)
            bc_placeholder = bc.lower() in _KNOWN_PLACEHOLDERS
            bc_ok = bool(bc and "\n" in bc and not bc_placeholder)
            aa_ok = bool(aa)
            return not (vc_ok or bc_ok or aa_ok)

        if body.force:
            existing_configs: dict[tuple[str, str], str] = {}
            _emit("force=True — skipping comparison, all devices will be re-scraped")
        else:
            existing = db.list_vpbx_device_configs(db_path())
            incomplete_count = 0
            existing_configs = {}
            for _r in existing:
                if not (_r.get("device_id") and _r.get("vpbx_id")):
                    continue
                key = (str(_r["device_id"]), str(_r["vpbx_id"]))
                if body.incomplete_only and _is_incomplete(_r):
                    # Treat as missing — will be re-scraped
                    incomplete_count += 1
                    continue
                existing_configs[key] = "\n".join([
                    _r.get("device_properties") or "",
                    _r.get("arbitrary_attributes") or "",
                    _r.get("bulk_config") or "",
                    _r.get("view_config") or "",
                ])
            if body.incomplete_only:
                _emit(
                    f"incomplete_only=True — {incomplete_count} incomplete devices will be "
                    f"re-scraped, {len(existing_configs)} complete devices skipped"
                )
            elif existing_configs:
                _emit(f"loaded {len(existing_configs)} existing device configs for comparison")

        total_saved = 0

        def _on_handle_done(handle: str, records: list) -> None:
            nonlocal total_saved
            now = _iso_now()
            db.upsert_vpbx_device_configs(db_path(), records, now)
            total_saved += len(records)
            _update_scrape_job(job_id=job_id, status="running",
                               completed=total_saved, total=total_saved + 1)
            # Pause/cancel checkpoint between handles
            while pause_event.is_set() and not cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="paused",
                                   completed=total_saved, total=total_saved + 1)
                time.sleep(0.5)
            if cancel_event.is_set():
                raise InterruptedError("cancelled")
            if pause_event.is_set() is False:
                _update_scrape_job(job_id=job_id, status="running",
                                   completed=total_saved, total=total_saved + 1)

        try:
            if cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                   finished_utc=_iso_now())
                _append_event("info", "vpbx_device_configs_cancelled_before_start", job_id=job_id)
                return
            while pause_event.is_set():
                if cancel_event.is_set():
                    _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                       finished_utc=_iso_now())
                    return
                time.sleep(0.5)
            _update_scrape_job(job_id=job_id, status="running", completed=0, total=1,
                               started_utc=_iso_now())
            records = fetch_device_configs(
                base_url,
                handles=handles,
                existing_configs=existing_configs,
                on_handle_done=_on_handle_done,
                login_timeout_seconds=login_timeout,
                emit_fn=_emit,
            )
            finished = _iso_now()
            _update_scrape_job(job_id=job_id, status="done", completed=len(records), total=len(records),
                               finished_utc=finished,
                               result={"device_count": len(records)})
            _append_event("info", f"vpbx_device_configs_done count={len(records)}", job_id=job_id)
        except InterruptedError:
            _update_scrape_job(job_id=job_id, status="cancelled", completed=total_saved,
                               total=total_saved, finished_utc=_iso_now())
            _append_event("info", f"vpbx_device_configs_cancelled saved={total_saved}", job_id=job_id)
        except Exception as exc:
            LOGGER.exception("vpbx_device_configs_failed job_id=%s", job_id)
            _update_scrape_job(job_id=job_id, status="error", completed=total_saved, total=total_saved,
                               finished_utc=_iso_now(), error_message=str(exc))
        finally:
            _SCRAPE_CANCEL_EVENTS.pop(job_id, None)
            _SCRAPE_PAUSE_EVENTS.pop(job_id, None)

    threading.Thread(target=_run, daemon=True, name=f"vpbx-devconf-{job_id[:8]}").start()
    return {"job_id": job_id, "status": "queued"}


# ── VPBX site-config endpoints ────────────────────────────────────────────────


class _VpbxSiteConfigsRefreshBody(BaseModel):
    handles: list[str] | None = None  # limit to specific handles; omit for all


@app.get("/api/vpbx/site-configs")
def api_vpbx_site_configs(handle: str | None = Query(None)):
    """Return cached VPBX site configs. Filter by handle= to narrow results."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_site_configs(db_path(), handle=handle)}


@app.get("/api/vpbx/site-configs/{handle}")
def api_vpbx_site_config_by_handle(handle: str):
    """Return site config for a single handle. 404 if not yet scraped."""
    db.ensure_indexes(db_path())
    h = _normalize_handle(handle)
    items = db.list_vpbx_site_configs(db_path(), handle=h)
    if not items:
        raise HTTPException(status_code=404, detail=f"No site config found for handle {h}")
    return items[0]


@app.post("/api/vpbx/site-configs/refresh")
def api_vpbx_site_configs_refresh(body: _VpbxSiteConfigsRefreshBody, request: Request):
    """Start a Selenium job to scrape site-specific configs from vpbx.cgi.

    Navigation: vpbx.cgi list → vpbx_detail per handle → click Site Specific Config button.
    Pass {"handles": ["ACG"]} to limit to one handle; omit for all.
    """
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="VPBX site config refresh is localhost-only")

    handles = [h.upper() for h in body.handles] if body.handles else None
    mode = f"vpbx_site_configs:{','.join(handles)}" if handles else "vpbx_site_configs"

    job_id = str(uuid.uuid4())
    now = _iso_now()
    db.ensure_indexes(db_path())
    db.create_scrape_job(
        db_path(), job_id=job_id, handle=None, mode=mode,
        ticket_limit=None, status="queued", created_utc=now,
    )
    _append_event("info", f"vpbx_site_configs_refresh_queued handles={handles or 'all'}", job_id=job_id)

    cancel_event = threading.Event()
    pause_event  = threading.Event()
    _SCRAPE_CANCEL_EVENTS[job_id] = cancel_event
    _SCRAPE_PAUSE_EVENTS[job_id]  = pause_event

    def _run() -> None:
        from webscraper.vpbx.device_configs import fetch_site_configs  # noqa: PLC0415

        base_url = (os.getenv("WEBSCRAPER_BASE_URL") or "https://secure.123.net").rstrip("/")
        login_timeout = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "300"))

        def _emit(msg: str) -> None:
            _append_event("info", f"vpbx_site_configs:{msg}", job_id=job_id)

        # Build handle-level existing config dict for comparison inside fetch_site_configs.
        # Keyed by handle (uppercase) → stored site_config text.
        # No handle-level pre-skip — every handle is visited so blank rows can be
        # backfilled and changed configs can be detected.
        existing = db.list_vpbx_site_configs(db_path())
        existing_configs: dict[str, str] = {
            (_r["handle"] or "").upper(): (_r.get("site_config") or "")
            for _r in existing
            if _r.get("handle")
        }
        if existing_configs:
            _emit(f"loaded {len(existing_configs)} existing site configs for comparison")

        total_saved = 0

        def _on_handle_done(h: str, records: list) -> None:
            nonlocal total_saved
            db.upsert_vpbx_site_configs(db_path(), records, _iso_now())
            total_saved += len(records)
            _update_scrape_job(job_id=job_id, status="running",
                               completed=total_saved, total=total_saved + 1)
            # Pause/cancel checkpoint between handles
            while pause_event.is_set() and not cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="paused",
                                   completed=total_saved, total=total_saved + 1)
                time.sleep(0.5)
            if cancel_event.is_set():
                raise InterruptedError("cancelled")
            if pause_event.is_set() is False:
                _update_scrape_job(job_id=job_id, status="running",
                                   completed=total_saved, total=total_saved + 1)

        try:
            if cancel_event.is_set():
                _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                   finished_utc=_iso_now())
                _append_event("info", "vpbx_site_configs_cancelled_before_start", job_id=job_id)
                return
            while pause_event.is_set():
                if cancel_event.is_set():
                    _update_scrape_job(job_id=job_id, status="cancelled", completed=0, total=1,
                                       finished_utc=_iso_now())
                    return
                time.sleep(0.5)
            _update_scrape_job(job_id=job_id, status="running", completed=0, total=1,
                               started_utc=_iso_now())
            records = fetch_site_configs(
                base_url,
                handles=handles,
                existing_configs=existing_configs,
                on_handle_done=_on_handle_done,
                login_timeout_seconds=login_timeout,
                emit_fn=_emit,
            )
            finished = _iso_now()
            _update_scrape_job(job_id=job_id, status="done", completed=len(records), total=len(records),
                               finished_utc=finished,
                               result={"site_config_count": len(records)})
            _append_event("info", f"vpbx_site_configs_done count={len(records)}", job_id=job_id)
        except InterruptedError:
            _update_scrape_job(job_id=job_id, status="cancelled", completed=total_saved,
                               total=total_saved, finished_utc=_iso_now())
            _append_event("info", f"vpbx_site_configs_cancelled saved={total_saved}", job_id=job_id)
        except Exception as exc:
            LOGGER.exception("vpbx_site_configs_failed job_id=%s", job_id)
            _update_scrape_job(job_id=job_id, status="error", completed=total_saved, total=total_saved,
                               finished_utc=_iso_now(), error_message=str(exc))
        finally:
            _SCRAPE_CANCEL_EVENTS.pop(job_id, None)
            _SCRAPE_PAUSE_EVENTS.pop(job_id, None)

    threading.Thread(target=_run, daemon=True, name=f"vpbx-siteconf-{job_id[:8]}").start()
    return {"job_id": job_id, "status": "queued"}


# ── CLI entry points ──────────────────────────────────────────────────────────


def run_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    reload: bool = False,
    db_override: str | None = None,
) -> None:
    if db_override:
        os.environ["TICKETS_DB_PATH"] = str(Path(db_override).resolve())
    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=host, port=port, reload=reload,
                proxy_headers=False)


def _pip_check_required_deps() -> list[tuple[str, str, bool]]:
    checks = [
        ("fastapi", "fastapi>=0.115.0"),
        ("uvicorn", "uvicorn[standard]>=0.30.0"),
        ("multipart", "python-multipart>=0.0.9"),
    ]
    return [
        (module, requirement, importlib.util.find_spec(module) is not None)
        for module, requirement in checks
    ]


def pip_check_command() -> int:
    missing = [(m, r) for m, r, ok in _pip_check_required_deps() if not ok]
    if not missing:
        print("[OK] All ticket API dependencies are installed.")
        return 0
    print("[FAIL] Missing required dependencies:")
    for module, requirement in missing:
        print(f"  - {module}: {requirement}")
    requirements = " ".join(r for _, r in missing)
    print(f"Install: {sys.executable} -m pip install {requirements}")
    return 1


def doctor_command() -> int:
    multipart_ok = _has_python_multipart()
    db_file = Path(db_path())
    db_ok = db_file.exists()
    table_ok = False
    table_error: str | None = None

    if db_ok:
        try:
            db.ensure_indexes(db_path())
            with sqlite3.connect(db_file) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='scrape_jobs'"
                ).fetchone()
                table_ok = bool(row and row[0] > 0)
        except Exception as exc:
            table_error = str(exc)

    if multipart_ok:
        print("[OK] python-multipart is installed.")
    else:
        print(f"[FAIL] {_missing_python_multipart_message()}", file=sys.stderr)

    if db_ok:
        print(f"[OK] Ticket DB path exists: {db_file}")
    else:
        print(f"[FAIL] Ticket DB path missing: {db_file}", file=sys.stderr)

    if table_ok:
        print("[OK] scrape_jobs table is ready.")
    else:
        msg = "scrape_jobs table check failed" if table_error else "scrape_jobs table missing"
        detail = f": {table_error}" if table_error else ""
        print(f"[FAIL] {msg}{detail}", file=sys.stderr)

    return 0 if multipart_ok and db_ok and table_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=db_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--doctor", action="store_true",
                        help="Validate API runtime dependencies and exit")
    parser.add_argument("--pip-check", action="store_true",
                        help="Print missing dependencies and pip install command")
    args = parser.parse_args()
    if args.pip_check:
        raise SystemExit(pip_check_command())
    if args.doctor:
        raise SystemExit(doctor_command())
    run_api(host=args.host, port=args.port, reload=args.reload, db_override=args.db)


if __name__ == "__main__":
    main()
