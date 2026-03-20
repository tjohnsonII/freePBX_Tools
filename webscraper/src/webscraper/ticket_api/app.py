from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from webscraper.lib.db_path import get_tickets_db_path
from webscraper.handles_loader import load_handles
from webscraper.auth.chrome_cookies import ChromeCookieError, load_cookies_from_profile
from webscraper.auth.chrome_profile import get_driver_reusing_profile
from webscraper.auth.chrome_cdp import ChromeCDPError, cdp_call, connect_browser_ws
from webscraper.auth.probe import probe_auth
from webscraper.auth.session import selenium_driver_to_requests_session, summarize_driver_cookies
from webscraper.auth.cookie_seeder import (
    DEFAULT_CDP_PORT,
    DEFAULT_DOMAINS,
    CookieSeedError,
    SeedResult,
    auth_doctor,
    browser_user_data_dir,
    cdp_availability,
    import_cookies_auto,
    is_cdp_origin_rejected,
    launch_debug_chrome,
    list_browser_profiles,
    resolve_chrome_user_data_dir,
    resolve_profile_name,
    seed_auto,
    seed_from_cdp,
    seed_from_disk,
)
from webscraper.ticket_api.auth import (
    dedupe_and_filter_expired,
    get_default_cookie_domain,
    get_target_domains,
    parse_cookies,
    parse_cookies_from_cookie_header,
    parse_cookies_from_json,
    parse_cookies_from_netscape,
)
from webscraper.ticket_api import auth_store
from webscraper.ticket_api.auth_manager import AuthManager, default_target_url
from webscraper.paths import kb_dir, runs_dir
from webscraper.ticket_api import db
from webscraper.vpbx.handles import VpbxConfig, fetch_handles
from webscraper.logging_config import LOG_DIR, setup_logging

from webscraper.ticket_api.schemas import (
    AuthSeedRequest,
    AuthState,
    BatchScrapeRequest,
    BrowserDetectRequest,
    BrowserImportRequest,
    HybridAuthRequest,
    ImportFromProfileRequest,
    ImportTextRequest,
    LaunchBrowserRequest,
    LaunchDebugChromeRequest,
    LaunchSeededRequest,
    QueueJob,
    ScrapeHandlesRequest,
    StartScrapeRequest,
    ValidateAuthRequest,
)
from webscraper.ticket_api.orchestration import (
    OrchestratorDeps,
    WebScraperOrchestrator,
)

SCRAPE_TIMEOUT_SECONDS = 3600
OUTPUT_ROOT = str((Path(__file__).resolve().parents[4] / "webscraper" / "var").resolve())
DEFAULT_TARGET_DOMAINS = get_target_domains()
CHROME_CUSTOMERS_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
NOC_TICKETS_BASE_URL = "https://noc-tickets.123.net"

# URL fragments that indicate the browser is on a login / SSO page.
_LOGIN_URL_MARKERS = ("login", "signin", "sign_in", "sso", "auth", "oauth", "keycloak", "saml")


def resolve_profile_dir(user_data_dir: str, profile: str) -> Path:
    """
    Resolve a Chrome profile directory correctly.
    Accepts:
      - "Default"
      - "Profile 1"
      - "1"
      - full absolute path
    """
    ud = Path(user_data_dir)
    p = (profile or "").strip()

    if p and Path(p).is_absolute() and Path(p).exists():
        return Path(p)

    if p.lower() == "default":
        return ud / "Default"

    if p.lower().startswith("profile "):
        return ud / p

    if p.isdigit():
        return ud / f"Profile {p}"

    return ud / p

LOGGER = setup_logging("ticket_api")

LOGIN_URL_HINTS = ("login", "signin", "sign-in", "oauth", "sso", "keycloak", "auth")
POST_LOGIN_SELECTORS = (
    "input[name='customer_name']",
    "select[name='customer_name']",
    "form[action*='customers.cgi']",
    "table",
)
SELENIUM_LOGIN_TIMEOUT_SECONDS = int(os.getenv("SELENIUM_FALLBACK_LOGIN_TIMEOUT_SECONDS", "300"))
TICKET_TABLE_ROW_XPATH = "//div[@id='slideid5']//table//tr[td[1]//a[contains(@href,'/ticket/')]]"


def _orchestrator_detect_browser() -> dict[str, Any]:
    return _detect_browser_session(browser="chrome", cdp_port=DEFAULT_CDP_PORT)


def _detect_browser_session(*, browser: str | None, cdp_port: int) -> dict[str, Any]:
    requested_browser = (browser or "chrome").strip().lower() or "chrome"
    LOGGER.info("browser_detect request browser=%s cdp_port=%s", requested_browser, cdp_port)
    try:
        profiles = list_browser_profiles(requested_browser)
    except ValueError as exc:
        LOGGER.warning("browser_detect unsupported browser=%s error=%s", requested_browser, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("browser_detect profile enumeration failed browser=%s", requested_browser)
        return {
            "available": False,
            "browser": requested_browser,
            "status": "browser_detection_failure",
            "message": f"Failed to enumerate {requested_browser} profiles: {exc}",
            "profiles": [],
            "cdp": {},
            "debug_browser_running": False,
            "secure_tab_open": False,
            "authenticated_session": False,
            "cookie_count": 0,
        }

    LOGGER.info(
        "browser_detect profile_enumeration browser=%s profile_count=%s profiles=%s",
        requested_browser,
        len(profiles),
        profiles,
    )
    cdp = cdp_availability(cdp_port, check_ws=False)
    debug_browser_running = bool(cdp.get("json_version_ok"))
    LOGGER.info(
        "browser_detect cdp_detection browser=%s cdp_status=%s cdp_error=%s debug_browser_running=%s",
        requested_browser,
        cdp.get("status"),
        cdp.get("error"),
        debug_browser_running,
    )
    live_session = _inspect_live_secure_session(cdp_port) if debug_browser_running else {
        "tabs": [],
        "secure_tabs": [],
        "preferred_tab": None,
        "cookies": [],
        "cookie_names": [],
        "cookie_error": None,
    }
    tabs = list(live_session.get("tabs") or [])
    secure_tabs = list(live_session.get("secure_tabs") or [])
    preferred_tab = live_session.get("preferred_tab") if isinstance(live_session.get("preferred_tab"), dict) else None
    tab_urls = [str(tab.get("url") or "") for tab in tabs]
    secure_tab_open = bool(secure_tabs)
    LOGGER.info(
        "browser_detect tab_enumeration browser=%s tab_count=%s secure_tab_open=%s",
        requested_browser,
        len(tab_urls),
        secure_tab_open,
    )

    detected_cookie_count = len(list(live_session.get("cookies") or []))
    auth_cookie_present = bool(live_session.get("auth_cookie_present"))
    authenticated_probe_ok = bool(live_session.get("authenticated_probe_ok"))
    authentication_checks = {
        "cookie_based_session_detection": auth_cookie_present,
        "authenticated_probe_detection": authenticated_probe_ok,
    }
    cookie_error = live_session.get("cookie_error")
    authenticated_session = auth_cookie_present or authenticated_probe_ok
    unauthenticated_reason = str(live_session.get("unauthenticated_reason") or "")
    if not unauthenticated_reason:
        unauthenticated_reason = _derive_unauthenticated_reason(
            secure_tab_found=secure_tab_open,
            cookie_error=cookie_error,
            cookie_count=detected_cookie_count,
            auth_cookie_present=auth_cookie_present,
            dom_login_marker_detected=((live_session.get("debug") or {}).get("dom_login_marker_detected") if isinstance(live_session.get("debug"), dict) else None),
            authenticated_probe_ok=authenticated_probe_ok,
        )
    LOGGER.info(
        "browser_detect secure_session browser=%s authenticated=%s cookie_count=%s auth_cookie_present=%s auth_probe_ok=%s cookie_error=%s unauthenticated_reason=%s",
        requested_browser,
        authenticated_session,
        detected_cookie_count,
        auth_cookie_present,
        authenticated_probe_ok,
        cookie_error or "-",
        unauthenticated_reason or "-",
    )

    status = "ready"
    message = "Debug browser detected with authenticated secure.123.net session."
    if not debug_browser_running:
        status = "no_debug_browser_running"
        message = f"No debug browser detected on 127.0.0.1:{cdp_port}."
    elif cookie_error:
        status = "cookie_extraction_failure"
        message = f"Detected debug browser but failed reading secure.123.net cookies: {cookie_error}"
    elif not secure_tab_open:
        status = "browser_wrong_tab_domain"
        message = "Debug browser is running, but no open tab is on secure.123.net."
    elif not authenticated_session:
        status = "no_authenticated_secure_session"
        message = f"Debug browser is running on secure.123.net, but authentication checks failed ({unauthenticated_reason or 'no_signal'})."

    return {
        "available": debug_browser_running or bool(profiles),
        "browser": requested_browser,
        "status": status,
        "message": message,
        "profiles": profiles,
        "profile_count": len(profiles),
        "cdp": cdp,
        "debug_browser_running": debug_browser_running,
        "tabs": {
            "count": len(tab_urls),
            "secure_tab_open": secure_tab_open,
            "urls": tab_urls[:10],
            "preferred_tab": preferred_tab,
            "secure_count": len(secure_tabs),
        },
        "secure_tab_open": secure_tab_open,
        "authenticated_session": authenticated_session,
        "cookie_count": detected_cookie_count,
        "cookie_error": cookie_error,
        "cookie_names": list(live_session.get("cookie_names") or []),
        "cookie_domains": list(live_session.get("cookie_domains") or []),
        "authentication_checks": authentication_checks,
        "authenticated_probe_ok": authenticated_probe_ok,
        "auth_cookie_present": auth_cookie_present,
        "unauthenticated_reason": unauthenticated_reason or None,
        "auth_detection_debug": live_session.get("debug"),
    }


def _orchestrator_seed_auth() -> dict[str, Any]:
    result = seed_auto(
        profile_dir=None,
        domains=DEFAULT_DOMAINS,
        profile_name=None,
        cdp_url_or_port=DEFAULT_CDP_PORT,
        browser="chrome",
    )
    return {
        "seeded": bool(len(result.cookies) > 0),
        "cookie_count": int(len(result.cookies)),
        "source": result.details.get("source") or result.mode_used,
        "mode_used": result.mode_used,
        "cookie_names": sorted({str(cookie.get("name") or "") for cookie in result.cookies if cookie.get("name")}),
    }


def _orchestrator_validate_auth() -> dict[str, Any]:
    probe = probe_auth(timeout_seconds=10)
    return {"authenticated": bool(probe.authenticated), "reason": probe.reason, "checks": [row.model_dump() for row in probe.checks]}


def _looks_like_login_page(url: str, page_source: str) -> bool:
    haystack = f"{url} {page_source}".lower()
    return any(hint in haystack for hint in LOGIN_URL_HINTS)


def _wait_for_post_login_ready(driver: Any, timeout_seconds: int = 300) -> str:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, timeout_seconds)
    for selector in POST_LOGIN_SELECTORS:
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return selector
        except Exception:
            continue
    raise TimeoutError(f"Timed out waiting for a post-login selector: {POST_LOGIN_SELECTORS}")


def _load_scrape_handles() -> list[str]:
    handles = [str(handle).strip().upper() for handle in load_handles() if str(handle).strip()]
    deduped = sorted(set(handles))
    LOGGER.info("scrape_handles_loaded count=%s", len(deduped))
    return deduped

# Keep old name as alias so any existing callers don't break
_load_selenium_fallback_handles = _load_scrape_handles


def _scrape_search_string(handle: str) -> str:
    return f"{handle}:company_data:handle:{handle}"

# Keep old name as alias
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

# Keep old name as alias
_update_selenium_fallback_job = _update_scrape_job


def _scrape_emit(job_id: str, message: str, *, handle: str | None = None, event: str | None = None, data: dict[str, Any] | None = None) -> None:
    _append_event("info", message, handle=handle, job_id=job_id, meta={"event": event or "progress", **(data or {})})

# Keep old name as alias
_selenium_fallback_emit = _scrape_emit


def _is_login_page(driver: object) -> bool:
    """Return True if the browser is currently showing a login / SSO page."""
    url = (getattr(driver, "current_url", None) or "").lower()
    if any(m in url for m in _LOGIN_URL_MARKERS):
        return True
    # Also check page source for common login-form signals
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

    If the session already covers the domain (common with SSO), this returns
    immediately after the first poll.  If a login is required, Chrome stays on
    the login page and the user can complete it manually.
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


def _scrape_ticket_detail(driver: object, ticket_url: str, *, wait_timeout: int = 15) -> dict[str, Any]:
    """Open a single ticket detail page and scrape every visible field.

    Returns a dict with:
      page_title   – browser tab title
      fields       – {normalised_label: value} for every labeled table row
      notes        – all textarea content joined (the internal notes / next-action block)
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
        # If we landed on a login page the session hasn't reached noc-tickets.123.net yet.
        # Surface this clearly instead of scraping a login form by mistake.
        if _is_login_page(driver):
            detail["scrape_error"] = (
                "Redirected to login page — session does not cover noc-tickets.123.net. "
                "Complete login and retry."
            )
            LOGGER.warning("ticket_detail_login_redirect url=%s current_url=%s", ticket_url, driver.current_url)  # type: ignore[attr-defined]
            return detail
        detail["page_title"] = (driver.title or "").strip()  # type: ignore[attr-defined]

        # ── Generic label → value extraction ──────────────────────────────────
        # Handles rows where the first cell is a label ("Status:", "Type:", …)
        # and the second cell contains either an <input>, <select>, <textarea>,
        # a checkbox, or plain text.
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

        # ── Internal notes / next-action textarea(s) ─────────────────────────
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


def _run_scrape_job(job_id: str, handles: list[str], login_timeout_seconds: int, resume_from_handle: str | None = None) -> None:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.options import Options

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
    _update_scrape_job(job_id=job_id, status="running", completed=0, total=len(handles), started_utc=started_utc, result=result)

    options = Options()
    options.add_argument("--start-maximized")
    driver = None
    scraped_rows: list[dict[str, str]] = []
    handle_summaries: list[dict[str, Any]] = []
    try:
        _scrape_emit(job_id, "launched_browser", event="launched_browser")
        driver = webdriver.Chrome(options=options)
        driver.get(CHROME_CUSTOMERS_URL)
        _scrape_emit(job_id, "waiting_for_login", event="waiting_for_login", data={"timeout_seconds": login_timeout_seconds})

        login_wait = WebDriverWait(driver, login_timeout_seconds, poll_frequency=1.0)
        login_wait.until(
            lambda d: "secure.123.net" in (d.current_url or "").lower()
            and (
                len(d.find_elements(By.CSS_SELECTOR, "#customers")) > 0
                or len(d.find_elements(By.XPATH, "//th[normalize-space()='Company Handle:']")) > 0
            )
        )
        _scrape_emit(job_id, "login_detected", event="login_detected")
        cookie_summary = summarize_driver_cookies(driver, domains=["secure.123.net", ".123.net"])
        LOGGER.info("scrape_cookie_count job_id=%s count=%s domains=%s", job_id, cookie_summary.get("count", 0), cookie_summary.get("domains", []))
        _ = selenium_driver_to_requests_session(driver, base_url=CHROME_CUSTOMERS_URL)

        # ── Verify noc-tickets.123.net is also accessible ─────────────────────
        # Ticket detail pages live on a different subdomain.  With SSO the first
        # login usually covers both, but if a second login is required the user
        # can complete it here before the batch starts.
        LOGGER.info("scrape_checking_noc_tickets_access job_id=%s", job_id)
        _scrape_emit(
            job_id,
            "checking_noc_tickets_access",
            event="checking_noc_tickets_access",
            data={"url": NOC_TICKETS_BASE_URL},
        )
        _wait_for_domain_access(
            driver,
            NOC_TICKETS_BASE_URL,
            timeout_seconds=login_timeout_seconds,
            emit_fn=lambda msg: _scrape_emit(job_id, msg, event="noc_tickets_login_wait"),
            label="noc-tickets.123.net",
        )
        _scrape_emit(job_id, "noc_tickets_access_confirmed", event="noc_tickets_access_confirmed")
        LOGGER.info("scrape_noc_tickets_access_ok job_id=%s", job_id)

        # Navigate back to the customers page so handle iteration starts cleanly
        driver.get(CHROME_CUSTOMERS_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#customers"))
        )

        run_output_dir = kb_dir()
        seen_tickets: set[tuple[str, str, str]] = set()

        # Stable output paths — overwritten in-place after every handle
        summary_path = run_output_dir / "handle_summary.json"
        tickets_path = run_output_dir / "ticket_urls.json"
        details_path = run_output_dir / "ticket_details.json"
        state_path = run_output_dir / "scrape_state.json"

        # Resume: skip handles we've already completed
        skip_until: str | None = resume_from_handle
        if skip_until is None and state_path.exists():
            try:
                saved_state = json.loads(state_path.read_text(encoding="utf-8"))
                skip_until = saved_state.get("last_completed_handle")
                if skip_until:
                    _scrape_emit(job_id, f"resuming_from {skip_until}", event="resuming_from", data={"handle": skip_until})
                    LOGGER.info("scrape_resuming job_id=%s from_handle=%s", job_id, skip_until)
            except Exception as state_exc:
                LOGGER.warning("scrape_state_read_failed error=%s", state_exc)

        skipping = skip_until is not None

        def _flush_progress(last_completed: str | None = None) -> None:
            """Write current scraped data to disk after every handle so nothing is lost on interruption."""
            try:
                summary_path.write_text(json.dumps(handle_summaries, indent=2, sort_keys=True), encoding="utf-8")
                tickets_path.write_text(json.dumps(scraped_rows, indent=2, sort_keys=True), encoding="utf-8")
                flat_details = [
                    {**{k: v for k, v in row.items() if k != "detail"}, **(row.get("detail") or {})}
                    for row in scraped_rows
                ]
                details_path.write_text(json.dumps(flat_details, indent=2, sort_keys=True), encoding="utf-8")
                if last_completed:
                    state_path.write_text(
                        json.dumps({"last_completed_handle": last_completed, "updated_utc": _iso_now()}, indent=2),
                        encoding="utf-8",
                    )
            except Exception as flush_exc:
                LOGGER.warning("scrape_flush_failed error=%s", flush_exc)

        for idx, handle in enumerate(handles, start=1):
            # Resume: skip handles before the resume point
            if skipping:
                if handle == skip_until:
                    skipping = False
                _scrape_emit(job_id, f"skipping_handle {handle}", handle=handle, event="skipping_handle")
                continue

            search_string = _scrape_search_string(handle)
            result.update({"status_message": f"scraping_handle {handle}", "current_handle": handle, "completed_handles": idx - 1})
            _update_scrape_job(job_id=job_id, status="running", completed=idx - 1, total=len(handles), result=result)
            _scrape_emit(job_id, f"scraping_handle {handle}", handle=handle, event="scraping_handle", data={"index": idx, "total": len(handles)})

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
                search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#customers")))
                search_input.click()
                search_input.send_keys(Keys.CONTROL + "a")
                search_input.send_keys(Keys.DELETE)
                search_input.send_keys(search_string)
                search_buttons = driver.find_elements(By.XPATH, "//input[@type='submit' and (contains(@value,'Search') or contains(@name,'search'))]")
                if search_buttons:
                    search_buttons[0].click()
                else:
                    search_input.send_keys(Keys.ENTER)
                _scrape_emit(job_id, f"search_submitted {handle}", handle=handle, event="search_submitted")

                verified_cell = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//th[normalize-space()='Company Handle:']/following-sibling::td[1]"))
                )
                verified_handle = (verified_cell.text or "").strip().upper()
                handle_summary["verified_handle"] = verified_handle
                if verified_handle != handle:
                    mismatch_msg = f"Expected {handle} but found {verified_handle}"
                    handle_summary["status"] = "handle_mismatch"
                    handle_summary["error"] = mismatch_msg
                    handle_summaries.append(handle_summary)
                    _scrape_emit(job_id, f"handle_mismatch {handle} {mismatch_msg}", handle=handle, event="handle_mismatch")
                    continue

                _scrape_emit(job_id, f"handle_verified {handle}", handle=handle, event="handle_verified")
                toggle = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@class,'show_hide') and normalize-space()='Show/Hide Trouble Ticket Data']"))
                )
                toggle.click()
                # Wait for #slideid5 to become visible (handles the case where there are zero tickets and no table)
                WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#slideid5"))
                )
                _scrape_emit(job_id, f"toggle_clicked {handle}", handle=handle, event="toggle_clicked")

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
                LOGGER.info("scrape_ticket_rows handle=%s rows=%s first5=%s", handle, len(handle_tickets), first_five)

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
                        data={"ticket_id": ticket_row["ticket_id"], "index": tidx, "total": len(handle_tickets)},
                    )
                    detail = _scrape_ticket_detail(driver, t_url)
                    ticket_row["detail"] = detail
                    if detail.get("scrape_error"):
                        detail_errors += 1
                        LOGGER.warning("ticket_detail_error handle=%s ticket=%s error=%s", handle, ticket_row["ticket_id"], detail["scrape_error"])
                    else:
                        LOGGER.info("ticket_detail_ok handle=%s ticket=%s title=%r fields=%s", handle, ticket_row["ticket_id"], detail.get("page_title"), list(detail.get("fields", {}).keys()))

                _scrape_emit(
                    job_id,
                    f"ticket_details_complete {handle} scraped={len(handle_tickets) - detail_errors} errors={detail_errors}",
                    handle=handle,
                    event="ticket_details_complete",
                    data={"scraped": len(handle_tickets) - detail_errors, "errors": detail_errors},
                )
                handle_summary["detail_errors"] = detail_errors
                handle_summaries.append(handle_summary)
            except Exception as handle_exc:
                handle_summary["status"] = "failed"
                handle_summary["error"] = str(handle_exc)
                handle_summaries.append(handle_summary)
                LOGGER.exception("scrape_handle_exception job_id=%s handle=%s error=%s", job_id, handle, handle_exc)
                _scrape_emit(job_id, f"handle_exception {handle}: {handle_exc}", handle=handle, event="handle_exception")
            finally:
                result.update(
                    {
                        "status_message": f"scraped_tickets {handle} count={handle_summary.get('ticket_count', 0)}",
                        "completed_handles": idx,
                        "current_handle": handle if idx < len(handles) else None,
                        "ticket_count": len(scraped_rows),
                        "handle_summaries": handle_summaries,
                        "output_dir": str(run_output_dir.resolve()),
                        "output_files": {
                            "handle_summary": str(summary_path.resolve()),
                            "tickets": str(tickets_path.resolve()),
                            "ticket_details": str(details_path.resolve()),
                        },
                    }
                )
                _flush_progress(last_completed=handle)
                _update_scrape_job(job_id=job_id, status="running", completed=idx, total=len(handles), result=result)

        _flush_progress()  # Final flush at job completion
        LOGGER.info("scrape_output summary=%s tickets=%s details=%s", summary_path, tickets_path, details_path)

        result.update(
            {
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
            }
        )
        _update_scrape_job(
            job_id=job_id,
            status="completed",
            completed=len(handles),
            total=len(handles),
            finished_utc=_iso_now(),
            result=result,
        )
        _scrape_emit(job_id, "completed", event="completed", data={"tickets": len(scraped_rows), "handles": len(handles)})
    except TimeoutException as exc:
        LOGGER.exception("scrape_login_timeout job_id=%s error=%s", job_id, exc)
        result["status_message"] = "failed"
        result["error"] = f"Manual login timeout after {login_timeout_seconds} seconds"
        _update_scrape_job(
            job_id=job_id,
            status="failed",
            completed=int(result.get("completed_handles") or 0),
            total=len(handles),
            finished_utc=_iso_now(),
            error_message=result["error"],
            result=result,
        )
        _scrape_emit(job_id, "failed", event="failed", data={"error": result["error"]})
    except Exception as exc:
        LOGGER.exception("scrape_job_error job_id=%s error=%s", job_id, exc)
        result["status_message"] = "failed"
        result["error"] = str(exc)
        _update_scrape_job(
            job_id=job_id,
            status="failed",
            completed=int(result.get("completed_handles") or 0),
            total=len(handles),
            finished_utc=_iso_now(),
            error_message=str(exc),
            result=result,
        )
        _scrape_emit(job_id, "failed", event="failed", data={"error": str(exc)})
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                LOGGER.warning("scrape_driver_quit_failed job_id=%s", job_id)


_run_selenium_fallback_scrape_job = _run_scrape_job


def _orchestrator_run_scrape(job_id: str) -> dict[str, Any]:
    handles = load_handles()
    selected = handles[: min(25, len(handles))]
    if not selected:
        raise RuntimeError("No handles available to scrape")
    now = _iso_now()
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=None,
        mode="selected",
        ticket_limit=25,
        status="queued",
        created_utc=now,
        handles=selected,
    )
    with JOB_QUEUE_LOCK:
        JOB_QUEUE.append(
            QueueJob(
                job_id=job_id,
                run_id=datetime.now(timezone.utc).strftime("orch_%Y%m%d_%H%M%S") + f"_{os.getpid()}",
                mode="selected",
                handle=None,
                handles=selected,
                rescrape=False,
                refresh_handles=False,
                scrape_mode="incremental",
                ticket_limit=25,
            )
        )

    deadline = time.monotonic() + SCRAPE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = db.get_scrape_job(db_path(), job_id)
        if not status:
            time.sleep(1)
            continue
        if status.get("status") == "completed":
            result = status.get("result") or {}
            found = int(result.get("completed_handles") or result.get("completed") or 0)
            return {"records_found": found, "raw_result": result}
        if status.get("status") == "failed":
            raise RuntimeError(status.get("error_message") or "scrape failed")
        time.sleep(1)
    raise RuntimeError("scrape timeout waiting for completion")


def _orchestrator_persist_records(job_id: str, scrape_result: dict[str, Any]) -> dict[str, Any]:
    job = db.get_scrape_job(db_path(), job_id) or {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    written = int(result.get("completed_handles") or result.get("completed") or scrape_result.get("records_found") or 0)
    return {"records_written": written}


def _orchestrator_db_status() -> dict[str, int]:
    stats = db.get_stats(db_path())
    return {"tickets": int(stats.get("total_tickets", 0)), "handles": int(stats.get("total_handles", 0))}


ORCHESTRATOR = WebScraperOrchestrator(
    deps=OrchestratorDeps(
        detect_browser=_orchestrator_detect_browser,
        seed_auth=_orchestrator_seed_auth,
        validate_auth=_orchestrator_validate_auth,
        run_scrape=_orchestrator_run_scrape,
        persist_records=_orchestrator_persist_records,
        db_status=_orchestrator_db_status,
    ),
    logger=LOGGER,
)


def _startup_bootstrap() -> None:
    db.ensure_indexes(db_path())
    _update_auth_state(
        authenticated=False,
        mode="startup",
        detail="Auth not validated yet",
        suggestion="Open Chrome using profile dir and login once",
    )
    handles = load_handles()
    if not handles:
        _log("No handles found from CSV or handles.txt.")
    else:
        for handle in handles:
            db.ensure_handle_row(db_path(), handle)
        _log(f"Loaded {len(handles)} handles.")
    stats = db.get_stats(db_path())
    _log(f"DB path: {db_path()}")
    _log(f"DB OK: handles={stats['total_handles']} tickets={stats['total_tickets']}")
    threading.Thread(target=_job_worker, daemon=True).start()
    threading.Thread(target=_auto_startup_chrome, daemon=True).start()
    threading.Thread(target=_cdp_login_watcher, daemon=True).start()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup_bootstrap()
    if not _has_python_multipart():
        _log(_missing_python_multipart_message())
    yield


app = FastAPI(title="Ticket History API", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


JOB_QUEUE: list[QueueJob] = []
JOB_QUEUE_LOCK = threading.Lock()
CURRENT_JOB_ID: str | None = None
LOCALHOST_ONLY = {"127.0.0.1", "::1"}
HANDLE_RE = re.compile(r"^[A-Za-z0-9]+$")
MAX_BATCH_HANDLES = 500


AUTH_STATE = AuthState()
AUTH_STATE_LOCK = threading.Lock()
AUTH_IMPORT_META: dict[str, Any] = {
    "active_source": "none",
    "last_import_method_attempted": None,
    "last_import_result": None,
    "last_validation_result": None,
    "source_context": {},
}
AUTH_IMPORT_META_LOCK = threading.Lock()


def _has_python_multipart() -> bool:
    return importlib.util.find_spec("multipart") is not None


def _missing_python_multipart_message() -> str:
    return f"Missing dependency python-multipart. Install: {sys.executable} -m pip install python-multipart"


def db_path() -> str:
    return get_tickets_db_path()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _normalize_handle(handle: str) -> str:
    normalized = (handle or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="handle is required")
    if not HANDLE_RE.match(normalized):
        raise HTTPException(status_code=400, detail="handle must be alphanumeric")
    return normalized


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


def _build_handle_timeline(handle: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tickets_payload = db.list_tickets(db_path(), handle=handle, page=1, page_size=1000, sort="oldest")
    ticket_rows = tickets_payload.get("items") if isinstance(tickets_payload, dict) else []
    events: list[dict[str, Any]] = []
    for row in ticket_rows:
        ticket_id = str(row.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        parts = [str(row.get("title") or ""), str(row.get("subject") or ""), str(row.get("status") or ""), str(row.get("raw_json") or "")]
        raw_text = " | ".join(part for part in parts if part).strip()
        category, confidence = _extract_event_category(raw_text)
        event_time = row.get("updated_utc") or row.get("created_utc") or row.get("opened_utc") or _iso_now()
        summary = str(row.get("title") or row.get("subject") or f"Ticket {ticket_id}")
        events.append(
            {
                "handle": handle,
                "ticket_id": ticket_id,
                "category": category,
                "event_utc": event_time,
                "summary": summary,
                "raw_source_text": raw_text,
                "confidence": confidence,
            }
        )
        if category != "ticket_opened":
            events.append(
                {
                    "handle": handle,
                    "ticket_id": ticket_id,
                    "category": "ticket_opened",
                    "event_utc": row.get("created_utc") or event_time,
                    "summary": f"Ticket opened: {summary}",
                    "raw_source_text": raw_text,
                    "confidence": 0.6,
                }
            )

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
        bucket = pattern_counts.setdefault(category, {"pattern": category, "count": 0, "last_seen_utc": None})
        bucket["count"] += 1
        bucket["last_seen_utc"] = event.get("event_utc")
    patterns = sorted(pattern_counts.values(), key=lambda item: int(item.get("count") or 0), reverse=True)
    return events, timeline_rows, patterns


def _log(msg: str, request_id: str | None = None, job_id: str | None = None) -> None:
    rid = f" requestId={request_id}" if request_id else ""
    jid = f" jobId={job_id}" if job_id else ""
    LOGGER.info("[%s]%s%s %s", _iso_now(), rid, jid, msg)


def _get_required_env() -> tuple[VpbxConfig | None, str | None]:
    base_url = (os.getenv("VPBX_BASE_URL") or "https://secure.123.net").strip()
    username = (os.getenv("VPBX_USERNAME") or "").strip()
    password = (os.getenv("VPBX_PASSWORD") or "").strip()
    missing = [name for name, value in [("VPBX_USERNAME", username), ("VPBX_PASSWORD", password)] if not value]
    if missing:
        return None, f"Missing required environment variables: {', '.join(missing)}"
    return VpbxConfig(base_url=base_url, username=username, password=password), None


def _append_event(level: str, message: str, *, handle: str | None = None, job_id: str | None = None, meta: dict[str, Any] | None = None) -> None:
    ts = _iso_now()
    db.add_event(db_path(), ts, level, handle, message, {"job_id": job_id, **(meta or {})})
    if job_id:
        db.add_scrape_event(db_path(), job_id, ts, level, "scrape.progress", message, {"handle": handle, **(meta or {})})
    _log(message, job_id=job_id)


def _is_localhost_request(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in LOCALHOST_ONLY


def _auth_meta_response(meta: dict[str, Any]) -> dict[str, Any]:
    count = int(meta.get("cookie_count") or meta.get("count") or 0)
    return {
        "ok": bool(meta.get("ok", True)),
        "reason": meta.get("reason"),
        "count": count,
        "cookie_count": count,
        "domains": meta.get("domains") or [],
        "domain_counts": meta.get("domain_counts") or [],
        "last_imported": meta.get("last_imported"),
        "source": meta.get("source") or "none",
    }


def _auth_state_payload() -> dict[str, Any]:
    with AUTH_STATE_LOCK:
        snapshot = {
            "authenticated": AUTH_STATE.authenticated,
            "mode": AUTH_STATE.mode,
            "detail": AUTH_STATE.detail,
            "last_check_ts": AUTH_STATE.last_check_ts,
            "last_error": AUTH_STATE.last_error,
            "profile_dir": AUTH_STATE.profile_dir,
            "suggestion": AUTH_STATE.suggestion,
        }
    with AUTH_IMPORT_META_LOCK:
        snapshot.update(
            {
                "active_source": AUTH_IMPORT_META.get("active_source"),
                "source_context": AUTH_IMPORT_META.get("source_context"),
                "last_import_method_attempted": AUTH_IMPORT_META.get("last_import_method_attempted"),
                "last_import_result": AUTH_IMPORT_META.get("last_import_result"),
                "last_validation_result": AUTH_IMPORT_META.get("last_validation_result"),
            }
        )
    return snapshot


def _update_auth_state(
    *,
    authenticated: bool,
    mode: str,
    detail: str,
    last_error: str | None = None,
    profile_dir: str | None = None,
    suggestion: str | None = None,
) -> None:
    with AUTH_STATE_LOCK:
        AUTH_STATE.authenticated = authenticated
        AUTH_STATE.mode = mode
        AUTH_STATE.detail = detail
        AUTH_STATE.last_check_ts = _iso_now()
        AUTH_STATE.last_error = last_error
        if profile_dir is not None:
            AUTH_STATE.profile_dir = profile_dir
        if suggestion is not None:
            AUTH_STATE.suggestion = suggestion


def _normalize_source_label(source: str) -> str:
    raw = str(source or "none").strip().lower()
    mapping = {
        "seed_cdp": "cdp_debug_chrome",
        "seed_cdp_auto": "cdp_debug_chrome",
        "seed_disk": "chrome_profile",
        "browser_disk": "chrome_profile",
        "browser_cdp": "cdp_debug_chrome",
        "seeded_profile": "isolated_profile",
        "paste": "paste",
        "none": "none",
    }
    if raw in mapping:
        return mapping[raw]
    if "edge" in raw:
        return "edge_profile"
    if "chrome" in raw and "cdp" not in raw:
        return "chrome_profile"
    if "isolated" in raw or "ticketing" in raw:
        return "isolated_profile"
    if "cdp" in raw or "debug" in raw:
        return "cdp_debug_chrome"
    return raw


def _record_auth_import_attempt(
    *,
    attempted: str,
    result: str,
    source: str,
    cookie_count: int,
    details: dict[str, Any] | None = None,
    overwritten_from: str | None = None,
) -> None:
    normalized_source = _normalize_source_label(source)
    context = dict(details or {})
    if overwritten_from:
        context["overwritten_from"] = _normalize_source_label(overwritten_from)
    with AUTH_IMPORT_META_LOCK:
        AUTH_IMPORT_META["last_import_method_attempted"] = attempted
        AUTH_IMPORT_META["last_import_result"] = {
            "result": result,
            "source": normalized_source,
            "cookie_count": int(cookie_count),
            "overwritten_from": context.get("overwritten_from"),
        }
        AUTH_IMPORT_META["active_source"] = normalized_source if result == "success" else AUTH_IMPORT_META.get("active_source", "none")
        AUTH_IMPORT_META["source_context"] = context


def _import_and_store_cookies(text_payload: str, *, source_label: str, filename: str, default_domain: str | None) -> dict[str, Any]:
    try:
        parsed, format_used = parse_cookies(text_payload, filename, default_domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not parsed:
        raise HTTPException(status_code=400, detail="Parsed 0 cookies from payload")

    kept, expired_dropped = dedupe_and_filter_expired(parsed)
    normalized_domains = {str(cookie.domain or "").strip().lstrip(".").lower() for cookie in kept if str(cookie.domain or "").strip()}

    target_hosts = {domain.strip().lstrip(".").lower() for domain in get_target_domains() if domain}
    if not target_hosts:
        target_hosts = {"secure.123.net", "123.net"}

    def _domain_matches_host(cookie_domain: str, host: str) -> bool:
        return cookie_domain == host or host.endswith(f".{cookie_domain}")

    has_target_domain = any(_domain_matches_host(cookie_domain, host) for cookie_domain in normalized_domains for host in target_hosts)
    if not has_target_domain:
        parsed_domains = sorted(normalized_domains)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "No target-domain cookies found in input.",
                "target_domains": sorted(target_hosts),
                "parsed_domains": parsed_domains,
            },
        )
    previous_status = auth_store.status(db_path())
    previous_source = str(previous_status.get("source") or "none")
    store_result = auth_store.replace_cookies(db_path(), [cookie.model_dump() for cookie in kept], source=source_label)
    overwritten_from = previous_source if previous_source not in {"none", source_label} else None
    status_payload = _auth_meta_response(auth_store.status(db_path()))
    _record_auth_import_attempt(
        attempted=source_label,
        result="success",
        source=source_label,
        cookie_count=int(store_result.get("accepted", len(kept))),
        details={"domains": status_payload.get("domains") or []},
        overwritten_from=overwritten_from,
    )
    _append_event(
        "info",
        f"Imported auth cookies count={len(kept)} expired_dropped={expired_dropped} source={source_label} filename={filename} domains={','.join(status_payload.get('domains', []))}",
    )
    return {
        "ok": True,
        **status_payload,
        "format_used": format_used,
        "filename": filename,
        "cookie_count": int(store_result.get("accepted", len(kept))),
        "accepted": int(store_result.get("accepted", len(kept))),
        "rejected": int(store_result.get("rejected", 0)),
        "expired_dropped": expired_dropped,
    }


AUTH_CHECK_URLS: list[str] = [
    "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
    "https://secure.123.net/cgi-bin/web_interface/admin/vpbx.cgi",
]
SECURE_DOMAIN = "secure.123.net"
AUTH_COOKIE_NAME_HINTS: tuple[str, ...] = (
    "sessionid",
    "session",
    "phpsessid",
    "jsessionid",
    "csrftoken",
    "xsrf",
    "auth",
    "token",
)

DEFAULT_TICKETING_TARGET_URL = (os.getenv("TICKETING_TARGET_URL") or os.getenv("TICKETING_LOGIN_URL") or "").strip()



def _sanitize_profile_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", (name or "").strip())
    return cleaned or "ticketing"


def _profile_dir(profile_name: str) -> Path:
    base_dir = Path(__file__).resolve().parents[4] / "webscraper" / "var" / "chrome_profiles"
    path = base_dir / _sanitize_profile_name(profile_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidate_browser_paths() -> list[Path]:
    program_files = os.getenv("ProgramFiles", r"C:\\Program Files")
    program_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\\Program Files (x86)")
    local_app_data = os.getenv("LOCALAPPDATA", "")
    return [
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]


def _detect_browser_path() -> Path:
    configured = (os.getenv("CHROME_PATH") or "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.exists() and configured_path.is_file():
            return configured_path
    for candidate in _candidate_browser_paths():
        if candidate.exists() and candidate.is_file():
            return candidate
    raise HTTPException(
        status_code=500,
        detail="Could not find Chrome/Edge. Set CHROME_PATH to your browser executable (for example chrome.exe).",
    )




AUTH_MANAGER = AuthManager(db_path_getter=db_path, browser_path_getter=_detect_browser_path, log_func=_log)

# ── Auto-Chrome / CDP login watcher ──────────────────────────────────────────
DEBUG_CHROME_PROC: subprocess.Popen | None = None
DEBUG_CHROME_PROC_LOCK = threading.Lock()
AUTO_SEED_LOCK = threading.Lock()
AUTO_LAUNCH_DEBUG_CHROME: bool = os.getenv("AUTO_LAUNCH_DEBUG_CHROME", "0").strip().lower() in {"1", "true", "yes", "on"}
AUTO_SEED_RETRY_BASE_SECONDS = 3
AUTO_SEED_RETRY_MAX_SECONDS = 60
AUTO_SEED_FATAL_COOLDOWN_SECONDS = 300
AUTO_SEED_STATE_LOCK = threading.Lock()
AUTO_SEED_STATE: dict[str, Any] = {
    "debug_browser_running": False,
    "cdp_attach_failed": False,
    "last_cdp_error": None,
    "auth_seed_in_progress": False,
    "last_seed_attempt_at": None,
    "next_seed_attempt_at": 0.0,
    "consecutive_seed_failures": 0,
    "fatal_cdp_error_at": None,
}


def _now_ts() -> float:
    return time.time()


def _is_fatal_cdp_attach_error(error_text: str | None, status: str | None = None) -> bool:
    lowered_status = str(status or "").strip().lower()
    if lowered_status in {"ws_origin_rejected", "origin_rejected"}:
        return True
    return is_cdp_origin_rejected(str(error_text or ""))


def _mark_cdp_attach_failure(*, error: str, fatal: bool) -> None:
    now_iso = _iso_now()
    now_ts = _now_ts()
    with AUTO_SEED_STATE_LOCK:
        AUTO_SEED_STATE["cdp_attach_failed"] = True
        AUTO_SEED_STATE["last_cdp_error"] = error
        if fatal:
            AUTO_SEED_STATE["fatal_cdp_error_at"] = now_iso
            AUTO_SEED_STATE["next_seed_attempt_at"] = now_ts + AUTO_SEED_FATAL_COOLDOWN_SECONDS
            AUTO_SEED_STATE["consecutive_seed_failures"] = max(1, int(AUTO_SEED_STATE.get("consecutive_seed_failures") or 0))


def _clear_cdp_attach_failure() -> None:
    with AUTO_SEED_STATE_LOCK:
        AUTO_SEED_STATE["cdp_attach_failed"] = False
        AUTO_SEED_STATE["last_cdp_error"] = None
        AUTO_SEED_STATE["fatal_cdp_error_at"] = None


def _set_seed_in_progress(in_progress: bool) -> None:
    with AUTO_SEED_STATE_LOCK:
        AUTO_SEED_STATE["auth_seed_in_progress"] = in_progress
        if in_progress:
            AUTO_SEED_STATE["last_seed_attempt_at"] = _iso_now()


def _record_seed_outcome(*, success: bool, error: str | None = None, fatal: bool = False) -> None:
    now_ts = _now_ts()
    with AUTO_SEED_STATE_LOCK:
        if success:
            AUTO_SEED_STATE["consecutive_seed_failures"] = 0
            AUTO_SEED_STATE["next_seed_attempt_at"] = now_ts
            AUTO_SEED_STATE["cdp_attach_failed"] = False
            AUTO_SEED_STATE["last_cdp_error"] = None
            AUTO_SEED_STATE["fatal_cdp_error_at"] = None
            return
        failures = int(AUTO_SEED_STATE.get("consecutive_seed_failures") or 0) + 1
        AUTO_SEED_STATE["consecutive_seed_failures"] = failures
        delay = min(AUTO_SEED_RETRY_MAX_SECONDS, AUTO_SEED_RETRY_BASE_SECONDS * (2 ** max(0, failures - 1)))
        AUTO_SEED_STATE["next_seed_attempt_at"] = now_ts + delay
        if error:
            AUTO_SEED_STATE["last_cdp_error"] = error
        if fatal:
            AUTO_SEED_STATE["cdp_attach_failed"] = True
            AUTO_SEED_STATE["fatal_cdp_error_at"] = _iso_now()
            AUTO_SEED_STATE["next_seed_attempt_at"] = now_ts + AUTO_SEED_FATAL_COOLDOWN_SECONDS


def _can_attempt_auto_seed() -> tuple[bool, str | None]:
    now_ts = _now_ts()
    with AUTO_SEED_STATE_LOCK:
        if bool(AUTO_SEED_STATE.get("auth_seed_in_progress")):
            return False, "seed_in_progress"
        next_at = float(AUTO_SEED_STATE.get("next_seed_attempt_at") or 0.0)
        if now_ts < next_at:
            return False, "retry_cooldown"
        if bool(AUTO_SEED_STATE.get("cdp_attach_failed")) and bool(AUTO_SEED_STATE.get("fatal_cdp_error_at")):
            return False, "fatal_cdp_attach_error"
    return True, None


def _is_login_like(payload: str) -> bool:
    lowered = payload.lower()
    return any(marker in lowered for marker in ["login", "sign in", "password", "username", "name=\"username\"", "name=\"password\""])


def _is_customers_page(url: str, payload: str) -> bool:
    lowered_url = (url or "").lower()
    if "customers.cgi" in lowered_url and "admin" in lowered_url:
        return True
    lowered_payload = (payload or "").lower()
    return "account search" in lowered_payload and "customers" in lowered_payload


def _validate_auth_targets(timeout_seconds: int = 10) -> dict[str, Any]:
    live_session = _inspect_live_secure_session(DEFAULT_CDP_PORT) if _is_cdp_available(DEFAULT_CDP_PORT) else {
        "tabs": [],
        "secure_tabs": [],
        "preferred_tab": None,
        "cookies": [],
        "cookie_names": [],
        "cookie_error": None,
    }
    secure_tab_found = bool(live_session.get("secure_tabs"))
    live_cookie_count = len(list(live_session.get("cookies") or []))
    live_auth_cookie_present = bool(live_session.get("auth_cookie_present"))
    live_authenticated_probe_ok = bool(live_session.get("authenticated_probe_ok"))
    live_unauthenticated_reason = str(live_session.get("unauthenticated_reason") or "")
    live_debug = live_session.get("debug") if isinstance(live_session.get("debug"), dict) else {}
    cookie_import_succeeded = False
    cookies = auth_store.load_cookies(db_path())
    required_cookie_names = AUTH_COOKIE_NAME_HINTS
    present_cookie_names = {str(cookie.get("name") or "").strip().lower() for cookie in cookies if cookie.get("name")}
    required_cookie_names_present = [name for name in required_cookie_names if name in present_cookie_names]
    missing_required_cookie_names = [name for name in required_cookie_names if name not in present_cookie_names]
    status_snapshot = auth_store.status(db_path())
    validation_probe_url = AUTH_CHECK_URLS[0] if AUTH_CHECK_URLS else None
    source = str(status_snapshot.get("source") or "none")
    source_browser = "chrome" if "chrome" in source else ("edge" if "edge" in source else None)
    profile_hint = os.getenv("CHROME_PROFILE_DIR") or os.getenv("BROWSER_PROFILE") or None

    if not cookies and live_cookie_count > 0:
        store_result = auth_store.replace_cookies(db_path(), list(live_session.get("cookies") or []), source="seed_cdp_validate")
        cookie_import_succeeded = bool(int(store_result.get("accepted", 0)) > 0)
        cookies = auth_store.load_cookies(db_path())
        present_cookie_names = {str(cookie.get("name") or "").strip().lower() for cookie in cookies if cookie.get("name")}
        required_cookie_names_present = [name for name in required_cookie_names if name in present_cookie_names]
        missing_required_cookie_names = [name for name in required_cookie_names if name not in present_cookie_names]
        _log(
            "auth_validate live_cookie_import "
            f"secure_tab_found={secure_tab_found} live_cookie_count={live_cookie_count} accepted={store_result.get('accepted', 0)}"
        )

    if not cookies:
        if not secure_tab_found:
            reason = "no_secure_tab_found"
        elif live_cookie_count == 0:
            reason = "no_cookies_returned"
        elif not live_auth_cookie_present:
            reason = "cookies_returned_but_no_auth_cookie_candidate"
        elif live_debug.get("dom_login_marker_detected") is True:
            reason = "dom_indicates_login_page"
        elif not live_authenticated_probe_ok:
            reason = "authenticated_probe_failed"
        else:
            reason = "secure_tab_found_not_logged_in"
        reasons = [{"code": "missing_cookie", "name": "*", "domain": "secure.123.net"}, {"code": "not_authenticated", "hint": "Import cookies from browser or login to debug profile"}]
        result_payload = {
            "ok": False,
            "authenticated": False,
            "reason": reason,
            "reasons": reasons,
            "checks": [],
            "details": {"domain": "secure.123.net", "checked": {"cookie_count": 0}},
            "validation_mode": "http_probe_with_cookie_inventory",
            "validation_reason": "missing_cookie",
            "source": source,
            "browser": source_browser,
            "profile": profile_hint,
            "cookie_count": 0,
            "domains": [],
            "required_cookie_names_present": required_cookie_names_present,
            "missing_required_cookie_names": missing_required_cookie_names,
            "validation_probe_url": validation_probe_url,
            "validation_http_status": None,
            "secure_tab_found": secure_tab_found,
            "live_cookie_count": live_cookie_count,
            "live_cookie_names": list(live_session.get("cookie_names") or []),
            "live_cookie_domains": list(live_session.get("cookie_domains") or []),
            "live_auth_cookie_present": live_auth_cookie_present,
            "live_authenticated_probe_ok": live_authenticated_probe_ok,
            "live_unauthenticated_reason": live_unauthenticated_reason or reason,
            "auth_detection_debug": live_debug,
            "cookie_import_succeeded": cookie_import_succeeded,
        }
        with AUTH_IMPORT_META_LOCK:
            AUTH_IMPORT_META["last_validation_result"] = {
                "authenticated": False,
                "reason": result_payload["reason"],
                "source": _normalize_source_label(source),
            }
        return result_payload

    timeout = max(2, int(timeout_seconds or 10))
    jar = requests.cookies.RequestsCookieJar()
    for cookie in cookies:
        jar.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path") or "/")

    checks: list[dict[str, Any]] = []
    for url in AUTH_CHECK_URLS:
        status = None
        final_url = url
        ok = False
        hint = None
        try:
            response = requests.get(url, cookies=jar, timeout=timeout, allow_redirects=True, verify=False)
            status = response.status_code
            final_url = response.url
            login_like = _is_login_like(response.text[:2500])
            on_customers_page = _is_customers_page(final_url, response.text[:6000])
            ok = status == 200 and not login_like and on_customers_page
            if not ok:
                if login_like:
                    hint = "redirected_to_login"
                elif status == 200 and not on_customers_page:
                    hint = "not_customers_page"
                elif status == 401:
                    hint = "missing_cookie"
                elif status == 403:
                    hint = "forbidden"
                else:
                    hint = "http_error"
        except Exception:
            hint = "exception"
        checks.append({"url": url, "status": status, "final_url": final_url, "ok": ok, "hint": hint})
        _log(f"auth_validate url={url} status={status} final_url={final_url} ok={ok} hint={hint or '-'}")

    overall_ok = all(item["ok"] for item in checks)
    reason = None
    if not overall_ok:
        if any((item.get("hint") or "").startswith("redirected_to_login") for item in checks):
            reason = "redirected_to_login"
        elif any((item.get("hint") or "") == "missing_cookie" for item in checks):
            reason = "missing_cookie"
        elif any((item.get("hint") or "") == "forbidden" for item in checks):
            reason = "forbidden"
        else:
            reason = "expired"
    if any((item.get("hint") or "") == "exception" for item in checks):
        reason = "exception"
    reasons: list[dict[str, Any]] = []
    for check in checks:
        if check.get("ok"):
            continue
        hint = check.get("hint") or "http_error"
        if hint in {"redirected_to_login"}:
            reasons.append({"code": "login_form_detected", "url": check.get("final_url") or check.get("url")})
        elif hint in {"missing_cookie"}:
            reasons.append({"code": "missing_cookie", "name": "session", "domain": "secure.123.net"})
        elif hint == "forbidden":
            reasons.append({"code": "forbidden", "url": check.get("url")})
        elif hint == "exception":
            reasons.append({"code": "request_exception", "url": check.get("url")})
        else:
            reasons.append({"code": "http_error", "url": check.get("url"), "status": check.get("status")})
    if not overall_ok and not reasons:
        reasons = [{"code": "not_authenticated", "hint": "Import cookies from browser or login to debug profile"}]
    if not overall_ok and not any(reason_item.get("code") == "not_authenticated" for reason_item in reasons):
        reasons.append({"code": "not_authenticated", "hint": "Import cookies from browser or login to debug profile"})
    request_test_succeeded = bool(overall_ok)
    request_test_failed = not request_test_succeeded
    result_payload = {
        "ok": overall_ok,
        "authenticated": overall_ok,
        "reason": reason,
        "reasons": reasons,
        "checks": checks,
        "details": {"domain": "secure.123.net", "checked": {"urls": AUTH_CHECK_URLS, "timeout_seconds": timeout}},
        "validation_mode": "http_probe_with_cookie_inventory",
        "validation_reason": "authenticated" if overall_ok else (reason or "not_authenticated"),
        "source": source,
        "browser": source_browser,
        "profile": profile_hint,
        "cookie_count": len(cookies),
        "domains": sorted({str(cookie.get("domain") or "") for cookie in cookies if cookie.get("domain")}),
        "required_cookie_names_present": required_cookie_names_present,
        "missing_required_cookie_names": missing_required_cookie_names,
        "validation_probe_url": validation_probe_url,
        "validation_http_status": next((item.get("status") for item in checks if item.get("status") is not None), None),
        "secure_tab_found": secure_tab_found,
        "live_cookie_count": live_cookie_count,
        "live_cookie_names": list(live_session.get("cookie_names") or []),
        "live_cookie_domains": list(live_session.get("cookie_domains") or []),
        "live_auth_cookie_present": live_auth_cookie_present,
        "live_authenticated_probe_ok": live_authenticated_probe_ok,
        "live_unauthenticated_reason": live_unauthenticated_reason or ("authenticated" if overall_ok else reason or "not_authenticated"),
        "auth_detection_debug": live_debug,
        "cookie_import_succeeded": cookie_import_succeeded,
        "authenticated_request_test_succeeded": request_test_succeeded,
        "authenticated_request_test_failed": request_test_failed,
        "secure_session_state": "secure_tab_found_and_cookies_present" if secure_tab_found and live_cookie_count > 0 else (
            "secure_tab_found_but_not_logged_in" if secure_tab_found else "no_secure_tab_found"
        ),
    }
    with AUTH_IMPORT_META_LOCK:
        AUTH_IMPORT_META["last_validation_result"] = {
            "authenticated": bool(result_payload.get("authenticated")),
            "reason": result_payload.get("reason"),
            "source": _normalize_source_label(source),
        }
    return result_payload


# ── CDP helpers ───────────────────────────────────────────────────────────────

def _is_cdp_available(port: int = DEFAULT_CDP_PORT) -> bool:
    """Return True if a debuggable Chrome is listening on *port*."""
    availability = cdp_availability(port, check_ws=False)
    return bool(availability.get("json_version_ok"))


def _cdp_diag(port: int = DEFAULT_CDP_PORT, *, check_ws: bool = True) -> dict[str, Any]:
    return cdp_availability(port, check_ws=check_ws)


def _get_cdp_tabs(port: int = DEFAULT_CDP_PORT) -> list[dict[str, Any]]:
    """Return all CDP page targets from /json without creating new tabs."""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/json", timeout=1.5)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    tabs: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "page") != "page":
            continue
        url = str(row.get("url") or "")
        title = str(row.get("title") or "")
        lowered_url = url.lower()
        matched_domain = SECURE_DOMAIN in lowered_url or lowered_url.endswith(".123.net")
        score = 0
        if matched_domain:
            score += 50
        if _url_is_post_login(url):
            score += 30
        if lowered_url == "about:blank":
            score -= 100
        if not url:
            score -= 10
        tabs.append(
            {
                "index": index,
                "id": row.get("id"),
                "url": url,
                "title": title,
                "matched_domain": matched_domain,
                "post_login": _url_is_post_login(url),
                "score": score,
            }
        )
    return tabs


def _get_cdp_tab_urls(port: int = DEFAULT_CDP_PORT) -> list[str]:
    return [str(tab.get("url") or "") for tab in _get_cdp_tabs(port)]


def _inspect_live_secure_session(cdp_port: int = DEFAULT_CDP_PORT) -> dict[str, Any]:
    tabs = _get_cdp_tabs(cdp_port)
    secure_tabs = [tab for tab in tabs if tab.get("matched_domain")]
    ranked = sorted(secure_tabs or tabs, key=lambda tab: int(tab.get("score") or 0), reverse=True)
    preferred_tab = ranked[0] if ranked else None
    rejection_reasons: list[str] = []
    for tab in tabs:
        url = str(tab.get("url") or "")
        title = str(tab.get("title") or "")
        matched_domain = bool(tab.get("matched_domain"))
        if not matched_domain:
            if url.lower() == "about:blank":
                rejection_reasons.append("about:blank")
            else:
                rejection_reasons.append("wrong_domain")
        LOGGER.info(
            "cdp_tab_check index=%s url=%r title=%r matched_domain=%s post_login=%s score=%s reject_reason=%s",
            tab.get("index"),
            url,
            title,
            matched_domain,
            tab.get("post_login"),
            tab.get("score"),
            "none" if matched_domain else rejection_reasons[-1],
        )
    cdp_cookies: list[dict[str, Any]] = []
    cookie_names: list[str] = []
    cookie_domains: list[str] = []
    cookie_error: str | None = None
    selected_tab: dict[str, Any] | None = preferred_tab
    selected_tab_id = str((selected_tab or {}).get("id") or "")
    active_tab_id = str((tabs[0] if tabs else {}).get("id") or "")
    selected_debug: dict[str, Any] = {
        "selected_target_id": selected_tab_id or None,
        "selected_tab_url": (selected_tab or {}).get("url"),
        "selected_tab_title": (selected_tab or {}).get("title"),
        "active_target_id": active_tab_id or None,
        "selected_tab_active": bool(selected_tab_id and active_tab_id and selected_tab_id == active_tab_id),
        "final_document_url": None,
        "document_title": None,
        "dom_login_marker_detected": None,
        "authenticated_probe_ok": False,
        "auth_cookie_candidate_present": False,
        "candidate_auth_cookie_names": [],
        "cookie_inspection_context": "cdp_target",
        "decision_tree": [],
    }

    if ranked:
        try:
            cdp_target = _inspect_target_session_via_cdp(cdp_port=cdp_port, target_id=selected_tab_id, tab_url=str((selected_tab or {}).get("url") or ""))
            cdp_cookies = list(cdp_target.get("cookies") or [])
            cookie_names = list(cdp_target.get("cookie_names") or [])
            cookie_domains = list(cdp_target.get("cookie_domains") or [])
            cookie_error = cdp_target.get("cookie_error")
            selected_debug.update(
                {
                    "final_document_url": cdp_target.get("final_document_url"),
                    "document_title": cdp_target.get("document_title"),
                    "dom_login_marker_detected": cdp_target.get("dom_login_marker_detected"),
                    "authenticated_probe_ok": bool(cdp_target.get("authenticated_probe_ok")),
                    "auth_cookie_candidate_present": bool(cdp_target.get("auth_cookie_candidate_present")),
                    "candidate_auth_cookie_names": list(cdp_target.get("candidate_auth_cookie_names") or []),
                    "cookie_inspection_context": str(cdp_target.get("cookie_inspection_context") or "cdp_target"),
                    "decision_tree": list(cdp_target.get("decision_tree") or []),
                }
            )
        except Exception as exc:  # pragma: no cover - runtime dependent
            cookie_error = str(exc)
            selected_debug["decision_tree"] = [{"step": "cdp_target_inspection", "result": "failed", "reason": f"exception:{exc}"}]

    auth_cookie_present = bool(selected_debug.get("auth_cookie_candidate_present"))
    authenticated_probe_ok = bool(selected_debug.get("authenticated_probe_ok"))
    unauthenticated_reason = _derive_unauthenticated_reason(
        secure_tab_found=bool(secure_tabs),
        cookie_error=cookie_error,
        cookie_count=len(cdp_cookies),
        auth_cookie_present=auth_cookie_present,
        dom_login_marker_detected=selected_debug.get("dom_login_marker_detected"),
        authenticated_probe_ok=authenticated_probe_ok,
    )
    LOGGER.info(
        "cdp_secure_session_check secure_tab_count=%s selected_target_id=%s selected_url=%r selected_title=%r final_document_url=%r selected_tab_active=%s cookies_found=%s cookie_names=%s cookie_domains=%s auth_cookie_present=%s auth_probe_ok=%s cookie_error=%s unauthenticated_reason=%s decision_tree=%s",
        len(secure_tabs),
        selected_debug.get("selected_target_id"),
        preferred_tab.get("url") if preferred_tab else None,
        preferred_tab.get("title") if preferred_tab else None,
        selected_debug.get("final_document_url"),
        selected_debug.get("selected_tab_active"),
        len(cdp_cookies),
        cookie_names,
        cookie_domains,
        auth_cookie_present,
        authenticated_probe_ok,
        cookie_error or "-",
        unauthenticated_reason,
        selected_debug.get("decision_tree"),
    )
    return {
        "tabs": tabs,
        "secure_tabs": secure_tabs,
        "preferred_tab": preferred_tab,
        "cookies": cdp_cookies,
        "cookie_names": cookie_names,
        "cookie_domains": cookie_domains,
        "cookie_error": cookie_error,
        "rejection_reasons": rejection_reasons,
        "auth_cookie_present": auth_cookie_present,
        "authenticated_probe_ok": authenticated_probe_ok,
        "unauthenticated_reason": unauthenticated_reason,
        "debug": selected_debug,
    }


def _derive_unauthenticated_reason(
    *,
    secure_tab_found: bool,
    cookie_error: str | None,
    cookie_count: int,
    auth_cookie_present: bool,
    dom_login_marker_detected: bool | None,
    authenticated_probe_ok: bool,
) -> str:
    if not secure_tab_found:
        return "no_secure_tab_found"
    if cookie_error:
        return "cookie_inspection_error"
    if cookie_count == 0:
        return "no_cookies_returned"
    if not auth_cookie_present:
        return "cookies_returned_but_no_auth_cookie_candidate"
    if dom_login_marker_detected is True:
        return "dom_indicates_login_page"
    if not authenticated_probe_ok:
        return "authenticated_probe_failed"
    return "authenticated"


def _inspect_target_session_via_cdp(*, cdp_port: int, target_id: str, tab_url: str) -> dict[str, Any]:
    decision_tree: list[dict[str, Any]] = []
    ws = connect_browser_ws(cdp_port)
    try:
        if not target_id:
            raise ChromeCDPError("No target id selected for CDP inspection.")
        attached = cdp_call(ws, "Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = str(attached.get("sessionId") or "")
        if not session_id:
            raise ChromeCDPError(f"Target.attachToTarget returned no sessionId for target={target_id}.")
        target_info = cdp_call(ws, "Target.getTargetInfo", {"targetId": target_id})
        browser_context_id = str((target_info.get("targetInfo") or {}).get("browserContextId") or "")
        cdp_call(ws, "Runtime.enable", {}, session_id=session_id)
        cdp_call(ws, "Page.enable", {}, session_id=session_id)
        cookie_urls = [
            tab_url or f"https://{SECURE_DOMAIN}/cgi-bin/web_interface/admin/customers.cgi",
            f"https://{SECURE_DOMAIN}/",
            "https://123.net/",
        ]
        cookie_result = cdp_call(
            ws,
            "Network.getCookies",
            {"urls": cookie_urls},
            session_id=session_id,
        )
        target_raw_cookies = list(cookie_result.get("cookies") or [])
        LOGGER.info(
            "cdp_cookie_fetch method=Network.getCookies target_id=%s session_id=%s browser_context_id=%s scope=target urls=%s raw_cookie_count=%s",
            target_id,
            session_id,
            browser_context_id or "-",
            cookie_urls,
            len(target_raw_cookies),
        )
        raw_cookies = list(target_raw_cookies)
        cookie_inspection_context = f"target:{target_id}"
        if not raw_cookies:
            all_cookie_result = cdp_call(ws, "Network.getAllCookies", {}, session_id=session_id)
            all_target_cookies = list(all_cookie_result.get("cookies") or [])
            LOGGER.info(
                "cdp_cookie_fetch method=Network.getAllCookies target_id=%s session_id=%s browser_context_id=%s scope=target raw_cookie_count=%s",
                target_id,
                session_id,
                browser_context_id or "-",
                len(all_target_cookies),
            )
            raw_cookies = list(all_target_cookies)
            cookie_inspection_context = f"target_all:{target_id}"
        if not raw_cookies:
            all_cookie_result = cdp_call(ws, "Network.getAllCookies", {})
            browser_all_cookies = list(all_cookie_result.get("cookies") or [])
            LOGGER.info(
                "cdp_cookie_fetch method=Network.getAllCookies target_id=%s session_id=%s browser_context_id=%s scope=browser raw_cookie_count=%s",
                target_id,
                session_id,
                browser_context_id or "-",
                len(browser_all_cookies),
            )
            raw_cookies = list(browser_all_cookies)
            cookie_inspection_context = "browser"
            decision_tree.append({"step": "cookie_fetch_fallback", "result": "ok", "reason": "target_scoped_empty_used_browser_scoped"})
        filter_criteria = f"domain contains {SECURE_DOMAIN} or 123.net"
        filtered_cookies = [
            cookie
            for cookie in raw_cookies
            if SECURE_DOMAIN in str(cookie.get("domain") or "").lower() or "123.net" in str(cookie.get("domain") or "").lower()
        ]
        LOGGER.info(
            "cdp_cookie_filter criteria=%r target_id=%s scope=%s raw_cookie_count=%s filtered_cookie_count=%s",
            filter_criteria,
            target_id,
            cookie_inspection_context,
            len(raw_cookies),
            len(filtered_cookies),
        )
        cookie_names = sorted({str(cookie.get("name") or "") for cookie in filtered_cookies if cookie.get("name")})
        cookie_domains = sorted({f"{cookie.get('domain') or ''}:{cookie.get('path') or '/'}" for cookie in filtered_cookies})
        cookie_name_domain_pairs = sorted(
            {
                f"{str(cookie.get('name') or '')}@{str(cookie.get('domain') or '')}"
                for cookie in filtered_cookies
                if cookie.get("name")
            }
        )
        LOGGER.info(
            "cdp_cookie_inventory target_id=%s scope=%s names=%s name_domain_pairs=%s",
            target_id,
            cookie_inspection_context,
            cookie_names,
            cookie_name_domain_pairs,
        )
        auth_cookie_candidates = [name for name in cookie_names if _looks_like_auth_cookie_name(name)]
        auth_cookie_present = bool(auth_cookie_candidates)
        decision_tree.append({"step": "cookie_inspection", "result": "ok", "reason": f"cookies={len(filtered_cookies)} auth_candidates={len(auth_cookie_candidates)}"})

        eval_result = cdp_call(
            ws,
            "Runtime.evaluate",
            {
                "expression": """
                    (() => {
                      const href = window.location.href || '';
                      const title = document.title || '';
                      const body = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase();
                      const loginLike = body.includes('login') || body.includes('sign in') || body.includes('username') || body.includes('password');
                      return JSON.stringify({href, title, loginLike});
                    })();
                """,
                "returnByValue": True,
            },
            session_id=session_id,
        )
        result_value = (((eval_result.get("result") or {}).get("value")) if isinstance(eval_result, dict) else None) or ""
        parsed = json.loads(result_value) if isinstance(result_value, str) and result_value else {}
        final_document_url = str(parsed.get("href") or tab_url or "")
        document_title = str(parsed.get("title") or "")
        dom_login_marker_detected = bool(parsed.get("loginLike"))
        if dom_login_marker_detected:
            decision_tree.append({"step": "dom_check", "result": "failed", "reason": "dom_indicates_login_page"})
        else:
            decision_tree.append({"step": "dom_check", "result": "ok", "reason": "dom_not_login_page"})
        authenticated_probe_ok = bool(auth_cookie_present and not dom_login_marker_detected and _url_is_post_login(final_document_url))
        if not authenticated_probe_ok:
            decision_tree.append({"step": "authenticated_probe", "result": "failed", "reason": "authenticated_probe_request_returned_login_or_non_admin_page"})
        else:
            decision_tree.append({"step": "authenticated_probe", "result": "ok", "reason": "post_login_url_and_dom_checks_passed"})

        cdp_call(ws, "Target.detachFromTarget", {"sessionId": session_id})
        return {
            "cookies": filtered_cookies,
            "cookie_names": cookie_names,
            "cookie_domains": cookie_domains,
            "candidate_auth_cookie_names": auth_cookie_candidates,
            "auth_cookie_candidate_present": auth_cookie_present,
            "final_document_url": final_document_url,
            "document_title": document_title,
            "dom_login_marker_detected": dom_login_marker_detected,
            "authenticated_probe_ok": authenticated_probe_ok,
            "cookie_error": None,
            "cookie_inspection_context": cookie_inspection_context,
            "decision_tree": decision_tree,
            "browser_context_id": browser_context_id or None,
        }
    except Exception as exc:
        decision_tree.append({"step": "cdp_target_inspection", "result": "failed", "reason": str(exc)})
        return {
            "cookies": [],
            "cookie_names": [],
            "cookie_domains": [],
            "candidate_auth_cookie_names": [],
            "auth_cookie_candidate_present": False,
            "final_document_url": tab_url or None,
            "document_title": None,
            "dom_login_marker_detected": None,
            "authenticated_probe_ok": False,
            "cookie_error": str(exc),
            "cookie_inspection_context": f"target:{target_id or 'none'}",
            "decision_tree": decision_tree,
        }
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _looks_like_auth_cookie_name(name: str) -> bool:
    lowered = (name or "").strip().lower()
    return any(marker in lowered for marker in AUTH_COOKIE_NAME_HINTS)


def _url_is_post_login(url: str) -> bool:
    """Return True if *url* looks like a post-login admin page."""
    low = url.lower()
    return ("customers.cgi" in low or "vpbx.cgi" in low) and "admin" in low


def _auto_seed_and_validate(port: int = DEFAULT_CDP_PORT) -> bool:
    """
    Seed cookies from the CDP instance on *port* and run validation.
    Returns True if authentication succeeded.  Thread-safe via AUTO_SEED_LOCK.
    """
    allowed, reason = _can_attempt_auto_seed()
    if not allowed:
        _log(f"[AUTO] Skipping seed attempt reason={reason}")
        return False

    with AUTO_SEED_LOCK:
        _set_seed_in_progress(True)
        try:
            try:
                result = seed_from_cdp(port, DEFAULT_DOMAINS)
            except CookieSeedError as exc:
                fatal = exc.code == "CDP_WS_ORIGIN_REJECTED" or _is_fatal_cdp_attach_error(str(exc))
                _record_seed_outcome(success=False, error=str(exc), fatal=fatal)
                if fatal:
                    _mark_cdp_attach_failure(error=str(exc), fatal=True)
                _log(f"[AUTO] CDP seed failed fatal={fatal}: {exc}")
                return False

            if not result.cookies:
                live_session = _inspect_live_secure_session(port) if _is_cdp_available(port) else {}
                secure_tab_detected = bool((live_session or {}).get("secure_tabs"))
                if secure_tab_detected:
                    _log("[AUTO] post-login tab detected but CDP cookie retrieval returned 0")
                    _record_seed_outcome(success=False, error="post-login tab detected but CDP cookie retrieval returned 0", fatal=False)
                else:
                    _log("[AUTO] CDP seed returned 0 cookies")
                    _record_seed_outcome(success=False, error="CDP seed returned 0 cookies", fatal=False)
                return False

            store_result = auth_store.replace_cookies(db_path(), result.cookies, source="seed_cdp_auto")
            _log(f"[AUTO] Stored {store_result.get('accepted', 0)} cookies via CDP auto-seed")

            validation = _validate_auth_targets(timeout_seconds=10)
            authenticated = bool(validation.get("authenticated"))
            if authenticated:
                _record_seed_outcome(success=True)
                _update_auth_state(
                    authenticated=True,
                    mode="cdp_auto",
                    detail="Auto-seeded auth cookies from CDP after login detected",
                    last_error=None,
                )
                _append_event(
                    "info",
                    f"Auto-seeded auth cookies mode=cdp_auto count={store_result.get('accepted', 0)}",
                )
            else:
                _log(f"[AUTO] Validation failed after CDP seed: {validation.get('reason')}")
                _record_seed_outcome(success=False, error=f"Validation failed: {validation.get('reason')}", fatal=False)
            return authenticated
        finally:
            _set_seed_in_progress(False)


def _try_auto_launch_debug_chrome() -> bool:
    """
    Launch the debug Chrome profile if not already running.
    Returns True when a new process was started.
    """
    global DEBUG_CHROME_PROC
    if not AUTO_LAUNCH_DEBUG_CHROME:
        return False

    with DEBUG_CHROME_PROC_LOCK:
        # Already alive?
        if DEBUG_CHROME_PROC is not None and DEBUG_CHROME_PROC.poll() is None:
            with AUTO_SEED_STATE_LOCK:
                AUTO_SEED_STATE["debug_browser_running"] = True
            return False
        if _is_cdp_available(DEFAULT_CDP_PORT):
            with AUTO_SEED_STATE_LOCK:
                AUTO_SEED_STATE["debug_browser_running"] = True
            return False  # something else is already on that port

        try:
            browser_path = _detect_browser_path()
        except HTTPException:
            _log("[AUTO] Chrome not found – skipping auto-launch (set CHROME_PATH)")
            return False

        debug_profile = Path(__file__).resolve().parents[4] / "webscraper" / "var" / "chrome-debug"
        try:
            proc = launch_debug_chrome(
                chrome_path=browser_path,
                user_data_dir=debug_profile,
                profile_name="Default",
                port=DEFAULT_CDP_PORT,
            )
            DEBUG_CHROME_PROC = proc
            with AUTO_SEED_STATE_LOCK:
                AUTO_SEED_STATE["debug_browser_running"] = True
            _log(f"[AUTO] Launched debug Chrome pid={proc.pid} cdp_port={DEFAULT_CDP_PORT} profile={debug_profile}")
            return True
        except Exception as exc:
            with AUTO_SEED_STATE_LOCK:
                AUTO_SEED_STATE["debug_browser_running"] = False
            _log(f"[AUTO] Failed to launch debug Chrome: {exc}")
            return False


# ── Background threads ────────────────────────────────────────────────────────

def _auto_startup_chrome() -> None:
    """
    Runs once at startup (in a daemon thread).

    * If Chrome is already on the CDP port → attempt an immediate seed so that
      sessions left over from a previous run are picked up automatically.
    * Otherwise → launch the debug Chrome profile so it is ready for the user.
    """
    time.sleep(2)  # let the server finish initialising
    _log("[AUTO] Startup: checking for existing CDP session")
    if _is_cdp_available(DEFAULT_CDP_PORT):
        _log("[AUTO] Chrome already on CDP port at startup – attempting quick seed")
        _auto_seed_and_validate(DEFAULT_CDP_PORT)
    else:
        launched = _try_auto_launch_debug_chrome()
        if launched:
            # Give Chrome a moment to start, then try seeding from any prior session
            time.sleep(5)
            if _is_cdp_available(DEFAULT_CDP_PORT):
                _log("[AUTO] Debug Chrome started – seeding from prior session cookies (if any)")
                _auto_seed_and_validate(DEFAULT_CDP_PORT)


def _cdp_login_watcher() -> None:
    """
    Long-running daemon thread.

    * Polls Chrome via CDP every ~3 s while not authenticated.
    * When a post-login tab (customers.cgi / vpbx.cgi) is detected,
      automatically seeds cookies and validates.
    * If the owned debug Chrome process dies, attempts a re-launch.
    * When authenticated, backs off to a 30 s check so it can detect
      session expiry and trigger a re-seed.
    """
    _log("[AUTO] CDP login watcher started")
    while True:
        try:
            with AUTH_STATE_LOCK:
                already_auth = AUTH_STATE.authenticated

            if already_auth:
                # Slow polling while authenticated – detect expiry
                time.sleep(30)
                continue

            time.sleep(3)

            # If Chrome died and we launched it, try to restart
            if not _is_cdp_available(DEFAULT_CDP_PORT):
                with AUTO_SEED_STATE_LOCK:
                    AUTO_SEED_STATE["debug_browser_running"] = False
                with DEBUG_CHROME_PROC_LOCK:
                    proc = DEBUG_CHROME_PROC
                if proc is not None and proc.poll() is not None:
                    _log("[AUTO] Debug Chrome process exited – re-launching")
                    _try_auto_launch_debug_chrome()
                continue
            with AUTO_SEED_STATE_LOCK:
                AUTO_SEED_STATE["debug_browser_running"] = True

            # CDP is up – check whether the user has logged in
            urls = _get_cdp_tab_urls(DEFAULT_CDP_PORT)
            post_login = [u for u in urls if _url_is_post_login(u)]
            if not post_login:
                continue  # still on login page or new tab

            _log(f"[AUTO] Post-login tab detected: {post_login[0]!r} – seeding cookies")
            _auto_seed_and_validate(DEFAULT_CDP_PORT)

        except Exception as exc:
            _log(f"[AUTO] Login watcher error: {exc}")
            time.sleep(5)


def _raise_auth_validation_error(job_id: str | None, handle: str | None, validation: dict[str, Any]) -> None:
    if validation.get("authenticated") or validation.get("ok"):
        return
    if job_id:
        db.add_scrape_event(
            db_path(),
            job_id,
            _iso_now(),
            "error",
            "auth_failed",
            "Auth validation failed",
            {"handle": handle, "validation": validation},
        )
    failed = validation.get("reasons") or [item for item in validation.get("checks", []) if not item.get("ok")]
    if not failed:
        failed = [{"code": "not_authenticated", "hint": "Import cookies from browser or login to debug profile"}]
    raise RuntimeError(f"Auth validation failed: {json.dumps(failed, sort_keys=True)}")


def _auth_error_from_output(lines: list[str]) -> str | None:
    auth_markers = ("not authenticated", "authentication failed", "login", "auth_required", "auth appears invalid")
    for line in lines:
        lowered = line.lower()
        if any(marker in lowered for marker in auth_markers):
            return "Not authenticated for secure.123.net (missing cookies or expired session)."
    return None


def map_batch_mode(mode: str) -> str:
    return "full" if mode == "full" else "incremental"


def _normalize_handles(raw_handles: list[str]) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    normalized: list[str] = []
    invalid: list[str] = []
    for raw_handle in raw_handles:
        handle = str(raw_handle or "").strip().upper()
        if not handle or not HANDLE_RE.match(handle):
            if handle:
                invalid.append(handle)
            continue
        if handle in seen:
            continue
        seen.add(handle)
        normalized.append(handle)
    return normalized, invalid


def _build_command(job: QueueJob, handle: str) -> list[str]:
    script = Path(__file__).resolve().parents[4] / "scripts" / "scrape_all_handles.py"
    out_dir = runs_dir() / job.run_id / handle
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script),
        "--db",
        db_path(),
        "--out",
        str(out_dir),
        "--handles",
        handle,
        "--mode",
        job.scrape_mode,
        "--max-tickets",
        str(max(1, int(job.ticket_limit or 1))),
    ]
    if job.rescrape:
        cmd.append("--resume")
    return cmd


def _discover_handles(config: VpbxConfig, job_id: str) -> list[str]:
    _append_event("info", "Starting handle discovery from vpbx.cgi", job_id=job_id)
    rows = fetch_handles(config)
    count = db.upsert_discovered_handles(db_path(), rows)
    _append_event("info", f"Discovered {count} handles from vpbx.cgi", job_id=job_id)
    return [str(row.get("handle")) for row in rows if row.get("handle")]


def _run_one_handle(job: QueueJob, handle: str) -> tuple[int, int, dict[str, Any], str | None]:
    db.ensure_handle_row(db_path(), handle)
    db.update_handle_progress(db_path(), handle, status="running", error=None, last_updated_utc=_iso_now(), last_run_id=job.run_id)
    _append_event("info", f"Starting handle {handle}", handle=handle, job_id=job.job_id)

    cmd = _build_command(job, handle)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    error_lines = 0
    output_lines: list[str] = []
    for line in proc.stdout:
        cleaned = line.strip()
        if cleaned:
            output_lines.append(cleaned)
            _log(f"[{handle}] {cleaned}", job_id=job.job_id)
            milestone: tuple[str, str] | None = None
            lowered = cleaned.lower()
            if "navigat" in lowered and "http" in lowered:
                milestone = ("nav_start", cleaned)
            elif "imported cookie auth applied" in lowered or "cookies loaded" in lowered:
                milestone = ("cookies_loaded", cleaned)
            elif "refresh" in lowered:
                milestone = ("nav_refresh", cleaned)
            elif "auth" in lowered and ("success" in lowered or "failed" in lowered):
                milestone = ("auth_check", cleaned)
            elif "ticket" in lowered and "loaded" in lowered:
                milestone = ("ticket_list_loaded", cleaned)
            if milestone:
                db.add_scrape_event(db_path(), job.job_id, _iso_now(), "info", milestone[0], milestone[1], {"handle": handle})
            if "Attempting imported cookie auth" in cleaned:
                _append_event("info", "Attempting imported cookie auth", handle=handle, job_id=job.job_id)
            elif cleaned.startswith("Imported cookie auth applied="):
                _append_event("info", cleaned, handle=handle, job_id=job.job_id)
            elif "Imported cookie auth successful" in cleaned or "Imported cookie auth succeeded" in cleaned:
                _append_event("info", "Imported cookie auth succeeded", handle=handle, job_id=job.job_id)
            elif "Imported cookie auth failed" in cleaned:
                _append_event("warning", "Imported cookie auth failed", handle=handle, job_id=job.job_id)
        if "[ERROR]" in cleaned:
            error_lines += 1
            _append_event("error", cleaned, handle=handle, job_id=job.job_id)
    rc = proc.wait(timeout=SCRAPE_TIMEOUT_SECONDS)
    stderr_tail: list[str] = []
    if proc.stderr is not None:
        for raw in proc.stderr.read().splitlines():
            line = raw.strip()
            if not line:
                continue
            stderr_tail.append(line)
            output_lines.append(line)
            _log(f"[{handle}][stderr] {line}", job_id=job.job_id)

    ticket_payload = db.list_tickets(db_path(), handle=handle, page=1, page_size=1)
    total_for_handle = int(ticket_payload.get("totalCount") or 0)
    if rc == 0:
        db.update_handle_progress(
            db_path(),
            handle,
            status="ok",
            error=None,
            ticket_count=total_for_handle,
            last_updated_utc=_iso_now(),
            last_run_id=job.run_id,
        )
        _append_event("info", f"Completed handle {handle}, total={total_for_handle}", handle=handle, job_id=job.job_id)
    else:
        msg = _auth_error_from_output(output_lines) or f"scraper exit code {rc}"
        auth_validation = _validate_auth_targets()
        if not auth_validation.get("authenticated"):
            msg = f"Not authenticated. validate={auth_validation.get('checks')}"
        db.update_handle_progress(
            db_path(),
            handle,
            status="error",
            error=msg,
            ticket_count=total_for_handle,
            last_updated_utc=_iso_now(),
            last_run_id=job.run_id,
        )
        _append_event("error", f"Handle {handle} failed: {msg}", handle=handle, job_id=job.job_id)
    result_payload: dict[str, Any] = {"logTail": output_lines[-20:], "stderrTail": stderr_tail[-20:]}
    final_error: str | None = None
    if rc != 0:
        final_error = msg
        auth_validation = _validate_auth_targets()
        result_payload = {
            "errorType": "auth_failed" if not auth_validation.get("authenticated") else "scrape_failed",
            "error": msg,
            "auth": auth_validation,
            "logTail": output_lines[-20:],
            "stderrTail": stderr_tail[-20:],
        }
    return rc, error_lines, result_payload, final_error


def _job_worker() -> None:
    global CURRENT_JOB_ID
    while True:
        job: QueueJob | None = None
        with JOB_QUEUE_LOCK:
            if JOB_QUEUE:
                job = JOB_QUEUE.pop(0)
                CURRENT_JOB_ID = job.job_id
        if not job:
            time.sleep(0.2)
            continue

        completed = 0
        errors = 0
        handles: list[str] = []
        try:
            if job.handles:
                handles = job.handles
            elif job.refresh_handles:
                config, err = _get_required_env()
                if err or not config:
                    raise RuntimeError(err or "Missing VPBX configuration")
                discovered = _discover_handles(config, job.job_id)
                handles = discovered if job.mode == "all" else [job.handle or ""]
            elif job.mode == "all":
                handles = db.list_all_handles(db_path())
            else:
                handles = [job.handle or ""]

            handles = [h for h in handles if h]
            if job.mode == "one" and job.handle and job.handle not in handles:
                handles = [job.handle]

            if not handles:
                raise RuntimeError("No handles available to scrape. Run with refresh_handles=true and valid VPBX credentials.")

            per_handle_status: dict[str, str] = {}
            last_payload: dict[str, Any] = {}
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="running",
                progress_completed=0,
                progress_total=len(handles),
                started_utc=_iso_now(),
                result={
                    "total_handles": len(handles),
                    "completed_handles": 0,
                    "current_handle": None,
                    "per_handle_status": per_handle_status,
                },
            )
            _append_event("info", f"Started scrape job with {len(handles)} handles", job_id=job.job_id)
            validation = _validate_auth_targets()
            if not validation.get("authenticated") and _is_cdp_available(DEFAULT_CDP_PORT):
                _log(f"[WORKER] Auth invalid before job start – attempting CDP auto-seed jobId={job.job_id}")
                _auto_seed_and_validate(DEFAULT_CDP_PORT)
                validation = _validate_auth_targets()
            _raise_auth_validation_error(job.job_id, job.handle, validation)

            for handle in handles:
                db.update_scrape_job(
                    db_path(),
                    job.job_id,
                    status="running",
                    progress_completed=completed,
                    progress_total=len(handles),
                    result={
                        "total_handles": len(handles),
                        "completed_handles": completed,
                        "current_handle": handle,
                        "per_handle_status": per_handle_status,
                        **last_payload,
                    },
                )
                try:
                    rc, line_errors, run_result_payload, run_error = _run_one_handle(job, handle)
                    last_payload = run_result_payload
                    errors += line_errors + (1 if rc != 0 else 0)
                    per_handle_status[handle] = "error" if rc != 0 or run_error else "ok"
                except Exception as exc:  # continue to next handle by requirement
                    errors += 1
                    per_handle_status[handle] = "error"
                    db.update_handle_progress(
                        db_path(), handle, status="error", error=str(exc), last_updated_utc=_iso_now(), last_run_id=job.run_id
                    )
                    _append_event("error", f"Handle {handle} exception: {exc}", handle=handle, job_id=job.job_id)
                finally:
                    completed += 1
                    db.update_scrape_job(
                        db_path(),
                        job.job_id,
                        status="running",
                        progress_completed=completed,
                        progress_total=len(handles),
                        result={
                            "total_handles": len(handles),
                            "completed_handles": completed,
                            "current_handle": None,
                            "per_handle_status": per_handle_status,
                            **last_payload,
                        },
                    )

            final_status = "completed" if errors == 0 else "failed"
            existing_result = (db.get_scrape_job(db_path(), job.job_id) or {}).get("result") or {}
            final_result = {
                **existing_result,
                **last_payload,
                "errors": errors,
                "total_handles": len(handles),
                "completed_handles": completed,
                "current_handle": None,
                "per_handle_status": per_handle_status,
                "queued": handles,
            }
            if errors and "errorType" not in final_result:
                final_result["errorType"] = "scrape_failed"
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status=final_status,
                progress_completed=completed,
                progress_total=len(handles),
                finished_utc=_iso_now(),
                error_message=None if errors == 0 else f"{errors} scrape errors",
                result=final_result,
            )
            _append_event("info", f"Job finished status={final_status}", job_id=job.job_id)
        except Exception as exc:
            err_msg = str(exc)
            if not err_msg:
                err_msg = "Unhandled scrape error"
            auth_payload = _validate_auth_targets()
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="failed",
                progress_completed=completed,
                progress_total=max(len(handles), completed, 1),
                finished_utc=_iso_now(),
                error_message="Auth validation failed" if not auth_payload.get("ok") else err_msg,
                result={
                    "errorType": "auth_failed" if not auth_payload.get("ok") else "scrape_failed",
                    "error": err_msg,
                    "auth": auth_payload,
                },
            )
            _append_event("error", f"Unhandled scrape exception: {err_msg}", job_id=job.job_id)
        finally:
            CURRENT_JOB_ID = None


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        _log(
            f"request method={request.method} path={request.url.path} status={response.status_code} duration_ms={duration_ms}",
            request_id=request_id,
        )
        response.headers["X-Request-Id"] = request_id
        return response
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        LOGGER.exception(
            "request_failed method=%s path=%s duration_ms=%s requestId=%s",
            request.method,
            request.url.path,
            duration_ms,
            request_id,
        )
        raise


@app.get("/api/handles")
def api_handles(limit: int = Query(default=500, ge=1, le=5000), offset: int = 0):
    _log(f"route_hit path=/api/handles limit={limit} offset={offset}")
    items = db.list_handles(db_path(), limit=limit, offset=offset)
    return {"items": sorted(items, key=lambda item: item.get("last_updated_utc") or item.get("finished_utc") or "", reverse=True)}


@app.get("/api/handles/summary")
def api_handles_summary(q: str = "", limit: int = Query(default=200, ge=1, le=5000), offset: int = Query(default=0, ge=0)):
    return db.list_handles_summary(db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    _log(f"route_hit path=/api/handles/all q={q!r} limit={limit}")
    items = db.list_handle_names(db_path(), q=q, limit=limit)
    return {"items": items, "count": len(items)}


@app.post("/api/scrape-batch")
def api_scrape_batch(req: BatchScrapeRequest):
    job_ids: list[str] = []
    mapped_mode = map_batch_mode(req.mode)
    for raw_handle in req.handles:
        handle = (raw_handle or "").strip()
        if not handle:
            continue
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)
        db.create_scrape_job(
            db_path(),
            job_id=job_id,
            handle=handle,
            mode=req.mode,
            ticket_limit=req.limit,
            status="queued",
            created_utc=_iso_now(),
        )
        with JOB_QUEUE_LOCK:
            JOB_QUEUE.append(
                QueueJob(
                    job_id=job_id,
                    run_id=datetime.now(timezone.utc).strftime("api_%Y%m%d_%H%M%S") + f"_{os.getpid()}",
                    mode="one",
                    handle=handle,
                    rescrape=False,
                    refresh_handles=False,
                    scrape_mode=mapped_mode,
                    ticket_limit=req.limit,
                )
            )
        _append_event("info", f"Queued scrape job from /api/scrape-batch mode={mapped_mode} max={req.limit}", handle=handle, job_id=job_id)
    return {"status": "queued", "jobIds": job_ids}


@app.post("/scrape/handles")
@app.post("/api/scrape/handles")
def api_scrape_handles(req: ScrapeHandlesRequest):
    handles, invalid_handles = _normalize_handles(req.handles)
    if not handles:
        raise HTTPException(status_code=400, detail="handles must contain at least one valid handle")
    if invalid_handles:
        raise HTTPException(status_code=400, detail={"message": "Invalid handles", "invalid_handles": invalid_handles})
    if len(handles) > MAX_BATCH_HANDLES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BATCH_HANDLES} handles per batch")

    options = req.options or {}
    scrape_mode = "full" if str(options.get("scrape_mode") or "").lower() == "full" else "incremental"
    ticket_limit = int(options.get("ticket_limit") or 50)
    ticket_limit = max(1, min(ticket_limit, 500))
    job_id = str(uuid.uuid4())
    run_id = datetime.now(timezone.utc).strftime("api_%Y%m%d_%H%M%S") + f"_{os.getpid()}"

    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=handles[0] if len(handles) == 1 else None,
        handles=handles,
        mode="selected",
        ticket_limit=ticket_limit,
        status="queued",
        created_utc=_iso_now(),
    )
    with JOB_QUEUE_LOCK:
        JOB_QUEUE.append(
            QueueJob(
                job_id=job_id,
                run_id=run_id,
                mode="selected",
                handle=handles[0] if len(handles) == 1 else None,
                handles=handles,
                rescrape=bool(options.get("rescrape", False)),
                refresh_handles=req.mode == "refresh_handles",
                scrape_mode=scrape_mode,
                ticket_limit=ticket_limit,
            )
        )
    _append_event("info", f"Queued scrape handles job count={len(handles)}", job_id=job_id, meta={"count": len(handles)})
    return {"job_id": job_id, "count": len(handles), "queued": handles}


@app.get("/api/events/latest")
def api_events_latest(limit: int = Query(default=50, ge=1, le=500), job_id: str | None = None):
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


@app.post("/api/scrape/start")
def api_scrape_start(req: StartScrapeRequest):
    if req.mode == "one" and not req.handle:
        raise HTTPException(status_code=400, detail="handle is required when mode='one'")

    if req.refresh_handles:
        _, env_error = _get_required_env()
        if env_error:
            _append_event("error", env_error, handle=req.handle)
            raise HTTPException(status_code=400, detail=env_error)

    if req.mode == "one" and req.handle and not req.refresh_handles and not db.handle_exists(db_path(), req.handle):
        raise HTTPException(status_code=404, detail="handle not found in DB; run with refresh_handles=true first")

    job_id = str(uuid.uuid4())
    run_id = datetime.now(timezone.utc).strftime("api_%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=req.handle,
        mode=req.mode,
        ticket_limit=None,
        status="queued",
        created_utc=_iso_now(),
    )
    with JOB_QUEUE_LOCK:
        JOB_QUEUE.append(
            QueueJob(job_id=job_id, run_id=run_id, mode=req.mode, handle=req.handle, rescrape=req.rescrape, refresh_handles=req.refresh_handles)
        )
    _append_event("info", f"Queued scrape job mode={req.mode} refresh_handles={req.refresh_handles}", handle=req.handle, job_id=job_id)
    return {"job_id": job_id, "started": True}


@app.get("/api/scrape/status")
def api_scrape_status(job_id: str | None = None):
    if not job_id:
        latest = db.get_latest_scrape_job(db_path())
        if not latest:
            raise HTTPException(status_code=404, detail="Job not found")
        job_id = str(latest["job_id"])
    job = db.get_scrape_job(db_path(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = job.get("result") or {}
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "total_handles": job.get("progress_total", 0),
        "completed": job.get("progress_completed", 0),
        "completed_handles": int(result.get("completed_handles") or job.get("progress_completed") or 0),
        "current_handle": result.get("current_handle"),
        "per_handle_status": result.get("per_handle_status") or {},
        "running": CURRENT_JOB_ID == job_id,
        "errors": int(result.get("errors") or 0),
        "started_utc": job.get("started_utc"),
        "finished_utc": job.get("finished_utc"),
        "error_message": job.get("error_message"),
        "result": result,
    }


if _has_python_multipart():

    @app.post("/api/auth/import-file")
    async def api_auth_import_file(
        request: Request,
        file: UploadFile | None = File(default=None),
        domain: str | None = Form(default=None),
    ):
        if not _is_localhost_request(request):
            raise HTTPException(status_code=403, detail="localhost requests only")
        if file is None:
            raise HTTPException(status_code=400, detail="Missing upload file in form field 'file'")

        filename = file.filename or "cookies_upload.txt"

        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            text_payload = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_payload = raw_bytes.decode("latin-1")

        default_domain = (domain or get_default_cookie_domain() or "").strip().lstrip(".").lower() or None
        _log(
            "Cookie import attempt"
            f" contentType={file.content_type or '-'} filename={filename or '-'} bytes={len(raw_bytes)}"
            f" targets={','.join(get_target_domains())} defaultDomain={default_domain or '-'}"
        )
        return _import_and_store_cookies(
            text_payload,
            source_label="file",
            filename=filename or "upload.txt",
            default_domain=default_domain,
        )


    @app.post("/api/auth/import-cookies")
    async def api_auth_import_cookies_legacy(
        request: Request,
        file: UploadFile | None = File(default=None),
        domain: str | None = Form(default=None),
    ):
        return await api_auth_import_file(request, file=file, domain=domain)

else:

    @app.post("/api/auth/import-file")
    async def api_auth_import_file_unavailable() -> dict[str, str]:
        raise HTTPException(status_code=503, detail=_missing_python_multipart_message())

    @app.post("/api/auth/import-cookies")
    async def api_auth_import_cookies_unavailable() -> dict[str, str]:
        raise HTTPException(status_code=503, detail=_missing_python_multipart_message())


@app.post("/api/auth/import")
def api_auth_import(request: Request, payload: ImportTextRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    if payload.cookies is not None:
        text_payload = json.dumps(payload.cookies)
    else:
        text_payload = payload.text or payload.cookie or ""
    if not text_payload.strip():
        raise HTTPException(status_code=400, detail="Payload text is empty")
    default_domain = get_default_cookie_domain()
    guessed_name = "pasted.json" if text_payload.strip().startswith(("[", "{")) else "pasted.txt"
    return _import_and_store_cookies(
        text_payload,
        source_label="paste",
        filename=guessed_name,
        default_domain=default_domain,
    )


@app.post("/api/auth/import-text")
def api_auth_import_text_legacy(request: Request, payload: ImportTextRequest):
    return api_auth_import(request, payload)


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    request_id = getattr(request.state, "request_id", None)
    try:
        status_payload = _auth_meta_response(auth_store.status(db_path()))
        validation = _validate_auth_targets(timeout_seconds=5)
        authenticated = bool(validation.get("authenticated"))
        detail = validation.get("reason") or ("Authenticated" if authenticated else "Not authenticated")
        _update_auth_state(
            authenticated=authenticated,
            mode="status_poll",
            detail=str(detail),
            last_error=None if authenticated else str(detail),
            suggestion="Open Chrome using profile dir and login once",
        )
        return {**status_payload, **_auth_state_payload()}
    except Exception as exc:  # pragma: no cover - defensive endpoint boundary
        _log(f"auth_status error={exc}", request_id=request_id)
        _update_auth_state(
            authenticated=False,
            mode="status_error",
            detail="Auth status lookup failed",
            last_error=str(exc),
            suggestion="Open Chrome using profile dir and login once",
        )
        return {"ok": False, "reason": str(exc), "domains": [], "count": 0, "cookie_count": 0, "domain_counts": [], "last_imported": None, "source": "none", **_auth_state_payload()}


@app.post("/api/auth/clear")
def api_auth_clear(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    auth_store.clear_cookies(db_path())
    _update_auth_state(
        authenticated=False,
        mode="clear",
        detail="Imported auth cookies cleared",
        last_error="Authentication cleared",
        suggestion="Open Chrome using profile dir and login once",
    )
    _append_event("info", "Cleared imported auth cookies")
    return {"ok": True, **_auth_meta_response(auth_store.status(db_path())), **_auth_state_payload()}


@app.post("/api/auth/clear-cookies")
def api_auth_clear_cookies_legacy(request: Request):
    return api_auth_clear(request)


def _import_from_browser_impl(request: Request, payload: BrowserImportRequest) -> dict[str, Any]:
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")

    selected_domain = (payload.domain or "secure.123.net").strip().lstrip(".").lower() or "secure.123.net"
    cdp_port = int(os.getenv("CHROME_DEBUG_PORT") or os.getenv("CHROME_CDP_PORT") or str(DEFAULT_CDP_PORT))
    try:
        user_data_dir = browser_user_data_dir(payload.browser)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info("Cookie import requested: browser=%s profile=%s domains=%s", payload.browser, payload.profile, [selected_domain])
    _log(
        f"route_hit path=/api/auth/import_from_browser browser={payload.browser} profile={payload.profile} domain={selected_domain}"
    )
    chosen_source = f"{payload.browser}_profile"
    cdp_diag = _cdp_diag(cdp_port, check_ws=True)
    if bool(cdp_diag.get("json_version_ok")):
        _log(
            f"auth_source_warning debug Chrome CDP is reachable on {cdp_port}; "
            f"sync_from_browser still targets local profile browser={payload.browser} profile={payload.profile}"
        )
    import_result: dict[str, Any]
    try:
        disk_result = seed_from_disk(user_data_dir, [selected_domain], profile_name=payload.profile, browser=payload.browser)
        import_result = {
            "method_used": "disk",
            "imported_count": len(disk_result.cookies),
            "warnings": [],
            "cookies": disk_result.cookies,
            "details": {**(disk_result.details or {}), "attempted_sources": [{"source": chosen_source, "status": "selected"}]},
        }
    except CookieSeedError as exc:
        _log(
            f"auth_source_skip source={chosen_source} reason={exc.code} "
            f"cdp_status={cdp_diag.get('status')} cdp_error={cdp_diag.get('error') or '-'}"
        )
        if exc.code != "DB_LOCKED":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        warnings = [
            f"{payload.browser} profile DB locked; falling back to CDP import.",
        ]
        fallback_sources = [{"source": chosen_source, "status": "failed", "reason": exc.code}]
        cdp_result = seed_from_cdp(cdp_port, [selected_domain])
        import_result = {
            "method_used": "cdp",
            "imported_count": len(cdp_result.cookies),
            "warnings": warnings,
            "cookies": cdp_result.cookies,
            "details": {
                **(cdp_result.details or {}),
                "fallback_from": chosen_source,
                "fallback_reason": exc.code,
                "cdp_status": cdp_diag.get("status"),
                "cdp_error": cdp_diag.get("error"),
                "attempted_sources": fallback_sources + [{"source": "cdp_debug_chrome", "status": "fallback"}],
            },
        }

    backend_source = "browser_cdp" if import_result["method_used"] == "cdp" else f"{payload.browser}_profile"
    previous_status = auth_store.status(db_path())
    previous_source = str(previous_status.get("source") or "none")
    store_result = auth_store.replace_cookies(db_path(), import_result["cookies"], source=backend_source)
    overwritten_from = previous_source if previous_source not in {"none", backend_source} else None
    status_payload = _auth_meta_response(auth_store.status(db_path()))
    _record_auth_import_attempt(
        attempted=chosen_source,
        result="success",
        source=backend_source,
        cookie_count=int(store_result.get("accepted", 0)),
        details={"browser": payload.browser, "profile": payload.profile, "domain": selected_domain, **(import_result.get("details") or {})},
        overwritten_from=overwritten_from,
    )
    _append_event(
        "info",
        (
            f"Browser auth import browser={payload.browser} domain={selected_domain} profile={payload.profile} "
            f"method={import_result['method_used']} accepted={store_result.get('accepted', 0)} "
            f"warnings={len(import_result.get('warnings', []))}"
        ),
    )
    _log(
        "browser_sync_result "
        f"browser={payload.browser} profile={payload.profile} domain={selected_domain} "
        f"method={import_result['method_used']} imported_count={int(store_result.get('accepted', 0))} "
        f"warnings={len(import_result.get('warnings', []))} "
        f"attempted_sources={import_result.get('details', {}).get('attempted_sources', [])}"
    )
    return {
        "ok": True,
        "status": "imported",
        "browser": payload.browser,
        "domain": selected_domain,
        "profile": payload.profile,
        "method_used": import_result["method_used"],
        "imported_count": int(store_result.get("accepted", 0)),
        "warnings": import_result.get("warnings", []),
        "details": import_result.get("details", {}),
        **status_payload,
    }


@app.post("/api/auth/import_from_browser")
def api_auth_import_from_browser(
    request: Request,
    payload: BrowserImportRequest | None = None,
    browser: str | None = Query(default=None),
    profile: str | None = Query(default=None),
    domain: str | None = Query(default=None),
):
    base_payload = payload or BrowserImportRequest()
    resolved_payload = BrowserImportRequest(
        browser=(browser or base_payload.browser),
        profile=(profile or base_payload.profile),
        domain=(domain or base_payload.domain),
    )
    return _import_from_browser_impl(request, resolved_payload)


@app.post("/api/auth/sync_from_browser")
def api_auth_sync_from_browser(request: Request, payload: BrowserImportRequest):
    return _import_from_browser_impl(request, payload)


@app.post("/api/auth/import-from-browser")
def api_auth_import_from_browser_alias_dash(request: Request, payload: BrowserImportRequest):
    return _import_from_browser_impl(request, payload)


@app.post("/api/auth/import-browser")
def api_auth_import_from_browser_alias_short(request: Request, payload: BrowserImportRequest):
    return _import_from_browser_impl(request, payload)


@app.post("/api/auth/sync-from-browser")
def api_auth_sync_from_browser_alias_dash(request: Request, payload: BrowserImportRequest):
    return _import_from_browser_impl(request, payload)


@app.get("/api/auth/validate")
def api_auth_validate_get(request: Request, domain: str = Query(default="secure.123.net"), timeout_seconds: int = Query(default=10, ge=2, le=60)):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    _log(f"route_hit path=/api/auth/validate method=GET domain={domain} timeout_seconds={timeout_seconds}")
    payload = _validate_auth_targets(timeout_seconds)
    payload.setdefault("details", {})
    payload["details"]["domain"] = domain
    return payload


@app.post("/api/auth/validate")
def api_auth_validate(request: Request, payload: ValidateAuthRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    _log(f"route_hit path=/api/auth/validate method=POST timeoutSeconds={payload.timeoutSeconds}")
    return _validate_auth_targets(payload.timeoutSeconds)


@app.get("/api/auth/detect_debug")
def api_auth_detect_debug(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    payload = _inspect_live_secure_session(DEFAULT_CDP_PORT) if _is_cdp_available(DEFAULT_CDP_PORT) else {"debug": {"decision_tree": [{"step": "cdp", "result": "failed", "reason": "cdp_unavailable"}]}}
    return {
        "ok": True,
        "cdp_port": DEFAULT_CDP_PORT,
        "secure_tab_detected": bool(payload.get("secure_tabs")),
        "cookie_count": len(list(payload.get("cookies") or [])),
        "cookie_names": list(payload.get("cookie_names") or []),
        "cookie_domains": list(payload.get("cookie_domains") or []),
        "auth_cookie_present": bool(payload.get("auth_cookie_present")),
        "authenticated_probe_ok": bool(payload.get("authenticated_probe_ok")),
        "unauthenticated_reason": payload.get("unauthenticated_reason"),
        "debug": payload.get("debug") or {},
    }


@app.post("/api/auth/hybrid")
def api_auth_hybrid(request: Request, payload: HybridAuthRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")

    target_url = (payload.target_url or "").strip() or CHROME_CUSTOMERS_URL
    timeout_seconds = max(10, min(int(payload.timeoutSeconds or 300), 1800))

    existing_validation = _validate_auth_targets(timeout_seconds=10)
    if existing_validation.get("authenticated"):
        return {"ok": True, "mode": "existing_cookies", "validate": existing_validation}

    previous_profile = os.environ.get("CHROME_PROFILE_DIR")
    if payload.profile:
        os.environ["CHROME_PROFILE_DIR"] = payload.profile

    driver = None
    try:
        driver = get_driver_reusing_profile(headless=False)
        selenium_probe = probe_auth(driver, url=target_url)
        cookie_summary = summarize_driver_cookies(driver)
        if not selenium_probe.get("ok"):
            _append_event("error", f"Hybrid auth selenium probe failed probe={selenium_probe} cookies={cookie_summary}")
            return {"ok": False, "mode": "selenium", "probe": selenium_probe, "cookies": cookie_summary}

        seeded = selenium_driver_to_requests_session(driver, base_url=target_url)
        requests_probe = probe_auth(seeded, url=target_url)
        if not requests_probe.get("ok"):
            _append_event("error", f"Hybrid auth seeded requests probe failed probe={requests_probe} seleniumProbe={selenium_probe} cookies={cookie_summary}")
            return {"ok": False, "mode": "requests_seeded_from_selenium", "probe": requests_probe, "selenium_probe": selenium_probe, "cookies": cookie_summary}

        normalized = []
        for cookie in (driver.get_cookies() or []):
            if not isinstance(cookie, dict):
                continue
            normalized.append({
                "name": str(cookie.get("name") or "").strip(),
                "value": str(cookie.get("value") or ""),
                "domain": str(cookie.get("domain") or "").strip() or "secure.123.net",
                "path": str(cookie.get("path") or "/") or "/",
                "expires": cookie.get("expiry", cookie.get("expires")),
                "secure": bool(cookie.get("secure")),
                "httpOnly": bool(cookie.get("httpOnly")),
                "sameSite": cookie.get("sameSite"),
            })

        store_result = auth_store.replace_cookies(db_path(), normalized, source="selenium_profile")
        validation = _validate_auth_targets(timeout_seconds=timeout_seconds)
        _append_event("info", f"Hybrid auth completed cookies_saved={store_result.get('accepted', 0)} domains={cookie_summary.get('domains', [])}")
        return {
            "ok": True,
            "mode": "requests_seeded_from_selenium",
            "cookie_count": int(store_result.get("accepted", 0)),
            "domains": cookie_summary.get("domains", []),
            "probe": requests_probe,
            "selenium_probe": selenium_probe,
            "validate": validation,
        }
    finally:
        if driver is not None:
            driver.quit()
        if payload.profile:
            if previous_profile is None:
                os.environ.pop("CHROME_PROFILE_DIR", None)
            else:
                os.environ["CHROME_PROFILE_DIR"] = previous_profile


@app.post("/api/auth/launch-browser")
@app.post("/api/auth/open_browser")
@app.post("/auth/launch-browser")
def api_auth_launch_browser(request: Request, payload: LaunchBrowserRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    target_url = default_target_url((payload.url or "").strip() or DEFAULT_TICKETING_TARGET_URL)
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing target URL. Set TICKETING_TARGET_URL or provide url in request.")
    _log(f"route_hit path=/api/auth/launch-browser profile={payload.profile} new_window={payload.new_window} target_url={target_url}")

    browser_path = _detect_browser_path()
    profile_dir = _profile_dir(payload.profile)

    command = [
        str(browser_path),
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if payload.new_window:
        command.append("--new-window")
    command.append(target_url)

    started = False
    error_text = None
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(command, creationflags=creationflags)
        started = True
        _update_auth_state(
            authenticated=False,
            mode="launch_browser",
            detail="Browser launched for manual authentication",
            last_error=None,
            profile_dir=str(profile_dir),
            suggestion="Open Chrome using profile dir and login once",
        )
    except Exception as exc:  # pragma: no cover - OS-specific process launch failures
        error_text = str(exc)
        _update_auth_state(
            authenticated=False,
            mode="launch_browser",
            detail="Browser launch failed",
            last_error=error_text,
            profile_dir=str(profile_dir),
            suggestion="Open Chrome using profile dir and login once",
        )

    _log(f"launched isolated browser browser={browser_path} profile_dir={profile_dir} url={target_url} started={started}")
    return {
        "ok": started,
        "started": started,
        "browser": str(browser_path),
        "profile_dir": str(profile_dir),
        "command": command,
        "error": error_text,
    }


@app.post("/api/admin/restart")
def api_admin_restart(request: Request):
    """Trigger a hot-reload of the API server (requires --reload / --no-proxy-headers flags on startup)."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    import signal
    import threading

    def _send_reload():
        import time
        time.sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM if os.name == "nt" else getattr(signal, "SIGHUP", signal.SIGTERM))

    threading.Thread(target=_send_reload, daemon=True).start()
    return {"ok": True, "message": "API restart signal sent"}


@app.post("/api/auth/force-reset")
@app.post("/auth/force-reset")
def api_auth_force_reset(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    result = AUTH_MANAGER.clear_auth_state()
    _append_event("info", f"Forced auth reset removed={len(result.get('removed', []))} warnings={len(result.get('warnings', []))}")
    return result


@app.post("/api/auth/launch")
@app.post("/auth/launch")
def api_auth_launch(
    request: Request,
    force: bool = Query(default=False),
    url: str | None = Query(default=None),
    timeout_seconds: int = Query(default=300, ge=10, le=1800),
):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    target_url = default_target_url(url or DEFAULT_TICKETING_TARGET_URL)
    _log(f"route_hit path=/api/auth/launch force={force} timeout_seconds={timeout_seconds} target_url={target_url}")
    result = AUTH_MANAGER.launch_login(force_fresh=force, target_url=target_url, timeout_seconds=timeout_seconds)
    _append_event(
        "info",
        f"Auth launch force={force} cookies_saved={result.get('cookies_saved')} profile_dir={result.get('profile_dir')}",
    )
    return result


@app.post("/api/auth/launch_seeded")
@app.post("/auth/launch_seeded")
def api_auth_launch_seeded(request: Request, payload: LaunchSeededRequest):
    seed_payload = AuthSeedRequest(
        mode="auto",
        chrome_profile_dir=payload.chrome_profile_dir,
        seed_domains=payload.seed_domains,
    )
    return api_auth_seed(request, seed_payload)


@app.post("/api/auth/seed")
@app.post("/auth/seed")
def api_auth_seed(request: Request, payload: AuthSeedRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")

    mode = payload.mode
    profile_name = resolve_profile_name(payload.chrome_profile_dir)
    user_data_dir = resolve_chrome_user_data_dir(payload.chrome_user_data_dir)
    try:
        warnings: list[str] = []
        cdp_diag = _cdp_diag(payload.cdp_port, check_ws=True)
        selected_source = "cdp_debug_chrome" if bool(cdp_diag.get("json_version_ok")) else "chrome_profile"
        _log(
            "auth_seed source_selection "
            f"selected={selected_source} mode={mode} cdp_port={payload.cdp_port} "
            f"cdp_status={cdp_diag.get('status')} cdp_error={cdp_diag.get('error') or '-'}"
        )
        if mode == "disk":
            result = seed_from_disk(user_data_dir, payload.seed_domains, profile_name=profile_name)
        elif mode == "cdp":
            result = seed_from_cdp(payload.cdp_port, payload.seed_domains)
        else:
            auto_result = import_cookies_auto(
                profile_dir=user_data_dir,
                domains=payload.seed_domains,
                profile_name=profile_name,
                cdp_url_or_port=payload.cdp_port,
            )
            warnings = list(auto_result.get("warnings") or [])
            result = SeedResult(mode_used=str(auto_result["method_used"]), cookies=list(auto_result["cookies"]), details=dict(auto_result.get("details") or {}))
            _log(
                "auth_seed auto_attempts "
                f"attempted_sources={result.details.get('attempted_sources', [])} "
                f"warnings={warnings}"
            )
    except CookieSeedError as exc:
        _record_auth_import_attempt(
            attempted=f"seed_{mode}",
            result="failed",
            source="none",
            cookie_count=0,
            details={
                "error_code": exc.code,
                "error": str(exc),
                "cdp_port": payload.cdp_port,
                "cdp_status": cdp_diag.get("status"),
                "cdp_error": cdp_diag.get("error"),
            },
        )
        detail = str(exc)
        next_step = "Verify auth-doctor output and profile settings."
        if exc.code == "DB_LOCKED":
            next_step = "Chrome is open. Either close Chrome OR start debug Chrome (button) to use CDP."
        elif exc.code == "CDP_WS_ORIGIN_REJECTED":
            next_step = (
                f"Chrome debug websocket rejected this backend origin on port {payload.cdp_port}. "
                f"Relaunch debug Chrome with --remote-allow-origins=http://127.0.0.1:{payload.cdp_port} "
                "or use Launch Debug Chrome button."
            )
        elif exc.code == "CDP_UNAVAILABLE":
            next_step = f"No debuggable Chrome found. Start Chrome with --remote-debugging-port={payload.cdp_port} or use Launch Debug Chrome button."
        _update_auth_state(
            authenticated=False,
            mode=mode,
            detail="Seed auth failed",
            last_error=detail,
            profile_dir=str(user_data_dir),
            suggestion="Open Chrome using profile dir and login once",
        )
        return {
            "ok": False,
            "mode_used": mode,
            "details": {"error_code": exc.code, "error": detail, **exc.details},
            "next_step_if_failed": next_step,
            **_auth_state_payload(),
        }

    store_source = "seed_cdp" if result.mode_used == "cdp" else "seed_disk"
    previous_status = auth_store.status(db_path())
    previous_source = str(previous_status.get("source") or "none")
    store_result = auth_store.replace_cookies(db_path(), result.cookies, source=store_source)
    overwritten_from = previous_source if previous_source not in {"none", store_source} else None
    status_payload = _auth_meta_response(auth_store.status(db_path()))
    selected_domains = sorted({str(cookie.get("domain") or "") for cookie in result.cookies if cookie.get("domain")})
    _record_auth_import_attempt(
        attempted=f"seed_{mode}",
        result="success",
        source=store_source,
        cookie_count=int(store_result.get("accepted", 0)),
        details={"domains": selected_domains, **(result.details or {})},
        overwritten_from=overwritten_from,
    )
    _log(
        "auth_seed_result "
        f"attempted=seed_{mode} selected={_normalize_source_label(store_source)} "
        f"cookie_count={int(store_result.get('accepted', 0))} domains={selected_domains} overwritten_from={overwritten_from or '-'} "
        f"attempted_sources={result.details.get('attempted_sources', [])}"
    )
    _update_auth_state(
        authenticated=True,
        mode=result.mode_used,
        detail="Seed auth succeeded",
        last_error=None,
        profile_dir=str(user_data_dir),
        suggestion="Open Chrome using profile dir and login once",
    )
    _append_event("info", f"Seeded auth cookies mode={result.mode_used} count={store_result.get('accepted', 0)} warnings={len(warnings)}")
    return {
        "ok": True,
        "mode_used": result.mode_used,
        "details": result.details,
        "warnings": warnings,
        "cookie_count": int(store_result.get("accepted", 0)),
        **status_payload,
        **_auth_state_payload(),
        "next_step_if_failed": None,
    }


@app.get("/api/auth/chrome_profiles")
@app.get("/auth/chrome_profiles")
def api_auth_chrome_profiles(request: Request, browser: str = Query(default="chrome")):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    try:
        profiles = list_browser_profiles(browser)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    preferred = "Profile 1" if "Profile 1" in profiles else ("Default" if "Default" in profiles else (profiles[0] if profiles else None))
    return {"ok": True, "browser": browser, "profiles": profiles, "preferred": preferred}


@app.post("/api/auth/import_from_profile")
@app.post("/auth/import_from_profile")
def api_auth_import_from_profile(request: Request, payload: ImportFromProfileRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")
    profile_dir = resolve_profile_dir(payload.temp_profile_dir, payload.profile)

    try:
        cookies, domain_counts = load_cookies_from_profile(profile_dir, payload.seed_domains)
    except ChromeCookieError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not cookies:
        raise HTTPException(status_code=400, detail="No cookies extracted for secure.123.net from profile.")

    store_result = auth_store.replace_cookies(db_path(), cookies, source="seeded_profile")
    status_payload = _auth_meta_response(auth_store.status(db_path()))
    _append_event(
        "info",
        f"Imported auth cookies from seeded profile count={store_result.get('accepted', 0)} domain_counts={domain_counts}",
    )
    return {
        "ok": True,
        **status_payload,
        "cookie_count": int(store_result.get("accepted", 0)),
        "domain_counts": [{"domain": domain, "count": count} for domain, count in sorted(domain_counts.items())],
    }


@app.post("/api/auth/launch_debug_chrome")
@app.post("/auth/launch_debug_chrome")
def api_auth_launch_debug_chrome(request: Request, payload: LaunchDebugChromeRequest):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="localhost requests only")

    cdp_diag = cdp_availability(payload.cdp_port, check_ws=True)
    cdp_running = bool(cdp_diag.get("json_version_ok"))
    target_already_open = any(
        str(url).lower().startswith(CHROME_CUSTOMERS_URL.lower())
        for url in (_get_cdp_tab_urls(payload.cdp_port) if cdp_running else [])
    )
    fatal_cdp_error = _is_fatal_cdp_attach_error(str(cdp_diag.get("error") or ""), str(cdp_diag.get("status") or ""))

    if cdp_running:
        with AUTO_SEED_STATE_LOCK:
            AUTO_SEED_STATE["debug_browser_running"] = True
        if fatal_cdp_error:
            _mark_cdp_attach_failure(error=str(cdp_diag.get("error") or "CDP websocket attach failure"), fatal=True)
            return {
                "ok": False,
                "mode_used": "cdp",
                "details": {
                    "cdp_port": payload.cdp_port,
                    "already_running": True,
                    "target_already_open": target_already_open,
                    "cdp_validation": cdp_diag,
                },
                "warning": (
                    "Debug Chrome is running, but CDP attach failed due to remote origin rejection. "
                    "Tabs will not be reopened until configuration is fixed."
                ),
                "next_step_if_failed": (
                    f"Chrome debug websocket rejected this backend origin on port {payload.cdp_port}. "
                    f"Relaunch debug Chrome with --remote-allow-origins=http://127.0.0.1:{payload.cdp_port} "
                    "or --remote-allow-origins=*."
                ),
            }
        return {
            "ok": True,
            "mode_used": "cdp",
            "details": {
                "cdp_port": payload.cdp_port,
                "already_running": True,
                "target_already_open": target_already_open,
                "cdp_validation": cdp_diag,
            },
            "next_step_if_failed": None,
        }

    browser_path = _detect_browser_path()
    debug_profile = Path(__file__).resolve().parents[4] / "webscraper" / "var" / "chrome-debug"
    proc = launch_debug_chrome(
        chrome_path=browser_path,
        user_data_dir=debug_profile,
        profile_name=payload.profile_name,
        port=payload.cdp_port,
    )
    launch_diagnostics = cdp_availability(payload.cdp_port, check_ws=True)
    _log(
        "auth_launch_debug_chrome "
        f"pid={proc.pid} cdp_port={payload.cdp_port} profile={payload.profile_name} "
        f"json_version_ok={launch_diagnostics.get('json_version_ok')} "
        f"ws_connectable={launch_diagnostics.get('ws_connectable')} "
        f"status={launch_diagnostics.get('status')} error={launch_diagnostics.get('error')} "
        f"launch_args=[--remote-debugging-port={payload.cdp_port},--remote-allow-origins=http://127.0.0.1:{payload.cdp_port},--remote-allow-origins=*]"
    )
    if str(launch_diagnostics.get("status")) == "ws_origin_rejected" or is_cdp_origin_rejected(str(launch_diagnostics.get("error") or "")):
        _mark_cdp_attach_failure(error=str(launch_diagnostics.get("error") or "CDP websocket origin rejected"), fatal=True)
        raise HTTPException(
            status_code=502,
            detail=(
                f"Chrome CDP websocket origin rejected on port {payload.cdp_port}. "
                f"Launch with --remote-allow-origins=http://127.0.0.1:{payload.cdp_port} "
                "or --remote-allow-origins=*."
            ),
        )
    _clear_cdp_attach_failure()
    return {
        "ok": True,
        "mode_used": "cdp",
        "details": {
            "pid": proc.pid,
            "cdp_port": payload.cdp_port,
            "user_data_dir": str(debug_profile),
            "profile_name": payload.profile_name,
            "cdp_validation": launch_diagnostics,
        },
        "next_step_if_failed": None,
    }


@app.get("/api/auth/doctor")
def api_auth_doctor():
    db_file = Path(db_path())
    auth_table_ready = False
    db_error: str | None = None
    try:
        db.ensure_indexes(db_path())
        with sqlite3.connect(db_file) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='auth_cookies'"
            ).fetchone()
            auth_table_ready = bool(row and row[0] > 0)
    except Exception as exc:  # pragma: no cover - defensive health path
        db_error = str(exc)

    doctor = auth_doctor()
    return {
        "ok": _has_python_multipart() and db_file.exists() and auth_table_ready and not db_error,
        "multipart_installed": _has_python_multipart(),
        "db_path": str(db_file),
        "db_exists": db_file.exists(),
        "auth_cookie_table_ready": auth_table_ready,
        "error": db_error,
        "auth": doctor,
    }


@app.get("/api/auth/auto_status")
def api_auth_auto_status():
    """Return the state of the auto Chrome launcher and CDP login watcher."""
    with DEBUG_CHROME_PROC_LOCK:
        proc = DEBUG_CHROME_PROC
    proc_alive = proc is not None and proc.poll() is None
    cdp_up = _is_cdp_available(DEFAULT_CDP_PORT)
    tab_urls = _get_cdp_tab_urls(DEFAULT_CDP_PORT) if cdp_up else []
    post_login = [u for u in tab_urls if _url_is_post_login(u)]
    with AUTH_STATE_LOCK:
        auth_snapshot = {
            "authenticated": AUTH_STATE.authenticated,
            "mode": AUTH_STATE.mode,
            "detail": AUTH_STATE.detail,
        }
    with AUTO_SEED_STATE_LOCK:
        auto_seed_snapshot = dict(AUTO_SEED_STATE)
    return {
        "auto_launch_enabled": AUTO_LAUNCH_DEBUG_CHROME,
        "debug_chrome_pid": proc.pid if proc_alive else None,
        "debug_chrome_alive": proc_alive,
        "cdp_port": DEFAULT_CDP_PORT,
        "cdp_available": cdp_up,
        "open_tabs": len(tab_urls),
        "post_login_tabs": post_login,
        "debug_browser_running": bool(auto_seed_snapshot.get("debug_browser_running")) or cdp_up or proc_alive,
        "cdp_attach_failed": bool(auto_seed_snapshot.get("cdp_attach_failed")),
        "last_cdp_error": auto_seed_snapshot.get("last_cdp_error"),
        "auth_seed_in_progress": bool(auto_seed_snapshot.get("auth_seed_in_progress")),
        "last_seed_attempt_at": auto_seed_snapshot.get("last_seed_attempt_at"),
        "next_seed_attempt_at": auto_seed_snapshot.get("next_seed_attempt_at"),
        "fatal_cdp_error_at": auto_seed_snapshot.get("fatal_cdp_error_at"),
        **auth_snapshot,
    }


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
def api_tickets(handle: str | None = None, q: str | None = None, status: str | None = None, page: int = 1, pageSize: int = 50):
    return db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=pageSize)


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row["artifacts"] = db.get_artifacts(db_path(), row["ticket_id"], row["handle"])
    return row


@app.get("/api/artifacts")
def api_artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


@app.get("/api/health")
def api_health():
    stats_payload = db.get_stats(db_path())
    stats_payload = {**stats_payload, "tickets": int(stats_payload.get("total_tickets", 0))}
    return {
        "ok": True,
        "status": "ok",
        "version": app.version,
        "db_path": db_path(),
        "db_exists": Path(db_path()).exists(),
        "last_updated_utc": stats_payload.get("last_updated_utc"),
        "total_handles": stats_payload.get("total_handles", 0),
        "total_tickets": stats_payload.get("total_tickets", 0),
        "stats": stats_payload,
    }


@app.get("/api/system/status")
def api_system_status_v2():
    return ORCHESTRATOR.system_status().model_dump()


@app.post("/api/browser/detect")
def api_browser_detect(
    payload: BrowserDetectRequest | None = None,
    browser: str | None = Query(default=None),
    cdp_port: int | None = Query(default=None, ge=1, le=65535),
):
    resolved_browser = (browser or (payload.browser if payload else None) or "chrome").strip().lower() or "chrome"
    resolved_cdp_port = int(cdp_port or (payload.cdp_port if payload else None) or DEFAULT_CDP_PORT)
    detection = _detect_browser_session(browser=resolved_browser, cdp_port=resolved_cdp_port)
    return ORCHESTRATOR.record_browser_detection(detection).model_dump()


@app.post("/api/orchestrator/auth/seed")
def api_orchestrator_auth_seed():
    return ORCHESTRATOR.seed_auth().model_dump()


@app.post("/api/orchestrator/auth/validate")
def api_orchestrator_auth_validate():
    return ORCHESTRATOR.validate_auth().model_dump()


@app.post("/api/scrape/run")
def api_scrape_run_v2():
    return ORCHESTRATOR.run_scrape().model_dump()


@app.post("/api/scrape/run-e2e")
def api_scrape_run_e2e():
    return ORCHESTRATOR.run_end_to_end()


@app.post("/api/scrape/selenium_fallback")
def api_scrape_selenium_fallback():
    handles = _load_selenium_fallback_handles()
    if not handles:
        raise HTTPException(status_code=400, detail="No handles available to scrape")
    now = _iso_now()
    job_id = str(uuid.uuid4())
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=None,
        mode="selenium_fallback",
        ticket_limit=None,
        status="queued",
        created_utc=now,
        handles=handles,
    )
    _append_event("info", "selenium_fallback_queued", job_id=job_id, meta={"event": "queued", "handles": len(handles)})
    threading.Thread(
        target=_run_scrape_job,
        kwargs={"job_id": job_id, "handles": handles, "login_timeout_seconds": SELENIUM_LOGIN_TIMEOUT_SECONDS},
        daemon=True,
    ).start()
    return {"queued": True, "job_id": job_id, "handles_total": len(handles), "status": "queued"}


class ScrapeStartRequest(BaseModel):
    resume_from_handle: str | None = None


@app.post("/api/scrape/start")
def api_scrape_start(payload: ScrapeStartRequest | None = None):
    """Primary endpoint to start (or resume) a scrape job.

    Accepts optional ``resume_from_handle`` to skip all handles up to and
    including the given handle.  If omitted, the last completed handle stored
    in ``var/kb/scrape_state.json`` is used automatically.
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
    _append_event("info", "scrape_queued", job_id=job_id, meta={"event": "queued", "handles": len(handles), "resume_from": resume})
    threading.Thread(
        target=_run_scrape_job,
        kwargs={"job_id": job_id, "handles": handles, "login_timeout_seconds": SELENIUM_LOGIN_TIMEOUT_SECONDS, "resume_from_handle": resume},
        daemon=True,
    ).start()
    return {"queued": True, "job_id": job_id, "handles_total": len(handles), "status": "queued", "resume_from_handle": resume}


@app.get("/api/scrape/state")
def api_scrape_state():
    """Return the last completed handle and other state from var/kb/scrape_state.json."""
    state_path = kb_dir() / "scrape_state.json"
    if not state_path.exists():
        return {"last_completed_handle": None, "updated_utc": None}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read scrape state: {exc}") from exc


@app.get("/api/jobs")
def api_jobs_v2():
    return {"items": [job.model_dump() for job in ORCHESTRATOR.list_jobs()]}


@app.get("/api/jobs/{job_id}")
def api_job_v2(job_id: str):
    job = ORCHESTRATOR.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@app.get("/api/jobs/{job_id}/events")
def api_scrape_job_events(job_id: str, limit: int = Query(default=50, ge=1, le=500)):
    """Return the last *limit* events for a scrape job as JSON (non-streaming)."""
    rows = db.get_scrape_events(db_path(), job_id, limit=limit)
    return {"job_id": job_id, "events": rows}


@app.get("/api/db/status")
def api_db_status():
    return ORCHESTRATOR.system_status().db_counts


@app.get("/system/status")
def api_system_status():
    auth = _auth_state_payload()
    return {
        "ok": True,
        "backend": api_health(),
        "auth": auth,
        "queue_depth": len(JOB_QUEUE),
        "current_job_id": CURRENT_JOB_ID,
    }


@app.get("/system/logs")
def api_system_logs(limit: int = Query(default=100, ge=1, le=1000)):
    items = db.get_latest_events(db_path(), limit=limit)
    return {"items": items}


@app.get("/auth/status")
def auth_status_alias(request: Request):
    return api_auth_status(request)


@app.post("/auth/open-login")
def auth_open_login(request: Request):
    payload = LaunchBrowserRequest()
    return api_auth_launch_browser(request, payload)


@app.post("/auth/check")
def auth_check(request: Request):
    return api_auth_validate_post(request, ValidateAuthRequest())


@app.post("/jobs/ingest-handle")
def jobs_ingest_handle(payload: dict[str, Any]):
    handle = _normalize_handle(str(payload.get("handle") or ""))
    now = _iso_now()
    job_id = str(uuid.uuid4())
    db.upsert_company(db_path(), handle=handle, last_ingest_job_id=job_id, now_utc=now)
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=handle,
        mode="selected",
        ticket_limit=int(payload.get("ticket_limit") or 50),
        status="queued",
        created_utc=now,
        handles=[handle],
    )
    with JOB_QUEUE_LOCK:
        JOB_QUEUE.append(
            QueueJob(
                job_id=job_id,
                run_id=datetime.now(timezone.utc).strftime("api_%Y%m%d_%H%M%S") + f"_{os.getpid()}",
                mode="selected",
                handle=handle,
                handles=[handle],
                rescrape=bool(payload.get("rescrape", False)),
                refresh_handles=False,
                scrape_mode="full" if bool(payload.get("full", False)) else "incremental",
                ticket_limit=int(payload.get("ticket_limit") or 50),
            )
        )
    _append_event("info", f"Queued ingest-handle job for {handle}", handle=handle, job_id=job_id)
    return {"ok": True, "job_id": job_id, "handle": handle, "status": "queued"}


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


@app.get("/handles")
def handles_alias(q: str = "", limit: int = Query(default=200, ge=1, le=5000), offset: int = Query(default=0, ge=0)):
    return {"items": db.list_handles_summary(db_path(), q=q, limit=limit, offset=offset)}


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


@app.get("/jobs/{job_id}")
def job_status_alias(job_id: str):
    job = db.get_scrape_job(db_path(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "result": job.get("result"),
        "error_message": job.get("error_message"),
        "created_utc": job.get("created_utc"),
        "started_utc": job.get("started_utc"),
        "finished_utc": job.get("finished_utc"),
    }


def _log_api_enabled() -> bool:
    raw = os.getenv("WEBSCRAPER_LOGS_ENABLED")
    if raw is None:
        raw = os.getenv("SCRAPER_ENABLE_LOG_API")
    if raw is not None:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    env_name = (os.getenv("ENV") or os.getenv("APP_ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return env_name in {"dev", "development", "local", "test"}


def _ensure_log_api_enabled(request: Request) -> None:
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    if not _log_api_enabled():
        raise HTTPException(status_code=403, detail={"error": "logs_disabled", "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"})


def _resolve_log_file(name: str) -> Path:
    candidate = (LOG_DIR / name).resolve()
    if candidate.parent != LOG_DIR or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    return candidate


@app.get("/api/logs/enabled")
def api_logs_enabled(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    return {"enabled": _log_api_enabled(), "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"}


def _tail_file(path: Path, lines: int) -> list[str]:
    if lines <= 0:
        return []
    chunk_size = 8192
    data = bytearray()
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        file_size = handle.tell()
        while file_size > 0 and data.count(b"\n") <= lines:
            read_size = min(chunk_size, file_size)
            file_size -= read_size
            handle.seek(file_size)
            data = handle.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-lines:]


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
def api_logs_tail(request: Request, name: str = Query(...), lines: int = Query(2000, ge=1, le=5000)):
    _ensure_log_api_enabled(request)
    log_file = _resolve_log_file(name)
    rows = _tail_file(log_file, lines)
    return {"name": log_file.name, "lines": rows}


@app.get("/health")
def health():
    return api_health()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/scrape")
def api_scrape_legacy(payload: dict[str, Any]):
    mode = payload.get("mode")
    if mode == "handle":
        mode = "one"
    if mode not in {"all", "one"}:
        raise HTTPException(status_code=400, detail="Unsupported mode for legacy endpoint")

    if mode == "one":
        handle = str(payload.get("handle") or "").strip()
        if not handle:
            raise HTTPException(status_code=400, detail="handle is required when mode='one'")
        out = api_scrape_handles(
            ScrapeHandlesRequest(
                handles=[handle],
                mode="normal",
                options={"rescrape": bool(payload.get("rescrape"))},
            )
        )
        return {"jobId": out["job_id"], "started": True}

    req = StartScrapeRequest(
        mode=mode,
        handle=payload.get("handle"),
        rescrape=bool(payload.get("rescrape")),
        refresh_handles=bool(payload.get("refresh_handles", True)),
    )
    out = api_scrape_start(req)
    return {"jobId": out["job_id"], "started": out["started"]}


@app.get("/api/scrape/{job_id}/events")
def api_scrape_events(job_id: str):
    def gen():
        last_id = 0
        while True:
            items = db.get_latest_events(db_path(), limit=200)
            fresh = [item for item in reversed(items) if int(item.get("id") or 0) > last_id and (item.get("meta") or {}).get("job_id") == job_id]
            for item in fresh:
                last_id = int(item["id"])
                payload = {
                    "ts": item["created_utc"],
                    "level": item["level"],
                    "event": "scrape.progress",
                    "message": item["message"],
                    "data": item.get("meta") or {},
                }
                yield f"data: {json.dumps(payload)}\\n\\n"
            status = db.get_scrape_job(db_path(), job_id)
            if status and status.get("status") in {"completed", "failed"}:
                break
            time.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")



def run_api(*, host: str = "127.0.0.1", port: int = 8787, reload: bool = False, db_override: str | None = None) -> None:
    if db_override:
        os.environ["TICKETS_DB_PATH"] = str(Path(db_override).resolve())
    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=host, port=port, reload=reload, proxy_headers=False)


def _pip_check_required_deps() -> list[tuple[str, str, bool]]:
    checks = [
        ("fastapi", "fastapi>=0.115.0"),
        ("uvicorn", "uvicorn[standard]>=0.30.0"),
        ("multipart", "python-multipart>=0.0.9"),
    ]
    return [(module, requirement, importlib.util.find_spec(module) is not None) for module, requirement in checks]


def pip_check_command() -> int:
    missing = [(module, requirement) for module, requirement, ok in _pip_check_required_deps() if not ok]
    if not missing:
        print("[OK] All ticket API dependencies are installed.")
        return 0

    print("[FAIL] Missing required dependencies:")
    for module, requirement in missing:
        print(f"  - {module}: {requirement}")
    requirements = " ".join(requirement for _, requirement in missing)
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
                row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='auth_cookies'").fetchone()
                table_ok = bool(row and row[0] > 0)
        except Exception as exc:  # pragma: no cover - defensive cli path
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
        print("[OK] auth_cookies table is ready.")
    else:
        msg = "auth_cookies table check failed" if table_error else "auth_cookies table missing"
        detail = f": {table_error}" if table_error else ""
        print(f"[FAIL] {msg}{detail}", file=sys.stderr)

    return 0 if multipart_ok and db_ok and table_ok else 1

def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=db_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--doctor", action="store_true", help="Validate API runtime dependencies and exit")
    parser.add_argument("--pip-check", action="store_true", help="Print missing dependencies and pip install command")
    args = parser.parse_args()
    if args.pip_check:
        raise SystemExit(pip_check_command())
    if args.doctor:
        raise SystemExit(doctor_command())
    run_api(host=args.host, port=args.port, reload=args.reload, db_override=args.db)


if __name__ == "__main__":
    main()
