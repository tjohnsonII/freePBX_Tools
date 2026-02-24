from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List


def _safe_cookie_view(cookie: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": cookie.get("name"),
        "domain": cookie.get("domain"),
        "path": cookie.get("path"),
        "secure": cookie.get("secure"),
        "httpOnly": cookie.get("httpOnly"),
        "sameSite": cookie.get("sameSite"),
        "expiry_present": "expiry" in cookie or "expires" in cookie,
    }


def _safe_cdp_cookie_view(cookie: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": cookie.get("name"),
        "domain": cookie.get("domain"),
        "path": cookie.get("path"),
        "secure": cookie.get("secure"),
        "httpOnly": cookie.get("httpOnly"),
        "sameSite": cookie.get("sameSite"),
        "expiry_present": "expires" in cookie or "expiry" in cookie,
    }


def _detect_login_markers(page_text: str, has_password: bool, has_username: bool) -> Dict[str, Any]:
    text = page_text.lower()
    keyword_hits = [kw for kw in ("login", "sign in", "password", "username", "mfa", "sso") if kw in text]
    return {
        "has_password_input": has_password,
        "has_username_input": has_username,
        "text_keywords": keyword_hits,
    }


def _detect_search_markers(search_inputs: int, search_buttons: int, page_text: str) -> Dict[str, Any]:
    text = page_text.lower()
    return {
        "search_input_count": search_inputs,
        "search_button_count": search_buttons,
        "text_has_search": "search" in text,
    }


def _summarize_inputs(inputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "tag": item.get("tag"),
            "type": item.get("type"),
            "name": item.get("name"),
            "id": item.get("id"),
            "placeholder": item.get("placeholder"),
            "autocomplete": item.get("autocomplete"),
        }
        for item in inputs
    ]


def _summarize_forms(forms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "action": item.get("action"),
            "method": item.get("method"),
            "id": item.get("id"),
            "name": item.get("name"),
        }
        for item in forms
    ]


def _page_text_for_markers(driver: Any) -> str:
    try:
        return driver.execute_script(
            "return (document.body && document.body.innerText) ? document.body.innerText.slice(0, 4000) : '';"
        )
    except Exception:
        return ""


def collect_auth_signals(driver: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cookies": {},
        "cdp_cookies": {},
        "storage": {},
        "page": {},
        "likely_authenticated": False,
        "likely_authenticated_reasons": [],
        "errors": {},
    }

    cookies = []
    try:
        selenium_cookies = driver.get_cookies() or []
        cookies = [_safe_cookie_view(c) for c in selenium_cookies if isinstance(c, dict)]
        report["cookies"] = {
            "count": len(cookies),
            "items": cookies,
        }
    except Exception as exc:
        report["errors"]["selenium_cookies_error"] = str(exc)

    cdp_items: List[Dict[str, Any]] = []
    cdp_error = None
    try:
        cdp_payload = driver.execute_cdp_cmd("Network.getAllCookies", {})
        raw_cdp = cdp_payload.get("cookies", []) if isinstance(cdp_payload, dict) else []
        cdp_items = [_safe_cdp_cookie_view(c) for c in raw_cdp if isinstance(c, dict)]
    except Exception as exc:
        cdp_error = str(exc)
    if cdp_error:
        report["errors"]["cdp_cookies_error"] = cdp_error
    domain_histogram = Counter()
    for item in cdp_items:
        domain_histogram[item.get("domain") or ""] += 1
    report["cdp_cookies"] = {
        "count": len(cdp_items),
        "items": cdp_items,
        "domain_histogram": dict(domain_histogram),
    }

    local_storage_keys: List[str] = []
    session_storage_keys: List[str] = []
    try:
        local_storage_keys = driver.execute_script(
            "return Object.keys(window.localStorage || {});"
        )
    except Exception as exc:
        report["errors"]["local_storage_error"] = str(exc)
    try:
        session_storage_keys = driver.execute_script(
            "return Object.keys(window.sessionStorage || {});"
        )
    except Exception as exc:
        report["errors"]["session_storage_error"] = str(exc)
    report["storage"] = {
        "localStorage_keys": local_storage_keys if isinstance(local_storage_keys, list) else [],
        "sessionStorage_keys": session_storage_keys if isinstance(session_storage_keys, list) else [],
    }

    page_text = _page_text_for_markers(driver)
    try:
        ready_state = driver.execute_script("return document.readyState")
    except Exception:
        ready_state = None
    try:
        forms = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('form')).slice(0, 8).map(f => ({
                action: f.getAttribute('action'),
                method: f.getAttribute('method'),
                id: f.getAttribute('id'),
                name: f.getAttribute('name')
            }));
            """
        )
    except Exception:
        forms = []
    try:
        inputs = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('input, select, textarea')).slice(0, 12).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute('type'),
                name: el.getAttribute('name'),
                id: el.getAttribute('id'),
                placeholder: el.getAttribute('placeholder'),
                autocomplete: el.getAttribute('autocomplete')
            }));
            """
        )
    except Exception:
        inputs = []
    try:
        has_password = bool(driver.execute_script("return !!document.querySelector('input[type=\"password\"]');"))
    except Exception:
        has_password = False
    try:
        has_username = bool(
            driver.execute_script(
                "return !!document.querySelector('input[name*=\"user\" i], input[id*=\"user\" i], input[name*=\"email\" i]');"
            )
        )
    except Exception:
        has_username = False
    try:
        search_inputs = int(
            driver.execute_script(
                "return document.querySelectorAll('input[type=\"search\"], input[name*=\"search\" i], input[id*=\"search\" i]').length;"
            )
        )
    except Exception:
        search_inputs = 0
    try:
        search_buttons = int(
            driver.execute_script(
                "return document.querySelectorAll('button[type=\"submit\"], input[type=\"submit\"], button').length;"
            )
        )
    except Exception:
        search_buttons = 0

    login_markers = _detect_login_markers(page_text, has_password, has_username)
    search_markers = _detect_search_markers(search_inputs, search_buttons, page_text)

    report["page"] = {
        "title": getattr(driver, "title", None),
        "current_url": getattr(driver, "current_url", None),
        "ready_state": ready_state,
        "forms": _summarize_forms(forms if isinstance(forms, list) else []),
        "inputs": _summarize_inputs(inputs if isinstance(inputs, list) else []),
        "login_markers": login_markers,
        "search_markers": search_markers,
    }

    reasons: List[str] = []
    domains = [c.get("domain") or "" for c in cookies] + [c.get("domain") or "" for c in cdp_items]
    if any("123.net" in d for d in domains):
        reasons.append("cookie_domain_contains_123.net")
    login_hits = bool(login_markers.get("text_keywords")) or login_markers.get("has_password_input")
    search_hits = (
        search_markers.get("search_input_count", 0) > 0
        or search_markers.get("search_button_count", 0) > 0
        or search_markers.get("text_has_search")
    )
    if search_hits and not login_hits:
        reasons.append("search_markers_without_login_markers")
    report["likely_authenticated"] = bool(reasons)
    report["likely_authenticated_reasons"] = reasons

    return report


def write_auth_report(out_dir: str, report_dict: Dict[str, Any]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "auth_report.json")
    summary_path = os.path.join(out_dir, "auth_summary.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    cookies_count = report_dict.get("cookies", {}).get("count", 0)
    cdp_count = report_dict.get("cdp_cookies", {}).get("count", 0)
    local_keys = report_dict.get("storage", {}).get("localStorage_keys", [])
    session_keys = report_dict.get("storage", {}).get("sessionStorage_keys", [])
    likely = report_dict.get("likely_authenticated")
    reasons = report_dict.get("likely_authenticated_reasons", [])

    summary_lines = [
        "Auth diagnostics summary",
        f"Generated: {report_dict.get('generated_at')}",
        f"URL: {report_dict.get('page', {}).get('current_url')}",
        f"Title: {report_dict.get('page', {}).get('title')}",
        f"Selenium cookies: {cookies_count}",
        f"CDP cookies: {cdp_count}",
        f"localStorage keys: {len(local_keys)}",
        f"sessionStorage keys: {len(session_keys)}",
        f"Likely authenticated: {likely}",
        f"Reasons: {', '.join(reasons) if reasons else 'none'}",
    ]

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")
