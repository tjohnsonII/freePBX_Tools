"""
Ultimate Scraper (minimal baseline)

Smoke test:
python -m webscraper.ultimate_scraper --show --handles KPM --out webscraper/output/test --scrape-ticket-details --max-tickets 3 --save-html --resume

This clean baseline provides a single, minimal Selenium function to capture
basic page state and debug artifacts for a list of customer handles.

Advanced logic (dropdown selection, robust waits, HTML parsing, aiohttp/requests
paths, and cookie handling) will be reintroduced in small, tested stages.
"""

import os
import io
import contextlib
import argparse
import glob
import json
import logging
import re
import sys
import sqlite3
import tempfile
import time
import urllib.request
import urllib.parse
import hashlib
import importlib
import importlib.util
from datetime import datetime, timezone
from typing import Any, List, Optional, TYPE_CHECKING, cast

if __package__ in (None, ""):
    raise RuntimeError("Run as a module: python -m webscraper.ultimate_scraper")

if TYPE_CHECKING:
    from selenium import webdriver
    from webscraper.auth import AuthMode

if importlib.util.find_spec("bs4") is None:
    BeautifulSoup = None
    _BS4_IMPORT_ERROR = ImportError("BeautifulSoup (bs4) is not installed.")
else:
    from bs4 import BeautifulSoup
    _BS4_IMPORT_ERROR = None

PROFILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "edge_profile_tmp"))


class EdgeStartupError(RuntimeError):
    def __init__(self, message: str, edge_args: List[str], profile_dir: str, edge_binary: Optional[str]) -> None:
        details = [
            message,
            f"Edge args: {edge_args}",
            f"Profile dir: {profile_dir}",
            f"Edge binary: {edge_binary or 'Selenium Manager auto-detect'}",
            "Advice: profile may be locked or invalid; try --edge-temp-profile",
        ]
        super().__init__("\n".join(details))
        self.edge_args = edge_args
        self.profile_dir = profile_dir
        self.edge_binary = edge_binary


def _validate_path(label: str, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return path
    print(f"[WARN] {label} not found at '{path}'. Falling back to auto-detect.")
    return None


def edge_binary_path() -> Optional[str]:
    edge_binary_env = os.environ.get("EDGE_PATH") or os.environ.get("EDGE_BINARY_PATH")
    if edge_binary_env:
        resolved = _validate_path("Edge binary (env)", edge_binary_env)
        if resolved:
            print(f"[INFO] Using Edge binary from env: {resolved}")
            return resolved
    pf86 = os.environ.get("ProgramFiles(x86)")
    pf = os.environ.get("ProgramFiles")
    preferred = []
    if pf86:
        preferred.append(os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"))
    if pf:
        preferred.append(os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"))
    for candidate in preferred:
        resolved = _validate_path("Edge binary", candidate)
        if resolved:
            print(f"[INFO] Using Edge binary: {resolved}")
            return resolved
    print("[INFO] Using Selenium Manager to locate Edge binary.")
    return None


def edge_profile_dir(args: Any) -> str:
    auth_mode = getattr(args, "auth_dump", False) or getattr(args, "auth_pause", False)
    use_temp = getattr(args, "edge_temp_profile", False)
    if auth_mode and use_temp:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{run_id}_{os.getpid()}"
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "output", run_id))
        return os.path.join(base, "edge_tmp_profile")
    profile_dir_override = os.path.abspath(args.profile_dir) if getattr(args, "profile_dir", None) else None
    if profile_dir_override:
        return profile_dir_override
    env_dir = os.environ.get("EDGE_PROFILE_DIR")
    if env_dir:
        return os.path.abspath(env_dir)
    return PROFILE_DIR


def as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v if x).strip()
    return str(v).strip()


def require_beautifulsoup():
    if BeautifulSoup is None:
        raise RuntimeError(
            "BeautifulSoup (bs4) is required for HTML parsing. Install with `pip install beautifulsoup4`."
        ) from _BS4_IMPORT_ERROR
    return BeautifulSoup


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _FlushStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        try:
            self.flush()
        except Exception:
            pass


def _build_phase_logger(enabled: bool) -> logging.Logger:
    logger = logging.getLogger("ultimate_scraper.phase")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = []
    if enabled:
        handler = _FlushStreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def _write_run_metadata(output_dir: str, mode: str, run_id: Optional[str] = None) -> None:
    os.makedirs(output_dir, exist_ok=True)
    payload = {
        "extracted_at": _iso_utc_now(),
        "mode": mode,
        "run_id": run_id,
    }
    metadata_path = os.path.join(output_dir, "run_metadata.json")
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"[INFO] Wrote run metadata to {metadata_path}")
    except Exception as exc:
        print(f"[WARN] Could not write run metadata: {exc}")


def classes_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v if x).strip()
    return str(v).strip()


def normalize_label(label: str) -> str:
    cleaned = re.sub(r"[:\s]+$", "", label.strip())
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned.strip().lower())
    return cleaned.strip("_")


def parse_ticket_id(url: str) -> Optional[str]:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    query_pairs = urllib.parse.parse_qs(parsed.query or "")
    for key in ("ticket_id", "id", "ticket"):
        values = query_pairs.get(key) or []
        for value in values:
            numeric = re.search(r"\b(\d{12,})\b", value or "")
            if numeric:
                return numeric.group(1)
    path = parsed.path or ""
    for segment in reversed(path.rstrip("/").split("/")):
        numeric = re.search(r"\b(\d{12,})\b", segment or "")
        if numeric:
            return numeric.group(1)
    return None


def classify_url(url: str) -> str:
    if not url:
        return "other"
    lowered = url.strip().lower()
    if lowered.startswith("file://") or lowered.startswith("smb://"):
        return "file_share"
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if host == "secure.123.net" and "dsx_circuits.cgi" in path:
        return "dsx_circuit"
    if host == "noc-tickets.123.net":
        if path.startswith("/new_ticket"):
            return "new_ticket"
        if re.fullmatch(r"/ticket/\d{12,}", path.rstrip("/")):
            return "ticket_detail"
    return "other"


def build_ticket_url_entry(url: str) -> dict[str, Optional[str]]:
    kind = classify_url(url)
    ticket_id = parse_ticket_id(url) if kind == "ticket_detail" else None
    return {"url": url, "kind": kind, "ticket_id": ticket_id}


def _url_kind_priority(kind: str) -> int:
    return 0 if kind == "ticket_detail" else 1


class PhaseLogger:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def log(self, message: str) -> None:
        if self.enabled:
            print(message, flush=True)


def parse_ticket_id_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"ticket\s*id[:\s]*([A-Za-z0-9-]+)",
        r"\bid[:\s]*([A-Za-z0-9-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_label_value_pairs(soup: Any) -> dict:
    fields: dict[str, Any] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            raw_label = cells[0].get_text(" ", strip=True)
            raw_value = cells[1].get_text(" ", strip=True)
            if not raw_label or not raw_value:
                continue
            key = normalize_label(raw_label)
            if not key:
                continue
            existing = fields.get(key)
            if existing is None:
                fields[key] = raw_value
            elif isinstance(existing, list):
                if raw_value not in existing:
                    existing.append(raw_value)
            else:
                if raw_value != existing:
                    fields[key] = [existing, raw_value]
    return fields


def _value_for_keys(fields: dict, keys: List[str]) -> Optional[str]:
    for key in keys:
        value = fields.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            joined = " ".join(v for v in value if v)
            if joined:
                return joined
        else:
            if str(value).strip():
                return str(value).strip()
    return None


def _extract_contacts(fields: dict, text: str) -> List[dict]:
    contacts: List[dict] = []
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    phone_pattern = r"\+?\d[\d\s().-]{6,}"
    for key, value in fields.items():
        if "contact" in key or "phone" in key or "email" in key:
            val_text = " ".join(value) if isinstance(value, list) else str(value)
            contact = {"label": key, "raw": val_text}
            email_match = re.search(email_pattern, val_text)
            phone_match = re.search(phone_pattern, val_text)
            if email_match:
                contact["email"] = email_match.group(0)
            if phone_match:
                contact["phone"] = phone_match.group(0)
            contacts.append(contact)
    for email in sorted(set(re.findall(email_pattern, text))):
        contacts.append({"label": "email", "email": email})
    for phone in sorted(set(re.findall(phone_pattern, text))):
        contacts.append({"label": "phone", "phone": phone})
    return contacts


def _extract_associated_files(soup: Any) -> List[dict]:
    files: List[dict] = []
    for table in soup.find_all("table"):
        headers = [h.get_text(" ", strip=True).lower() for h in table.find_all("th")]
        header_text = " ".join(headers)
        if "file" not in header_text and "attachment" not in header_text:
            continue
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            entry = {
                "file_name": cells[0] if len(cells) > 0 else None,
                "size": cells[1] if len(cells) > 1 else None,
                "distinction": cells[2] if len(cells) > 2 else None,
                "description": cells[3] if len(cells) > 3 else None,
            }
            files.append(entry)
    return files


def extract_ticket_fields(html: str) -> dict:
    bs4 = require_beautifulsoup()
    soup = bs4(html, "html.parser")
    fields = extract_label_value_pairs(soup)
    raw_text = soup.get_text(" ", strip=True)
    full_text = " ".join(raw_text.split())

    company_value = _value_for_keys(fields, ["company", "company_name", "customer", "company_handle"])
    company_name = None
    company_code = None
    if company_value:
        match = re.match(r"^(.*?)(?:\(([^)]+)\))?$", company_value)
        if match:
            company_name = match.group(1).strip() if match.group(1) else company_value
            company_code = match.group(2).strip() if match.group(2) else None
        else:
            company_name = company_value

    subject = _value_for_keys(fields, ["subject", "issue", "ticket_subject"])
    status = _value_for_keys(fields, ["status", "ticket_status"])
    ticket_type = _value_for_keys(fields, ["type", "ticket_type"])
    circuit_id = _value_for_keys(fields, ["circuit_id", "circuit"])
    external_id = _value_for_keys(fields, ["external_id", "external_ticket_id", "external"])
    born_updated = _value_for_keys(fields, ["born_updated", "born_updated_line", "born_updated_date", "born_updated_time"])
    if not born_updated:
        match = re.search(r"born/updated\s*[:\s]*([^\n]+)", raw_text, flags=re.IGNORECASE)
        if match:
            born_updated = match.group(1).strip()

    address = _value_for_keys(fields, ["address", "service_address", "location"])
    access_hours = _value_for_keys(fields, ["access_hours", "access", "access_hours"])
    dispatch = _value_for_keys(fields, ["dispatch", "dispatch_info"])
    region = _value_for_keys(fields, ["region", "market"])
    work_involved = _value_for_keys(fields, ["work_involved", "work", "work_details"])
    quick_links = _value_for_keys(fields, ["quick_links", "quick_link", "links"])

    contacts = _extract_contacts(fields, full_text)
    associated_files = _extract_associated_files(soup)

    return {
        "company_name": company_name,
        "company_code": company_code,
        "subject": subject,
        "status": status,
        "type": ticket_type,
        "circuit_id": circuit_id,
        "external_id": external_id,
        "born_updated": born_updated,
        "address": address,
        "access_hours": access_hours,
        "dispatch": dispatch,
        "region": region,
        "work_involved": work_involved,
        "quick_links": quick_links,
        "contacts": contacts,
        "associated_files": associated_files,
        "full_page_text": full_text,
        "fields": fields,
    }


def save_ticket_json(kb_dir: str, ticket_id: str, data: dict) -> str:
    tickets_dir = os.path.join(kb_dir, "tickets")
    os.makedirs(tickets_dir, exist_ok=True)
    json_path = os.path.join(tickets_dir, f"{ticket_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return json_path


def init_sqlite(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            url TEXT,
            company_handle TEXT NULL,
            company_name TEXT NULL,
            subject TEXT NULL,
            status TEXT NULL,
            type TEXT NULL,
            circuit_id TEXT NULL,
            born_updated TEXT NULL,
            extracted_at TEXT NOT NULL,
            json_path TEXT NOT NULL,
            html_path TEXT NULL,
            full_text TEXT NULL,
            data_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def upsert_ticket(conn: sqlite3.Connection, data: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO tickets (
            ticket_id, url, company_handle, company_name, subject, status, type,
            circuit_id, born_updated, extracted_at, json_path, html_path, full_text, data_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("ticket_id"),
            data.get("url"),
            data.get("company_handle"),
            data.get("company_name"),
            data.get("subject"),
            data.get("status"),
            data.get("type"),
            data.get("circuit_id"),
            data.get("born_updated"),
            data.get("extracted_at"),
            data.get("json_path"),
            data.get("html_path"),
            data.get("full_text"),
            data.get("data_json"),
        ),
    )
    conn.commit()


def _parse_year_month(extracted_at: Optional[str], fallback_path: Optional[str]) -> str:
    if extracted_at:
        cleaned = extracted_at.rstrip("Z")
        try:
            parsed = datetime.fromisoformat(cleaned)
            return parsed.strftime("%Y-%m")
        except ValueError:
            pass
    if fallback_path and os.path.exists(fallback_path):
        try:
            ts = os.path.getmtime(fallback_path)
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m")
        except OSError:
            pass
    fallback_stamp = _iso_utc_now()
    try:
        return datetime.fromisoformat(fallback_stamp.rstrip("Z")).strftime("%Y-%m")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_existing_kb_keys(kb_jsonl: str) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    if not os.path.exists(kb_jsonl):
        return seen
    with open(kb_jsonl, "r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ticket_id = as_str(data.get("ticket_id"))
            handle = as_str(data.get("handle"))
            if ticket_id and handle:
                seen.add((handle, ticket_id))
    return seen


def _init_kb_sqlite(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets(
            handle TEXT,
            ticket_id TEXT,
            url TEXT,
            extracted_at TEXT,
            page_title TEXT,
            text TEXT,
            hash TEXT,
            word_count INTEGER,
            year_month TEXT,
            html_path TEXT,
            screenshot_path TEXT,
            PRIMARY KEY(handle, ticket_id)
        )
        """
    )
    conn.commit()
    return conn


def _upsert_kb_record(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO tickets (
            handle, ticket_id, url, extracted_at, page_title, text, hash, word_count,
            year_month, html_path, screenshot_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("handle"),
            record.get("ticket_id"),
            record.get("url"),
            record.get("extracted_at"),
            record.get("page_title"),
            record.get("text"),
            record.get("hash"),
            record.get("word_count"),
            record.get("year_month"),
            record.get("html_path"),
            record.get("screenshot_path"),
        ),
    )
    conn.commit()


def build_kb_index(
    out_dir: str,
    resume: bool,
    kb_jsonl: str,
    kb_sqlite: Optional[str],
) -> dict:
    tickets_root = os.path.join(out_dir, "tickets")
    if not os.path.isdir(tickets_root):
        print(f"[KB] Tickets folder not found at {tickets_root}")
        return {"processed": 0, "skipped": 0, "failed": 0, "total": 0}

    os.makedirs(os.path.dirname(kb_jsonl), exist_ok=True)
    seen_keys = _load_existing_kb_keys(kb_jsonl) if resume else set()
    mode = "a" if resume else "w"
    conn = _init_kb_sqlite(kb_sqlite) if kb_sqlite else None

    processed = 0
    skipped = 0
    failed = 0
    total = 0

    with open(kb_jsonl, mode, encoding="utf-8") as out_f:
        for handle in sorted(os.listdir(tickets_root)):
            handle_dir = os.path.join(tickets_root, handle)
            if not os.path.isdir(handle_dir):
                continue
            for ticket_id in sorted(os.listdir(handle_dir)):
                ticket_dir = os.path.join(handle_dir, ticket_id)
                if not os.path.isdir(ticket_dir):
                    continue
                total += 1
                key = (handle, ticket_id)
                if key in seen_keys:
                    skipped += 1
                    continue
                ticket_json_path = os.path.join(ticket_dir, "ticket.json")
                if not os.path.exists(ticket_json_path):
                    failed += 1
                    print(f"[KB] missing ticket.json for {handle}/{ticket_id}")
                    continue
                try:
                    with open(ticket_json_path, "r", encoding="utf-8") as fh:
                        ticket_data = json.load(fh)
                except Exception as exc:
                    failed += 1
                    print(f"[KB] failed to read {ticket_json_path}: {exc}")
                    continue

                text = as_str(ticket_data.get("text"))
                text = text[:20000]
                page_title = as_str(ticket_data.get("page_title")) or None
                extracted_at = as_str(ticket_data.get("extracted_at")) or None
                html_path = ticket_data.get("html_path")
                if not html_path:
                    candidate = os.path.join(ticket_dir, "page.html")
                    html_path = candidate if os.path.exists(candidate) else None
                screenshot_path = ticket_data.get("screenshot_path")
                if not screenshot_path:
                    candidate = os.path.join(ticket_dir, "page.png")
                    screenshot_path = candidate if os.path.exists(candidate) else None
                year_month = _parse_year_month(extracted_at, ticket_json_path)
                word_count = len(text.split()) if text else 0
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

                record = {
                    "ticket_id": ticket_data.get("ticket_id") or ticket_id,
                    "handle": ticket_data.get("handle") or handle,
                    "url": ticket_data.get("url"),
                    "extracted_at": extracted_at,
                    "page_title": page_title,
                    "text": text,
                    "html_path": html_path,
                    "screenshot_path": screenshot_path,
                    "source": ticket_data.get("source"),
                    "tags": [],
                    "hash": text_hash,
                    "word_count": word_count,
                    "year_month": year_month,
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                if conn:
                    _upsert_kb_record(conn, record)
                seen_keys.add(key)
                processed += 1

    if conn:
        conn.close()
    print(f"[KB] Summary: processed={processed} skipped={skipped} failed={failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed, "total": total}


def probe_edge_debugger(host: str, port: int, timeout: float) -> dict:
    url = f"http://{host}:{port}/json/version"
    result = {"ok": False, "url": url, "status": None, "error": None, "body": None}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            result["status"] = resp.status
            payload = resp.read().decode("utf-8", errors="replace")
            result["body"] = payload
            result["ok"] = resp.status == 200
    except Exception as exc:
        result["error"] = str(exc)
    return result


def edge_debug_targets(host: str, port: int, timeout: float) -> List[dict]:
    try:
        url = f"http://{host}:{port}/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, list):
            return payload
    except Exception:
        return []
    return []


def switch_to_target_tab(driver: Any, target_url: str, url_contains: Optional[str] = None) -> bool:
    if not driver:
        return False
    try:
        original = driver.current_window_handle
    except Exception:
        original = None
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
            if current == target_url or (url_contains and url_contains in current):
                return True
        except Exception:
            continue
    if original:
        try:
            driver.switch_to.window(original)
        except Exception:
            pass
    return False


def create_edge_driver(
    output_dir: str,
    headless: bool,
    attach: Optional[int],
    auto_attach: bool,
    attach_host: str,
    attach_timeout: float,
    fallback_profile_dir: str,
    profile_dir: Optional[str],
    profile_name: str,
    auth_dump: bool,
    auth_pause: bool,
    auth_timeout: int,
    auth_url: Optional[str],
    edge_temp_profile: bool,
    edge_kill_before: bool,
    show_browser: bool,
    headless_requested: bool = False,
) -> tuple["webdriver.Edge", bool, bool, Optional[str]]:
    # Local imports to avoid top-level dependency failures
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.common.exceptions import (
        InvalidSessionIdException,
        SessionNotCreatedException,
        WebDriverException,
    )

    _ = auth_timeout
    _ = show_browser

    EDGEDRIVER = os.environ.get("EDGEDRIVER_PATH")
    edge_driver_env = EDGEDRIVER
    edge_binary_path_resolved = edge_binary_path()
    profile_dir_override = os.path.abspath(profile_dir) if profile_dir else None
    edge_profile_env = profile_dir_override or os.environ.get("EDGE_PROFILE_DIR")
    default_profile = PROFILE_DIR
    legacy_profile = os.path.abspath(os.path.join(os.path.dirname(__file__), "chrome_profile"))
    edge_profile_dir_resolved = os.path.abspath(edge_profile_env.strip()) if edge_profile_env else default_profile
    resolved_fallback_profile_dir = os.path.abspath(fallback_profile_dir) if fallback_profile_dir else edge_profile_dir_resolved
    resolved_edge_profile_dir = edge_profile_dir_resolved if edge_profile_env else resolved_fallback_profile_dir
    if os.path.exists(legacy_profile) and not os.path.exists(default_profile):
        print("[WARN] legacy chrome_profile detected; using edge_profile_tmp instead")
    if resolved_edge_profile_dir:
        try:
            os.makedirs(resolved_edge_profile_dir, exist_ok=True)
        except Exception as e:
            print(f"[WARN] Could not create Edge profile directory '{resolved_edge_profile_dir}': {e}")
        print(f"[INFO] Edge profile dir (resolved): {resolved_edge_profile_dir}")
    chrome_profile_env = profile_dir_override or os.environ.get("CHROME_PROFILE_DIR")
    chrome_profile_dir = os.path.abspath(chrome_profile_env.strip()) if chrome_profile_env else legacy_profile
    print(f"[INFO] Chrome profile dir (resolved): {chrome_profile_dir}")

    debugger_address = os.environ.get("SCRAPER_DEBUGGER_ADDRESS")
    if debugger_address and not attach:
        print(f"[INFO] Attaching to existing Edge at {debugger_address}")
        if resolved_edge_profile_dir:
            print("[INFO] Attach mode ignores EDGE_PROFILE_DIR.")
        try:
            if ":" in debugger_address:
                host_part, port_part = debugger_address.split(":", 1)
                attach_host = host_part.strip() or attach_host
                attach = int(port_part.strip())
            else:
                attach = int(debugger_address.strip())
        except Exception as e:
            print(f"[WARN] Could not parse SCRAPER_DEBUGGER_ADDRESS='{debugger_address}': {e}")

    resolved_profile_name = profile_name or "Default"

    def _profile_lock_paths(profile_root: str) -> List[str]:
        return [
            os.path.join(profile_root, "SingletonLock"),
            os.path.join(profile_root, "SingletonCookie"),
            os.path.join(profile_root, "SingletonSocket"),
        ]

    def _profile_in_use(profile_root: str) -> bool:
        if not profile_root:
            return False
        try:
            import subprocess

            if os.name == "nt":
                try:
                    cmd = [
                        "wmic",
                        "process",
                        "where",
                        "name='msedge.exe'",
                        "get",
                        "CommandLine",
                    ]
                    output = subprocess.check_output(cmd, text=True, errors="ignore")
                except Exception:
                    output = ""
            else:
                output = subprocess.check_output(["ps", "-eo", "args"], text=True, errors="ignore")
            return profile_root in output
        except Exception:
            return False

    def _cleanup_stale_profile_locks(profile_root: str) -> bool:
        if not profile_root:
            return False
        lock_paths = _profile_lock_paths(profile_root)
        existing = [p for p in lock_paths if os.path.exists(p)]
        if not existing:
            return False
        if _profile_in_use(profile_root):
            print(f"[WARN] Profile appears in use; skipping lock cleanup for {profile_root}")
            return False
        removed_any = False
        for lock_path in existing:
            try:
                os.remove(lock_path)
                removed_any = True
                print(f"[INFO] Removed stale Edge lock file: {lock_path}")
            except Exception as e:
                print(f"[WARN] Could not remove lock file {lock_path}: {e}")
        return removed_any

    def _kill_edge_processes() -> None:
        if not edge_kill_before:
            return
        if os.name != "nt":
            print("[INFO] --edge-kill-before ignored on non-Windows platform.")
            return
        import subprocess

        for proc in ("msedge.exe", "msedgedriver.exe"):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"[INFO] taskkill issued for {proc}")
            except Exception as exc:
                print(f"[WARN] Failed to taskkill {proc}: {exc}")

    def _edge_processes_exist() -> bool:
        try:
            import psutil  # type: ignore
        except Exception:
            psutil = None
        if psutil:
            names = set()
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info.get("name") or ""
                    names.add(name.lower())
                except Exception:
                    continue
            return "msedge.exe" in names and "msedgedriver.exe" in names
        if os.name == "nt":
            import subprocess

            try:
                output = subprocess.check_output(["tasklist"], text=True, errors="ignore").lower()
            except Exception:
                return False
            return "msedge.exe" in output and "msedgedriver.exe" in output
        print("[WARN] Process check skipped (no psutil, non-Windows).")
        return True

    def _confirm_edge_processes(edge_args: List[str], current_profile_dir: str) -> None:
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if _edge_processes_exist():
                return
            time.sleep(0.2)
        raise EdgeStartupError(
            "Edge appears to have exited immediately after startup.",
            edge_args=edge_args,
            profile_dir=current_profile_dir,
            edge_binary=edge_binary_path_resolved,
        )

    def _make_temp_profile_dir() -> str:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{run_id}_{os.getpid()}"
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "output", run_id))
        temp_dir = os.path.join(base, "edge_tmp_profile")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def _build_edge_options(current_profile_dir: Optional[str], allow_headless: bool) -> tuple["EdgeOptions", List[str]]:
        edge_options = EdgeOptions()
        edge_args: List[str] = []
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option("useAutomationExtension", False)
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_args.append("--disable-blink-features=AutomationControlled")
        # Allow navigating IP/under-secured endpoints without blocking
        edge_options.add_argument("--ignore-certificate-errors")
        edge_args.append("--ignore-certificate-errors")
        edge_options.add_argument("--allow-insecure-localhost")
        edge_args.append("--allow-insecure-localhost")
        # Capture browser console logs for troubleshooting
        try:
            edge_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        except Exception:
            pass
        if edge_binary_path_resolved:
            edge_options.binary_location = edge_binary_path_resolved
        auth_mode = auth_dump or auth_pause
        if auth_mode:
            for arg in ("--window-position=0,0", "--window-size=1400,900", "--start-maximized"):
                edge_options.add_argument(arg)
                edge_args.append(arg)
        if current_profile_dir:
            edge_options.add_argument(f"--user-data-dir={current_profile_dir}")
            edge_args.append(f"--user-data-dir={current_profile_dir}")
            edge_options.add_argument(f"--profile-directory={resolved_profile_name}")
            edge_args.append(f"--profile-directory={resolved_profile_name}")
        if allow_headless and headless:
            edge_options.add_argument("--headless=new")
            edge_args.append("--headless=new")
            edge_options.add_argument("--disable-gpu")
            edge_args.append("--disable-gpu")
            edge_options.add_argument("--no-sandbox")
            edge_args.append("--no-sandbox")
        return edge_options, edge_args

    attach_requested = bool(attach or auto_attach)
    plan = []
    if attach:
        plan.append(("ATTACH_EXPLICIT", attach))
    if auto_attach and not attach:
        plan.append(("ATTACH_AUTO", 9222))
    if not attach_requested:
        plan.append(("LAUNCH_FALLBACK", None))

    edgedriver_path = _validate_path("EdgeDriver", edge_driver_env or EDGEDRIVER)
    last_error: Optional[Exception] = None

    for mode, port in plan:
        allow_headless = False if (attach_requested and not headless_requested) else True
        edge_options, edge_args = _build_edge_options(None, allow_headless=allow_headless)

        if mode in ("ATTACH_EXPLICIT", "ATTACH_AUTO"):
            attach_port = cast(int, port)
            debugger_address = f"{attach_host}:{attach_port}"
            probe_result = probe_edge_debugger(attach_host, attach_port, attach_timeout)
            if not probe_result["ok"]:
                last_error = RuntimeError(f"Edge debug endpoint not reachable at {debugger_address}")
                print(f"[ATTACH] failed: {last_error}; probe={probe_result}")
                curl_cmd = f'curl "{probe_result["url"]}"'
                edge_bin = edge_binary_path_resolved or "msedge.exe"
                profile_hint = os.path.join(os.environ.get("USERNAME", "C:\\Temp"), "edge_remote_profile")
                print("[ATTACH] Troubleshooting:")
                print(f"  curl test: {curl_cmd}")
                print(
                    "  PowerShell launch: "
                    f'& "{edge_bin}" --remote-debugging-port={attach_port} --user-data-dir="{profile_hint}"'
                )
                raise SystemExit(2)
            edge_options.add_experimental_option("debuggerAddress", debugger_address)
            print(f"[INFO] Edge args: {edge_args}")
            try:
                service = EdgeService(log_output=os.path.join(output_dir, "msedgedriver.log"))
                new_driver = webdriver.Edge(service=service, options=edge_options)
            except Exception as exc:
                last_error = exc
                print(f"[ATTACH] failed: {exc}; probe={probe_result}")
                curl_cmd = f'curl "{probe_result["url"]}"'
                edge_bin = edge_binary_path_resolved or "msedge.exe"
                profile_hint = os.path.join(os.environ.get("USERNAME", "C:\\Temp"), "edge_remote_profile")
                print("[ATTACH] Troubleshooting:")
                print(f"  curl test: {curl_cmd}")
                print(
                    "  PowerShell launch: "
                    f'& "{edge_bin}" --remote-debugging-port={attach_port} --user-data-dir="{profile_hint}"'
                )
                raise SystemExit(2)
            print(f"[INFO] Driver init mode: {mode}")
            print(f"[INFO] Edge attached. Session id: {new_driver.session_id}")
            try:
                title = new_driver.title
            except Exception:
                title = "<unavailable>"
            try:
                current_url = new_driver.current_url
            except Exception:
                current_url = "<unavailable>"
            print(f"[ATTACH] success {debugger_address} title='{title}' url='{current_url}'")
            found = switch_to_target_tab(
                new_driver,
                auth_url or "",
                url_contains="secure.123.net/cgi-bin/web_interface/admin/",
            )
            if not found and auth_url:
                try:
                    new_driver.get(auth_url)
                except Exception:
                    pass
            return new_driver, False, True, None

        if mode == "LAUNCH_FALLBACK":
            _kill_edge_processes()
            fallback_dir = resolved_edge_profile_dir
            temp_profile_used = False
            if edge_temp_profile and not profile_dir:
                fallback_dir = _make_temp_profile_dir()
                temp_profile_used = True
            try:
                os.makedirs(fallback_dir, exist_ok=True)
            except Exception as e:
                print(f"[WARN] Could not create fallback Edge profile directory '{fallback_dir}': {e}")
            edge_options, edge_args = _build_edge_options(fallback_dir, allow_headless=True)
            print(f"[INFO] Edge args: {edge_args}")
            attempted_lock_cleanup = False
            while True:
                try:
                    if edgedriver_path:
                        print(f"[INFO] Using custom EdgeDriver path: {edgedriver_path}")
                        service = EdgeService(edgedriver_path, log_output=os.path.join(output_dir, "msedgedriver.log"))
                        new_driver = webdriver.Edge(service=service, options=edge_options)
                    else:
                        print("[INFO] Using Selenium Manager for EdgeDriver resolution.")
                        service = EdgeService(log_output=os.path.join(output_dir, "msedgedriver.log"))
                        new_driver = webdriver.Edge(service=service, options=edge_options)
                    _confirm_edge_processes(edge_args, fallback_dir)
                    print(f"[INFO] Driver init mode: {mode}")
                    print(f"[INFO] Edge started. Session id: {new_driver.session_id}")
                    if auth_url:
                        try:
                            new_driver.get(auth_url)
                        except Exception:
                            pass
                    return new_driver, True, False, fallback_dir
                except (InvalidSessionIdException, SessionNotCreatedException, WebDriverException, EdgeStartupError) as exc:
                    last_error = exc
                    if fallback_dir and not attempted_lock_cleanup:
                        attempted_lock_cleanup = True
                        if _cleanup_stale_profile_locks(fallback_dir):
                            print("[WARN] Retrying Edge launch after clearing stale profile locks.")
                            continue
                    if not temp_profile_used:
                        temp_profile_used = True
                        temp_dir = _make_temp_profile_dir()
                        edge_options, edge_args = _build_edge_options(temp_dir, allow_headless=True)
                        print(f"[INFO] Edge args: {edge_args}")
                        print(
                            "[WARN] Edge failed to start with current profile. Retrying once with a fresh temp profile: "
                            f"{temp_dir}"
                        )
                        fallback_dir = temp_dir
                        continue
                    print(
                        "[ERROR] Edge session could not be created. This may be due to an Edge/"
                        "EdgeDriver version mismatch, profile lock, or enterprise policy restrictions."
                    )
                    break

    if last_error:
        raise last_error
    raise RuntimeError("Edge driver could not be initialized.")


def save_cookie_store(
    driver: Any,
    cookie_store_path: str,
    *,
    label: Optional[str] = None,
    phase_logger: Optional[PhaseLogger] = None,
    merge: bool = True,
    skip_if_empty: bool = True,
) -> int:
    store_label = label or "cookie_store"
    if not cookie_store_path:
        print(f"[COOKIES] save skipped label={store_label} reason=missing_path", flush=True)
        return 0
    try:
        latest_cookies = driver.get_cookies()
    except Exception as exc:
        print(f"[COOKIES] save failed label={store_label} path={cookie_store_path} error={exc}", flush=True)
        return 0

    if not latest_cookies and skip_if_empty:
        print(
            f"[COOKIES] save skipped (0 cookies) path={cookie_store_path} (existing file retained)",
            flush=True,
        )
        return 0

    merged_or_replaced = 0
    final_cookies = latest_cookies
    if merge and os.path.exists(cookie_store_path):
        try:
            with open(cookie_store_path, "r", encoding="utf-8") as existing_file:
                existing_data = json.load(existing_file)
            existing_cookies = existing_data.get("cookies", []) if isinstance(existing_data, dict) else existing_data
            if not isinstance(existing_cookies, list):
                existing_cookies = []
        except Exception as exc:
            print(f"[COOKIES] merge read failed path={cookie_store_path} error={exc}; using latest only", flush=True)
            existing_cookies = []

        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for cookie in existing_cookies:
            if not isinstance(cookie, dict):
                continue
            key = (str(cookie.get("domain") or ""), str(cookie.get("path") or "/"), str(cookie.get("name") or ""))
            merged[key] = cookie
        for cookie in latest_cookies:
            if not isinstance(cookie, dict):
                continue
            key = (str(cookie.get("domain") or ""), str(cookie.get("path") or "/"), str(cookie.get("name") or ""))
            if key in merged:
                merged_or_replaced += 1
            merged[key] = cookie
        final_cookies = list(merged.values())

    unique_domains = len({str(cookie.get("domain") or "") for cookie in final_cookies if isinstance(cookie, dict)})
    payload = {
        "version": 1,
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": str(getattr(driver, "current_url", "") or ""),
        "cookies": final_cookies,
    }

    os.makedirs(os.path.dirname(os.path.abspath(cookie_store_path)) or ".", exist_ok=True)
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=os.path.dirname(os.path.abspath(cookie_store_path)) or ".") as tmp_file:
            tmp_path = tmp_file.name
            json.dump(payload, tmp_file, indent=2)
        os.replace(tmp_path, cookie_store_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    print(
        f"[COOKIES] save complete saved={len(final_cookies)} merged_or_replaced={merged_or_replaced} domains={unique_domains} path={cookie_store_path}",
        flush=True,
    )
    if phase_logger:
        phase_logger.log(
            f"[{_iso_utc_now()}] PHASE COOKIES_SAVE saved={len(final_cookies)} merged_or_replaced={merged_or_replaced} domains={unique_domains} path={cookie_store_path}"
        )
    return len(final_cookies)


def load_cookie_store(
    driver: Any,
    cookie_store_path: str,
    *,
    phase_logger: Optional[PhaseLogger] = None,
    require_domains: Optional[List[str]] = None,
) -> int:
    from selenium.common.exceptions import WebDriverException

    if not cookie_store_path or not os.path.exists(cookie_store_path):
        print(f"[COOKIES] load skipped missing_file path={cookie_store_path}", flush=True)
        return 0

    try:
        with open(cookie_store_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        print(f"[COOKIES] load failed path={cookie_store_path} error={exc}", flush=True)
        return 0

    cookies = raw.get("cookies", []) if isinstance(raw, dict) else raw
    if not isinstance(cookies, list):
        print(f"[COOKIES] load failed path={cookie_store_path} reason=invalid_format", flush=True)
        return 0

    domain_filter = {d.lower().lstrip(".") for d in (require_domains or []) if d}
    grouped: dict[str, List[dict[str, Any]]] = {}
    sanitized_count = 0
    for c in cookies:
        if not isinstance(c, dict):
            continue
        domain_raw = str(c.get("domain") or "").strip()
        domain = domain_raw.lstrip(".").lower()
        if not domain:
            continue
        if domain_filter and domain not in domain_filter:
            continue
        cookie = dict(c)
        if isinstance(cookie.get("expiry"), float):
            cookie["expiry"] = int(cookie["expiry"])
            sanitized_count += 1
        if "sameSite" in cookie and str(cookie.get("sameSite") or "").lower() not in {"strict", "lax", "none"}:
            cookie.pop("sameSite", None)
            sanitized_count += 1
        grouped.setdefault(domain, []).append(cookie)

    added = 0
    rejected: List[str] = []
    for domain, domain_cookies in grouped.items():
        base_url = f"https://{domain}/"
        try:
            driver.get(base_url)
        except Exception as exc:
            print(f"[COOKIES] domain bootstrap failed domain={domain} url={base_url} error={exc}", flush=True)
            continue
        domain_added = 0
        for cookie in domain_cookies:
            try:
                driver.add_cookie(cookie)
                added += 1
                domain_added += 1
            except WebDriverException as exc:
                rejected.append(f"{domain}:{cookie.get('name','?')}:{exc}")
        print(f"[COOKIES] domain loaded domain={domain} added={domain_added} total={len(domain_cookies)}", flush=True)

    if rejected:
        examples = "; ".join(rejected[:3])
        print(f"[COOKIES] rejected count={len(rejected)} examples={examples}", flush=True)

    try:
        driver.get("https://noc-tickets.123.net/")
        driver.refresh()
    except Exception as exc:
        print(f"[COOKIES] post-load navigation warning error={exc}", flush=True)

    print(
        f"[COOKIES] load complete loaded={added} sanitized={sanitized_count} domains={len(grouped)} path={cookie_store_path}",
        flush=True,
    )
    if phase_logger:
        phase_logger.log(
            f"[{_iso_utc_now()}] PHASE COOKIES_LOAD loaded={added} sanitized={sanitized_count} domains={len(grouped)} path={cookie_store_path}"
        )
    return added


def save_cookies_json(driver: Any, path: str) -> None:
    save_cookie_store(driver, path, label="legacy_cookie_json", merge=False, skip_if_empty=True)


def load_cookies_json(driver: Any, path: str) -> bool:
    return load_cookie_store(driver, path) > 0


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _ensure_http_cookies(
    cookie_path: str,
    output_dir: str,
    profile_dir_override: Optional[str],
    profile_name: str,
    resolved_profiles: List[str],
    resolved_cookies: List[str],
    auth_mode_value: Optional[str],
    auth_profile_only: bool,
    headless: bool,
    attach: Optional[int],
    auto_attach: bool,
    attach_host: str,
    attach_timeout: float,
    fallback_profile_dir: str,
    edge_temp_profile: bool,
    edge_kill_before: bool,
    show_browser: bool,
    edge_binary_path_resolved: Optional[str],
    edge_driver_env: Optional[str],
    auth_username: Optional[str],
    auth_password: Optional[str],
    auth_check_url: Optional[str],
    target_url: str,
) -> bool:
    if cookie_path and os.path.exists(cookie_path):
        return True

    auth_symbols = _resolve_auth_symbols()
    if not auth_symbols:
        print("[WARN] Auth module unavailable; cannot bootstrap cookies for HTTP mode.")
        return False

    AuthContext, AuthMode, authenticate = auth_symbols
    (
        auth_modes,
        auth_profile_candidates,
        auth_cookie_candidates,
        _profile_only_enabled,
    ) = build_auth_strategy_plan(
        profile_dir_override=profile_dir_override,
        profile_name=profile_name,
        resolved_profiles=resolved_profiles,
        resolved_cookies=resolved_cookies,
        cookie_file_path=cookie_path,
        auth_mode_value=auth_mode_value,
        profile_only_flag=auth_profile_only,
    )

    auth_ctx = AuthContext(
        base_url=target_url,
        auth_check_url=auth_check_url or target_url,
        preferred_browser="edge",
        profile_dirs=auth_profile_candidates,
        profile_name=profile_name,
        cookie_files=auth_cookie_candidates,
        username=auth_username,
        password=auth_password,
        headless=headless,
        timeout_sec=30,
        output_dir=output_dir,
        attach=attach,
        auto_attach=auto_attach,
        attach_host=attach_host,
        attach_timeout=attach_timeout,
        fallback_profile_dir=fallback_profile_dir,
        edge_temp_profile=edge_temp_profile,
        edge_kill_before=edge_kill_before,
        show_browser=show_browser,
        edge_binary=edge_binary_path_resolved,
        edgedriver_path=edge_driver_env,
    )

    auth_result = authenticate(auth_ctx, modes=auth_modes)
    if not auth_result.ok or not auth_result.driver:
        if auth_result.need_user_input:
            print(auth_result.need_user_input.get("message", "Authentication failed."))
        if auth_result.reason:
            print(f"[AUTH] {auth_result.reason}")
        return False

    save_cookies_json(auth_result.driver, cookie_path)
    try:
        auth_result.driver.quit()
    except Exception:
        pass
    return os.path.exists(cookie_path)


def http_scrape_customers(
    handles: List[str],
    output_dir: str,
    cookie_file: Optional[str],
    target_url: str,
    profile_dir_override: Optional[str],
    profile_name: str,
    resolved_profiles: List[str],
    resolved_cookies: List[str],
    auth_mode_value: Optional[str],
    auth_profile_only: bool,
    headless: bool,
    attach: Optional[int],
    auto_attach: bool,
    attach_host: str,
    attach_timeout: float,
    fallback_profile_dir: str,
    edge_temp_profile: bool,
    edge_kill_before: bool,
    show_browser: bool,
    edge_binary_path_resolved: Optional[str],
    edge_driver_env: Optional[str],
    auth_username: Optional[str],
    auth_password: Optional[str],
    auth_check_url: Optional[str],
    auth_user_agent: Optional[str],
) -> None:
    from webscraper import http_scraper

    # HTTP scraping is preferred to avoid brittle GUI interactions; Selenium is used only for auth cookies.
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{run_id}_{os.getpid()}"
    run_dir = os.path.join(output_dir, run_id)
    http_output_dir = os.path.join(run_dir, "http")
    os.makedirs(http_output_dir, exist_ok=True)
    _write_run_metadata(run_dir, mode="http", run_id=run_id)

    cookie_path = cookie_file or os.path.join(run_dir, "selenium_cookies.json")
    if not _ensure_http_cookies(
        cookie_path=cookie_path,
        output_dir=run_dir,
        profile_dir_override=profile_dir_override,
        profile_name=profile_name,
        resolved_profiles=resolved_profiles,
        resolved_cookies=resolved_cookies,
        auth_mode_value=auth_mode_value,
        auth_profile_only=auth_profile_only,
        headless=headless,
        attach=attach,
        auto_attach=auto_attach,
        attach_host=attach_host,
        attach_timeout=attach_timeout,
        fallback_profile_dir=fallback_profile_dir,
        edge_temp_profile=edge_temp_profile,
        edge_kill_before=edge_kill_before,
        show_browser=show_browser,
        edge_binary_path_resolved=edge_binary_path_resolved,
        edge_driver_env=edge_driver_env,
        auth_username=auth_username,
        auth_password=auth_password,
        auth_check_url=auth_check_url,
        target_url=target_url,
    ):
        print("[ERROR] Unable to obtain authenticated cookies for HTTP mode.")
        return

    for handle in handles:
        print(f"[HTTP] Fetching {handle}")
        result = http_scraper.fetch_customer(
            handle=handle,
            cookies_path=cookie_path,
            user_agent=auth_user_agent,
            url=target_url,
        )
        if not result.auth_valid:
            print("[HTTP] Auth appears invalid; re-authenticating via Selenium.")
            if not _ensure_http_cookies(
                cookie_path=cookie_path,
                output_dir=run_dir,
                profile_dir_override=profile_dir_override,
                profile_name=profile_name,
                resolved_profiles=resolved_profiles,
                resolved_cookies=resolved_cookies,
                auth_mode_value=auth_mode_value,
                auth_profile_only=auth_profile_only,
                headless=headless,
                attach=attach,
                auto_attach=auto_attach,
                attach_host=attach_host,
                attach_timeout=attach_timeout,
                fallback_profile_dir=fallback_profile_dir,
                edge_temp_profile=edge_temp_profile,
                edge_kill_before=edge_kill_before,
                show_browser=show_browser,
                edge_binary_path_resolved=edge_binary_path_resolved,
                edge_driver_env=edge_driver_env,
                auth_username=auth_username,
                auth_password=auth_password,
                auth_check_url=auth_check_url,
                target_url=target_url,
            ):
                print("[ERROR] Re-authentication failed; skipping HTTP scrape.")
                return
            result = http_scraper.fetch_customer(
                handle=handle,
                cookies_path=cookie_path,
                user_agent=auth_user_agent,
                url=target_url,
            )

        html_path = os.path.join(http_output_dir, f"customer_{handle}.html")
        _write_text(html_path, result.html)

        try:
            parsed = http_scraper.parse_customer_html(result.html, handle=handle)
            json_path = os.path.join(http_output_dir, f"customer_{handle}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2)
        except Exception as exc:
            print(f"[WARN] HTTP parse failed for {handle}: {exc}")
            print(f"[WARN] Saved raw HTML snapshot to {html_path}")


def smoke_test_edge_driver() -> None:
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions

    edge_options = EdgeOptions()
    driver = webdriver.Edge(options=edge_options)
    try:
        driver.get("https://example.com")
        print("[INFO] EDGE OK")
    finally:
        driver.quit()


def _resolve_auth_mode_type() -> Optional[Any]:
    try:
        auth_module = importlib.import_module("webscraper.auth")
    except ModuleNotFoundError:
        return None
    return getattr(auth_module, "AuthMode", None)


def _resolve_auth_symbols() -> Optional[tuple[Any, Any, Any]]:
    try:
        auth_module = importlib.import_module("webscraper.auth")
    except ModuleNotFoundError:
        return None
    auth_context = getattr(auth_module, "AuthContext", None)
    auth_mode = getattr(auth_module, "AuthMode", None)
    authenticate = getattr(auth_module, "authenticate", None)
    if auth_context and auth_mode and authenticate:
        return auth_context, auth_mode, authenticate
    return None


def build_auth_strategy_plan(
    profile_dir_override: Optional[str],
    profile_name: str,
    resolved_profiles: List[str],
    resolved_cookies: List[str],
    cookie_file_path: Optional[str],
    auth_mode_value: Optional[str],
    profile_only_flag: bool,
) -> tuple[Optional[List["AuthMode"]], List[str], List[str], bool]:
    auth_mode_type = _resolve_auth_mode_type()

    auth_modes_local: Optional[List["AuthMode"]] = None
    if auth_mode_value and auth_mode_type:
        normalized = auth_mode_value.strip().upper()
        if normalized and normalized != "AUTO":
            try:
                auth_modes_local = [auth_mode_type[normalized]]
            except KeyError:
                print(f"[WARN] Unknown SCRAPER_AUTH_MODE '{auth_mode_value}'. Falling back to AUTO.")
    elif auth_mode_value and not auth_mode_type:
        print("[WARN] AuthMode unavailable; ignoring SCRAPER_AUTH_MODE override.")

    profile_only_enabled = bool(profile_only_flag or profile_dir_override)
    if profile_only_enabled:
        print("[AUTH] profile_only enabled; skipping other strategies")
        if profile_dir_override:
            profile_candidates = [profile_dir_override]
        else:
            if resolved_profiles:
                print("[AUTH] profile_only enabled without --profile-dir; using first configured profile dir only")
                profile_candidates = [resolved_profiles[0]]
            else:
                profile_candidates = []
        profile_name_display = profile_name or "Default"
        profile_dir_display = profile_candidates[0] if profile_candidates else "<missing>"
        print(f"[AUTH] using profile dir={profile_dir_display} name={profile_name_display}")
        if auth_mode_type:
            return [auth_mode_type.PROFILE], profile_candidates, [], True
        print("[WARN] AuthMode unavailable; profile_only requested but auth orchestration disabled.")
        return None, profile_candidates, [], True

    profile_candidates = []
    if profile_dir_override:
        profile_candidates.append(profile_dir_override)
    for candidate in resolved_profiles:
        if candidate and candidate not in profile_candidates:
            profile_candidates.append(candidate)
    cookie_candidates = [p for p in resolved_cookies if p]
    if cookie_file_path:
        cookie_candidates.insert(0, os.path.abspath(cookie_file_path))
    return auth_modes_local, profile_candidates, cookie_candidates, False


def self_test_auth_strategy_profile_only() -> None:
    profile_path = os.path.abspath(os.path.join("webscraper", "edge_profile_tmp"))
    auth_modes_local, profiles_local, cookies_local, profile_only_enabled = build_auth_strategy_plan(
        profile_dir_override=profile_path,
        profile_name="Default",
        resolved_profiles=["/tmp/other"],
        resolved_cookies=["/tmp/cookies.json"],
        cookie_file_path="/tmp/override.json",
        auth_mode_value=None,
        profile_only_flag=False,
    )
    auth_mode_type = _resolve_auth_mode_type()
    if not auth_mode_type:
        print("[WARN] AuthMode unavailable; skipping auth strategy self-test.")
        return

    assert profile_only_enabled is True, "profile_only should be enabled when profile_dir is provided"
    assert auth_modes_local == [auth_mode_type.PROFILE], "auth modes should be PROFILE only"
    assert profiles_local == [profile_path], "profile candidates should be exactly the provided profile dir"
    assert cookies_local == [], "cookie strategies should be skipped when profile_only is enabled"


def _ticket_page_looks_ready(html: str, current_url: str) -> bool:
    text = html or ""
    if re.search(r"Ticket Information", text, flags=re.IGNORECASE):
        return True
    if "/ticket/" in (current_url or "").lower():
        if re.search(r"Ticket ID", text, flags=re.IGNORECASE) and "<table" in text:
            return True
    if BeautifulSoup is None:
        return False
    soup = BeautifulSoup(text, "html.parser")
    for table in soup.find_all("table"):
        headers = " ".join(h.get_text(" ", strip=True) for h in table.find_all("th")).lower()
        if any(key in headers for key in ("ticket information", "circuit id", "born/updated", "status", "type")):
            return True
    return False


def _wait_for_ticket_page(driver: Any, timeout: float, retries: int = 2) -> bool:
    from selenium.webdriver.support.ui import WebDriverWait

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: _ticket_page_looks_ready(d.page_source or "", d.current_url or "")
            )
            return True
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                try:
                    driver.refresh()
                except Exception:
                    pass
                time.sleep(1.0)
    if last_error:
        print(f"[WARN] Ticket page did not stabilize: {last_error}")
    return False


def _coerce_ticket_entry(item: Any) -> Optional[dict[str, Optional[str]]]:
    if isinstance(item, str):
        return build_ticket_url_entry(item)
    if isinstance(item, dict):
        url = as_str(item.get("url"))
        if not url:
            return None
        kind = as_str(item.get("kind")) or classify_url(url)
        ticket_id = as_str(item.get("ticket_id")) or (parse_ticket_id(url) if kind == "ticket_detail" else None)
        return {"url": url, "kind": kind, "ticket_id": ticket_id}
    return None


def _load_tickets_json(path: str) -> dict[str, List[dict[str, Optional[str]]]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "handle" in data and "tickets" in data:
                handle = str(data.get("handle"))
                tickets = data.get("tickets")
                if handle and isinstance(tickets, list):
                    return {handle: [entry for entry in (_coerce_ticket_entry(item) for item in tickets) if entry]}
            loaded: dict[str, List[dict[str, Optional[str]]]] = {}
            for key, values in data.items():
                if not isinstance(values, list):
                    continue
                loaded[str(key)] = [entry for entry in (_coerce_ticket_entry(item) for item in values) if entry]
            return loaded
    except Exception as exc:
        print(f"[WARN] Could not read tickets json '{path}': {exc}")
    return {}


def _load_ticket_urls_for_handle(output_dir: str, handle: str) -> List[dict[str, Optional[str]]]:
    handle_path = os.path.join(output_dir, f"tickets_{handle}.json")
    if os.path.exists(handle_path):
        data = _load_tickets_json(handle_path)
        if handle in data:
            return data[handle]
    all_path = os.path.join(output_dir, "tickets_all.json")
    if os.path.exists(all_path):
        data = _load_tickets_json(all_path)
        if handle in data:
            return data[handle]
    return []


def _wait_for_ticket_ready(driver: Any, timeout: float) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))


def _is_login_redirect(driver: Any) -> bool:
    current_url = (driver.current_url or "").lower()
    if any(token in current_url for token in ("login", "signin", "sso", "auth")):
        return True
    try:
        title = (driver.title or "").lower()
        if any(token in title for token in ("login", "sign in", "authenticate")):
            return True
    except Exception:
        pass
    try:
        page_html = driver.page_source or ""
    except Exception:
        return False
    if re.search(r"type=['\"]password['\"]", page_html, flags=re.IGNORECASE):
        return True
    return False


def _is_keycloak_auth_redirect(driver: Any) -> bool:
    current_url = (getattr(driver, "current_url", "") or "").lower()
    if "keycloak-01.123.net" in current_url or "/protocol/openid-connect/auth" in current_url:
        return True
    try:
        title = (driver.title or "").lower()
        if "sign in" in title:
            return True
    except Exception:
        pass
    try:
        html = (driver.page_source or "").lower()
    except Exception:
        return False
    login_markers = (
        "kc-form-login",
        "id=\"username\"",
        "name=\"username\"",
        "id=\"password\"",
        "name=\"password\"",
        "/protocol/openid-connect/auth",
    )
    return any(marker in html for marker in login_markers)


def _is_authenticated_session(driver: Any) -> bool:
    current = str(getattr(driver, "current_url", "") or "")
    current_lower = current.lower()
    if not current_lower.startswith("https://noc-tickets.123.net/"):
        return False
    if _is_keycloak_auth_redirect(driver):
        return False
    try:
        title = str(getattr(driver, "title", "") or "")
    except Exception:
        title = ""
    if "noc tickets" in title.lower() or "noc-tickets" in title.lower():
        return True
    try:
        has_nav = bool(
            driver.execute_script(
                "return !!document.querySelector('nav, .navbar, [data-testid*=\"nav\" i], a[href*=\"/ticket/\"]');"
            )
        )
        has_login_form = bool(
            driver.execute_script(
                "return !!document.querySelector('form[action*=\"login\" i], input[type=\"password\"], #kc-form-login');"
            )
        )
        return has_nav or not has_login_form
    except Exception:
        return False


def _phase_line(phase_name: str, handle: str, url: str, started_at: float, status: str) -> None:
    dt = max(0.0, time.monotonic() - started_at)
    print(
        f"[{_iso_utc_now()}] PHASE {phase_name} handle={handle or '-'} url={url or '-'} dt={dt:.2f}s status={status}",
        flush=True,
    )


def _capture_auth_redirect_artifacts(driver: Any, out_dir: str, ticket_id: str) -> dict[str, str]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_ticket = re.sub(r"[^A-Za-z0-9_-]", "_", ticket_id or "unknown")
    base = os.path.join(out_dir, f"auth_redirect_{safe_ticket}_{ts}")
    html_path = f"{base}.html"
    png_path = f"{base}.png"
    log_path = f"{base}.log"
    os.makedirs(out_dir, exist_ok=True)
    try:
        _write_text(html_path, driver.page_source or "")
    except Exception as exc:
        print(f"[WARN] Could not save auth redirect HTML: {exc}", flush=True)
    try:
        driver.save_screenshot(png_path)
    except Exception as exc:
        print(f"[WARN] Could not save auth redirect screenshot: {exc}", flush=True)
    try:
        logs = driver.get_log("browser")
        with open(log_path, "w", encoding="utf-8") as fh:
            for entry in logs:
                fh.write(f"{entry.get('level')} {entry.get('message')}\n")
    except Exception as exc:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(f"console_log_unavailable: {exc}\n")
    return {"html": html_path, "png": png_path, "log": log_path}


def ensure_noc_tickets_session(
    driver: Any,
    preauth_url: str,
    preauth_timeout: int,
    pause: bool,
    out_dir: str,
    handle: str,
    auth_timeout: int = 300,
    cookie_store_path: Optional[str] = None,
    save_cookies_after_auth: bool = True,
    load_cookies_before_auth: bool = True,
) -> bool:
    phase_start = time.monotonic()
    _phase_line("AUTH_WARMUP_START", handle=handle, url=preauth_url, started_at=phase_start, status="begin")
    if cookie_store_path and load_cookies_before_auth:
        preloaded = load_cookie_store(driver, cookie_store_path)
        print(f"[AUTH] cookie preload added={preloaded}", flush=True)

    try:
        driver.get(preauth_url)
    except Exception as exc:
        _phase_line("AUTH_WARMUP_TIMEOUT", handle=handle, url=preauth_url, started_at=phase_start, status=f"navigate_error:{exc}")
        return False

    if _is_authenticated_session(driver) and not _is_keycloak_auth_redirect(driver):
        _phase_line("AUTH_WARMUP_OK", handle=handle, url=driver.current_url or preauth_url, started_at=phase_start, status="already_authenticated")
        if cookie_store_path and save_cookies_after_auth:
            saved_count = save_cookie_store(driver, cookie_store_path, skip_if_empty=True)
            print(f"[AUTH] cookie save complete count={saved_count} path={cookie_store_path}", flush=True)
        return True

    if _is_keycloak_auth_redirect(driver):
        _phase_line("AUTH_WARMUP_KEYCLOAK_DETECTED", handle=handle, url=driver.current_url or preauth_url, started_at=phase_start, status="redirect")
        _capture_auth_redirect_artifacts(driver=driver, out_dir=out_dir, ticket_id="warmup")

    if pause and _is_keycloak_auth_redirect(driver):
        _phase_line("AUTH_WARMUP_WAITING_FOR_USER", handle=handle, url=driver.current_url or preauth_url, started_at=phase_start, status="manual_login_required")
        print(
            "\n" + "=" * 88 + "\n"
            "[AUTH] KEYCLOAK LOGIN REQUIRED: complete noc-tickets login in the browser window now.\n"
            "[AUTH] Waiting for authenticated noc-tickets session...\n"
            + "=" * 88,
            flush=True,
        )

    deadline = time.monotonic() + max(auth_timeout if pause else preauth_timeout, 1)
    while time.monotonic() < deadline:
        try:
            current_url = driver.current_url or ""
            authenticated = _is_authenticated_session(driver)
            print(
                f"[AUTH] heartbeat elapsed={time.monotonic() - phase_start:.1f}s current_url={current_url} authenticated={authenticated}",
                flush=True,
            )
            if authenticated and not _is_keycloak_auth_redirect(driver):
                _phase_line("AUTH_WARMUP_OK", handle=handle, url=current_url, started_at=phase_start, status="authenticated")
                if cookie_store_path and save_cookies_after_auth:
                    saved_count = save_cookie_store(driver, cookie_store_path, skip_if_empty=True)
                    print(f"[AUTH] cookie save complete count={saved_count} path={cookie_store_path}", flush=True)
                return True
        except Exception:
            pass
        time.sleep(2.0)

    _phase_line("AUTH_WARMUP_TIMEOUT", handle=handle, url=getattr(driver, "current_url", preauth_url) or preauth_url, started_at=phase_start, status="timeout")
    return False


def scrape_ticket_details(
    driver: Any,
    handle: str,
    ticket_urls: List[dict[str, Optional[str]]],
    out_dir: str,
    max_tickets: Optional[int],
    save_html: bool,
    resume: bool,
    preauth_noc_tickets: bool,
    preauth_url: str,
    preauth_timeout: int,
    preauth_pause: bool,
    retry_on_auth_redirect: int,
    cookie_store_path: Optional[str] = None,
    load_cookies_before_auth: bool = True,
    save_cookies_after_auth: bool = True,
    auth_timeout: int = 300,
    noc_tickets_authed: Optional[dict[str, bool]] = None,
    phase_logger: Optional[PhaseLogger] = None,
) -> dict:
    bs4 = require_beautifulsoup()
    urls = [entry for entry in (_coerce_ticket_entry(u) for u in ticket_urls) if entry]
    if not urls:
        urls = _load_ticket_urls_for_handle(out_dir, handle)
    if not urls:
        print(f"[TICKET] No URLs found for {handle}")
        return {"handle": handle, "scraped": 0, "skipped": 0, "failed": 0, "total": 0}

    urls = sorted(urls, key=lambda item: (_url_kind_priority(as_str(item.get("kind"))), as_str(item.get("url"))))
    plog = phase_logger or PhaseLogger(enabled=True)

    ticket_root = os.path.join(out_dir, "tickets", handle)
    os.makedirs(ticket_root, exist_ok=True)

    scraped = 0
    skipped = 0
    failed = 0
    total = 0
    session_state = noc_tickets_authed if noc_tickets_authed is not None else {"ok": False}

    for entry in urls:
        if max_tickets is not None and total >= max_tickets:
            break
        total += 1
        url = as_str(entry.get("url"))
        kind = as_str(entry.get("kind")) or classify_url(url)
        ticket_id = as_str(entry.get("ticket_id")) or (parse_ticket_id(url) if kind == "ticket_detail" else None)
        plog.log(f"[{_iso_utc_now()}] PHASE SCRAPE_URL handle={handle} status=begin classification={kind} url={url}")
        if kind != "ticket_detail":
            print(f"[TICKET] skipped url={url} reason=non_ticket_detail kind={kind}", flush=True)
            skipped += 1
            continue
        if not ticket_id:
            print(f"[TICKET] failed url={url} reason=missing_ticket_id")
            failed += 1
            continue

        ticket_dir = os.path.join(ticket_root, ticket_id)
        os.makedirs(ticket_dir, exist_ok=True)
        ticket_json_path = os.path.join(ticket_dir, "ticket.json")
        if resume and os.path.exists(ticket_json_path):
            print(f"[TICKET] skipped {ticket_id} (resume)")
            skipped += 1
            continue
        try:
            auth_fail = False
            max_attempts = max(0, retry_on_auth_redirect) + 1
            for attempt in range(1, max_attempts + 1):
                driver.get(url)
                redirected = _is_keycloak_auth_redirect(driver)
                if redirected:
                    plog.log(
                        f"[{_iso_utc_now()}] PHASE AUTH_REDIRECT handle={handle} ticket_id={ticket_id} "
                        f"attempt={attempt}/{max_attempts} redirect_url={driver.current_url or '-'}"
                    )
                if not redirected:
                    try:
                        _wait_for_ticket_ready(driver, timeout=25)
                    except Exception:
                        redirected = _is_keycloak_auth_redirect(driver)
                        if not redirected:
                            raise
                if not redirected:
                    auth_fail = False
                    break

                auth_fail = True
                _capture_auth_redirect_artifacts(driver=driver, out_dir=out_dir, ticket_id=ticket_id)
                if preauth_noc_tickets:
                    if not session_state.get("ok") or _is_keycloak_auth_redirect(driver):
                        session_state["ok"] = ensure_noc_tickets_session(
                            driver=driver,
                            preauth_url=preauth_url,
                            preauth_timeout=preauth_timeout,
                            pause=preauth_pause,
                            out_dir=out_dir,
                            handle=handle,
                            auth_timeout=auth_timeout,
                            cookie_store_path=cookie_store_path,
                            save_cookies_after_auth=save_cookies_after_auth,
                            load_cookies_before_auth=load_cookies_before_auth,
                        )
                phase_started = time.monotonic()
                _phase_line(
                    "TICKET_RETRY",
                    handle=handle,
                    url=url,
                    started_at=phase_started,
                    status=f"attempt={attempt}/{max_attempts}",
                )
                if attempt >= max_attempts:
                    break

            if auth_fail:
                failed += 1
                print(f"[TICKET] failed {ticket_id}: auth_redirect_persisted", flush=True)
                continue

            if _is_login_redirect(driver):
                raise RuntimeError(f"login redirect detected at {driver.current_url}")
            if "/ticket/" not in (driver.current_url or "").lower():
                print(f"[WARN] Ticket URL unexpected: {driver.current_url}")

            page_html = driver.page_source or ""
            soup = bs4(page_html, "html.parser")
            page_text = soup.get_text(" ", strip=True)
            page_title = soup.title.string.strip() if soup.title and soup.title.string else None
            ticket_fields = extract_ticket_fields(page_html)
            subject = ticket_fields.get("subject") or page_title

            html_path = None
            if save_html:
                html_path = os.path.join(ticket_dir, "page.html")
                _write_text(html_path, page_html)
            screenshot_path = os.path.join(ticket_dir, "page.png")
            try:
                driver.get_screenshot_as_file(screenshot_path)
            except Exception as exc:
                print(f"[WARN] Screenshot failed for {ticket_id}: {exc}")

            extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            payload = {
                "ticket_id": ticket_id,
                "handle": handle,
                "url": url,
                "extracted_at": extracted_at,
                "page_title": page_title,
                "subject": subject,
                "text": page_text,
                "html_path": html_path,
                "screenshot_path": screenshot_path,
                "source": "noc-tickets.123.net",
            }
            with open(ticket_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            bytes_saved = len(page_html.encode("utf-8"))
            plog.log(f"[{_iso_utc_now()}] PHASE SCRAPE_URL handle={handle} status=ok ticket_id={ticket_id} bytes_saved={bytes_saved} output={ticket_json_path}")
            print(f"[TICKET] scraped {ticket_id}")
            scraped += 1
        except Exception as exc:
            failed += 1
            print(f"[TICKET] failed {ticket_id or url}: {exc}")

    summary = {"handle": handle, "scraped": scraped, "skipped": skipped, "failed": failed, "total": total}
    print(f"[TICKET] Summary {handle}: scraped={scraped} skipped={skipped} failed={failed}")
    return summary


def selenium_scrape_tickets(
    url: str,
    output_dir: str,
    handles: List[str],
    headless: bool = True,
    headless_requested: bool = False,
    vacuum: bool = False,
    aggressive: bool = False,
    cookie_file: Optional[str] = None,
    attach: Optional[int] = None,
    auto_attach: bool = False,
    attach_host: str = "127.0.0.1",
    attach_timeout: float = 2.0,
    fallback_profile_dir: str = "webscraper/edge_profile_tmp",
    target_url: Optional[str] = None,
    auth_dump: bool = False,
    auth_pause: bool = False,
    auth_timeout: int = 180,
    auth_url: Optional[str] = None,
    profile_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
    no_quit: bool = False,
    edge_only: bool = False,
    edge_profile_dir_override: Optional[str] = None,
    edge_temp_profile: bool = False,
    edge_kill_before: bool = False,
    show_browser: bool = False,
    auth_orchestration: bool = True,
    auth_profile_dirs: Optional[List[str]] = None,
    auth_cookie_files: Optional[List[str]] = None,
    auth_username: Optional[str] = None,
    auth_password: Optional[str] = None,
    auth_check_url: Optional[str] = None,
    auth_user_agent: Optional[str] = None,
    auth_mode: Optional[str] = None,
    auth_profile_only: bool = False,
    scrape_ticket_details_enabled: bool = False,
    tickets_json: Optional[str] = None,
    kb_dir: str = "webscraper/knowledge_base",
    build_kb: bool = False,
    kb_jsonl: Optional[str] = None,
    kb_sqlite: Optional[str] = None,
    max_tickets: Optional[int] = None,
    rate_limit: float = 0.5,
    resume: bool = False,
    save_html: bool = False,
    save_screenshot: bool = False,
    phase_logs: bool = False,
    debug_dir: Optional[str] = None,
    dump_dom_on_fail: bool = True,
    edge_smoke_test: bool = False,
    preauth_noc_tickets: bool = False,
    preauth_url: str = "https://noc-tickets.123.net/",
    preauth_timeout: int = 180,
    preauth_pause: bool = True,
    retry_on_auth_redirect: int = 2,
    cookie_store_path: Optional[str] = None,
    load_cookies: bool = True,
    save_cookies: bool = True,
    save_cookies_after_auth: bool = True,
    include_new_ticket_links: bool = False,
) -> None:
    """Minimal Selenium workflow that:
    - launches Edge (headless optional)
    - opens the target URL
    - for each handle: saves current HTML and a debug log

    Notes:
    - Imports are inside the function so the module can be imported even if
      Selenium is not installed in the environment.
    - This function intentionally does not interact with dropdowns or perform
      complex waits yet. We'll add those back incrementally.
    """
    # Local imports to avoid top-level dependency failures
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import (
        ElementClickInterceptedException,
        InvalidSessionIdException,
        NoSuchElementException,
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )

    os.makedirs(output_dir, exist_ok=True)
    debug_dir = os.path.abspath(debug_dir or output_dir)
    os.makedirs(debug_dir, exist_ok=True)
    _write_run_metadata(output_dir, mode="selenium")
    # Prune legacy noisy files to keep output readable
    try:
        legacy_patterns = [
            os.path.join(output_dir, "debug_no_*.html"),
            os.path.join(output_dir, "debug_no_*.txt"),
        ]
        removed = 0
        for pat in legacy_patterns:
            for p in glob.glob(pat):
                try:
                    os.remove(p)
                    removed += 1
                except Exception:
                    pass
        if removed:
            print(f"[CLEANUP] Removed {removed} legacy debug_no_* files from {output_dir}")
    except Exception:
        pass

    # Use E:\-aware paths if provided via config/env
    edge_driver_env = os.environ.get("EDGEDRIVER_PATH")
    edge_binary_path_resolved = edge_binary_path()
    profile_dir_override = os.path.abspath(profile_dir) if profile_dir else None

    effective_target_url = target_url or url
    effective_auth_url = auth_url or effective_target_url
    resolved_profile_name = profile_name or "Default"
    auth_mode = "AUTO" if (auth_dump or auth_pause) else None
    attach_requested = bool(attach or auto_attach)
    enable_auth_orchestration = auth_orchestration and not auth_mode and not attach_requested
    allow_manual_prompts = not enable_auth_orchestration
    if auth_mode or show_browser:
        headless = False
    if edge_temp_profile and not auth_mode:
        print("[INFO] --edge-temp-profile is only applied in auth mode; ignoring for this run.")

    driver = cast("webdriver.Edge", None)
    created_browser = False
    attach_mode = False
    cookies_path: Optional[str] = None
    resolved_auth_profiles = [os.path.abspath(p) for p in (auth_profile_dirs or []) if p]
    resolved_auth_cookies = [os.path.abspath(p) for p in (auth_cookie_files or []) if p]

    def run_auth_diagnostics() -> None:
        nonlocal driver, created_browser, attach_mode
        from webscraper import auth_diagnostics
        import threading
        import time

        os.makedirs(output_dir, exist_ok=True)
        print("[AUTH] Diagnostics mode enabled.")
        print(
            "[AUTH] Example commands:\n"
            "  .\\.venv-webscraper\\Scripts\\python.exe -m webscraper.ultimate_scraper --auth-dump --auth-pause "
            "--edge-only --out webscraper/output/auth_test\n"
            "  python -m webscraper.ultimate_scraper --auth-dump --no-quit --auth-url "
            "\"https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi\" --out webscraper/output/auth_test"
        )

        driver, created_browser, attach_mode, resolved_edge_profile_dir = create_edge_driver(
            output_dir=output_dir,
            headless=headless,
            headless_requested=headless_requested,
            attach=attach,
            auto_attach=auto_attach,
            attach_host=attach_host,
            attach_timeout=attach_timeout,
            fallback_profile_dir=fallback_profile_dir,
            profile_dir=profile_dir,
            profile_name=resolved_profile_name,
            auth_dump=auth_dump,
            auth_pause=auth_pause,
            auth_timeout=auth_timeout,
            auth_url=effective_target_url,
            edge_temp_profile=edge_temp_profile,
            edge_kill_before=edge_kill_before,
            show_browser=show_browser,
        )
        try:
            driver.set_page_load_timeout(30)
        except Exception:
            pass

        navigation_error = None
        for attempt in range(2):
            try:
                driver.get(effective_auth_url)
                navigation_error = None
                break
            except Exception as exc:
                navigation_error = str(exc)
                if attempt == 0:
                    time.sleep(1.0)

        if auth_pause:
            print("Login in browser, then press ENTER in this terminal to continue")
            done_state = {"done": False}

            def _wait_for_enter() -> None:
                try:
                    input()
                except Exception:
                    pass
                done_state["done"] = True

            waiter = threading.Thread(target=_wait_for_enter, daemon=True)
            waiter.start()
            waiter.join(max(auth_timeout, 0))
            if not done_state["done"]:
                print(f"[WARN] Auth pause timed out after {auth_timeout} seconds; continuing.")

        report = auth_diagnostics.collect_auth_signals(driver)
        report.update(
            {
                "auth_url": effective_auth_url,
                "navigation_error": navigation_error,
                "attach_mode": attach_mode,
                "edge_only": edge_only,
                "profile_dir": resolved_edge_profile_dir,
                "profile_name": resolved_profile_name,
                "auth_pause": auth_pause,
            }
        )

        page_html_path = os.path.join(output_dir, "auth_page.html")
        page_html_error = None
        for attempt in range(2):
            try:
                page_html = driver.page_source or ""
                with open(page_html_path, "w", encoding="utf-8") as f:
                    f.write(page_html)
                page_html_error = None
                break
            except Exception as exc:
                page_html_error = str(exc)
                if attempt == 0:
                    time.sleep(0.5)
        if page_html_error:
            report.setdefault("errors", {})["page_html_error"] = page_html_error

        screenshot_path = os.path.join(output_dir, "auth_screenshot.png")
        screenshot_error = None
        for attempt in range(2):
            try:
                driver.get_screenshot_as_file(screenshot_path)
                screenshot_error = None
                break
            except Exception as exc:
                screenshot_error = str(exc)
                if attempt == 0:
                    time.sleep(0.5)
        if screenshot_error:
            report.setdefault("errors", {})["screenshot_error"] = screenshot_error

        auth_diagnostics.write_auth_report(output_dir, report)

        if no_quit:
            print("[WARN] --no-quit set; leaving browser open for manual inspection.")
        else:
            try:
                driver.quit()
            except Exception:
                pass

        return

    def dump_browser_console(prefix: str) -> None:
        try:
            logs = driver.get_log('browser')
            path = os.path.join(output_dir, f"{prefix}_console.log")
            with open(path, "w", encoding="utf-8") as f:
                for entry in logs:
                    lvl = entry.get('level')
                    msg = entry.get('message')
                    f.write(f"{lvl} {msg}\n")
            print(f"[INFO] Saved browser console log to {path}")
        except Exception:
            pass

    def _post_auth_setup() -> None:
        nonlocal driver, created_browser, attach_mode, cookies_path

        if not driver:
            raise RuntimeError("Driver not initialized.")

        # Avoid indefinite page-load waits
        try:
            driver.set_page_load_timeout(30)
        except Exception:
            pass

        # Attempt to load and inject cookies after navigation to target
        if cookie_file:
            try:
                injected = load_cookie_store(driver, cookie_file)
                if injected > 0:
                    try:
                        driver.get(effective_target_url)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[WARN] Cookie injection failed: {e}")
        try:
            # Try to navigate; if DNS fails, prompt for manual navigation
            try:
                driver.get(effective_target_url)
            except Exception as e:
                print(f"[WARN] Could not navigate to '{effective_target_url}': {e}")
                if allow_manual_prompts:
                    # Offer alternative: prompt for a reachable URL (e.g., IP-based)
                    print(
                        "[PROMPT] Enter a reachable URL (e.g., http://<IP>/customers.cgi), "
                        "or press Enter to skip manual navigation:"
                    )
                    try:
                        alt = input().strip()
                    except Exception:
                        alt = ""
                    if alt:
                        try:
                            driver.get(alt)
                            print(f"[INFO] Navigated to alternative URL: {alt}")
                        except Exception as e2:
                            print(f"[WARN] Alternative URL navigation failed: {e2}")
                    if not alt:
                        print(
                            "[ACTION REQUIRED] In Edge, open the customers page (use IP if hostname fails), "
                            "complete VPN/SSO/MFA, then return here."
                        )
                        print(
                            "[PROMPT] Press Enter ONLY after you see real page content (menus/search). "
                            "I'll verify the DOM before proceeding."
                        )
                        try:
                            input()
                        except Exception:
                            pass
                else:
                    print("[WARN] Manual navigation prompts disabled; auth orchestration is enabled.")
                # Verify DOM has content (tables/links/inputs) before proceeding
                try:
                    from selenium.webdriver.support.ui import WebDriverWait

                    def dom_has_content(d):
                        try:
                            tables = d.find_elements(By.TAG_NAME, "table")
                            links = d.find_elements(By.TAG_NAME, "a")
                            inputs = d.find_elements(By.TAG_NAME, "input")
                            return (len(tables) + len(links) + len(inputs)) > 5
                        except Exception:
                            return False

                    WebDriverWait(driver, 25).until(dom_has_content)
                    print("[INFO] Detected page content; continuing scrape.")
                except Exception:
                    print("[WARN] Page still looks empty; proceeding but results may be blank.")
            # Persist current cookies only when not on a login redirect.
            current_url_lower = str(getattr(driver, "current_url", "") or "").lower()
            if any(marker in current_url_lower for marker in ("keycloak", "/protocol/openid-connect/", "/login-actions/")):
                print("[COOKIES] startup save skipped (auth not complete)", flush=True)
            else:
                cookies_path = os.path.join(output_dir, "selenium_cookies.json")
                save_cookie_store(driver, cookies_path, skip_if_empty=True)
                if cookie_file:
                    save_cookie_store(driver, cookie_file, skip_if_empty=True)

            # Quick readiness check: ensure we can see a search input or Search button
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(driver, 20).until(
                    lambda d: (
                        len(d.find_elements(By.CSS_SELECTOR, "input[type='text'], input#customers, input[name='customer'], input[name='customer_handle']")) > 0 or
                        len(d.find_elements(By.XPATH, "//button[contains(.,'Search')] | //input[@type='submit' and contains(@value,'Search')]")) > 0
                    )
                )
                print("[INFO] Landing page looks ready (search input/button present)")
            except Exception:
                print("[WARN] Could not confirm search input yet; proceeding to scrape artifacts")

            # --- FIRST PAGE SCRAPE: save and parse before any interaction ---
            try:
                # Save HTML and screenshot
                first_html = driver.page_source
                first_html_path = os.path.join(output_dir, "first_page.html")
                with open(first_html_path, "w", encoding="utf-8") as f:
                    f.write(first_html)
                screenshot_path = os.path.join(output_dir, "first_page.png")
                try:
                    driver.get_screenshot_as_file(screenshot_path)
                    print(f"[INFO] Saved initial page HTML and screenshot to {first_html_path}, {screenshot_path}")
                except Exception:
                    print(f"[INFO] Saved initial page HTML to {first_html_path}")
                dump_browser_console("first_page")

                # Parse DOM summary: tables, links, inputs, selects, buttons
                bs4 = require_beautifulsoup()
                soup = bs4(first_html, "html.parser")
                # Tables
                tables = []
                for t in soup.find_all("table"):
                    rows = []
                    headers = [th.get_text(strip=True) for th in t.find_all("th")]
                    for tr in t.find_all("tr"):
                        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                        if cells:
                            rows.append(cells)
                    tables.append({"headers": headers, "rows": rows})
                # Links
                links = []
                for a in soup.find_all("a", href=True):
                    links.append({"text": a.get_text(strip=True), "href": a.get("href")})
                # Inputs
                inputs = []
                for inp in soup.find_all("input"):
                    inputs.append({
                        "id": inp.get("id"),
                        "name": inp.get("name"),
                        "type": inp.get("type"),
                        "class": inp.get("class"),
                        "placeholder": inp.get("placeholder"),
                        "value": inp.get("value"),
                    })
                # Selects
                selects = []
                for sel in soup.find_all("select"):
                    options = [opt.get_text(strip=True) for opt in sel.find_all("option")]
                    selected = None
                    for opt in sel.find_all("option"):
                        if opt.has_attr("selected"):
                            selected = opt.get_text(strip=True)
                            break
                    selects.append({
                        "id": sel.get("id"),
                        "name": sel.get("name"),
                        "class": sel.get("class"),
                        "options": options,
                        "selected": selected,
                    })
                # Buttons
                buttons = []
                for btn in soup.find_all(["button"]):
                    buttons.append({
                        "id": btn.get("id"),
                        "name": btn.get("name"),
                        "type": btn.get("type"),
                        "class": btn.get("class"),
                        "text": btn.get_text(strip=True),
                    })
                # Try to expand and capture Toggle Help content
                help_text = None
                try:
                    th = driver.find_element(By.XPATH, "//button[contains(.,'Toggle Help')] | //a[contains(.,'Toggle Help')]")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", th)
                    driver.execute_script("arguments[0].click();", th)
                    import time
                    time.sleep(0.4)
                    # Refresh soup and extract help container text (heuristic)
                    first_html = driver.page_source
                    bs4 = require_beautifulsoup()
                    soup = bs4(first_html, "html.parser")
                    cand = soup.find_all(text=lambda s: isinstance(s, str) and ("Wildcard Searches" in s or "Fields" in s or "A query is broken up" in s))
                    if cand:
                        helps = []
                        for c in cand:
                            try:
                                blk = c.parent
                                if blk:
                                    helps.append(blk.get_text("\n", strip=True))
                            except Exception:
                                pass
                        help_text = "\n\n".join(helps) if helps else None
                except Exception:
                    pass

                # Build summary
                first_summary = {
                    "url": driver.current_url,
                    "title": soup.title.string if soup.title else None,
                    "tables": tables,
                    "links": links,
                    "inputs": inputs,
                    "selects": selects,
                    "buttons": buttons,
                    "help_text": help_text,
                    "raw_html_path": first_html_path,
                    "screenshot_path": screenshot_path,
                }
                import json
                first_json_path = os.path.join(output_dir, "first_page_summary.json")
                with open(first_json_path, "w", encoding="utf-8") as f:
                    json.dump(first_summary, f, indent=2)
                print(f"[INFO] Saved initial page summary to {first_json_path}")
            except Exception as e:
                print(f"[WARN] Initial page scrape failed: {e}")
        except Exception as e:
            print(f"[WARN] Edge setup encountered an error: {e}")

    def initialize_driver() -> None:
        nonlocal driver, created_browser, attach_mode, cookies_path
        driver, created_browser, attach_mode, _ = create_edge_driver(
            output_dir=output_dir,
            headless=headless,
            headless_requested=headless_requested,
            attach=attach,
            auto_attach=auto_attach,
            attach_host=attach_host,
            attach_timeout=attach_timeout,
            fallback_profile_dir=fallback_profile_dir,
            profile_dir=profile_dir,
            profile_name=resolved_profile_name,
            auth_dump=auth_dump,
            auth_pause=auth_pause,
            auth_timeout=auth_timeout,
            auth_url=effective_target_url,
            edge_temp_profile=edge_temp_profile,
            edge_kill_before=edge_kill_before,
            show_browser=show_browser,
        )
        _post_auth_setup()

    try:
        if auth_dump:
            run_auth_diagnostics()
            return
        if enable_auth_orchestration:
            auth_symbols = _resolve_auth_symbols()
            if not auth_symbols:
                print("[WARN] Auth module unavailable; skipping auth orchestration.")
            else:
                AuthContext, AuthMode, authenticate = auth_symbols

                (
                    auth_modes,
                    auth_profile_candidates,
                    auth_cookie_candidates,
                    _profile_only_enabled,
                ) = build_auth_strategy_plan(
                    profile_dir_override=profile_dir_override,
                    profile_name=resolved_profile_name,
                    resolved_profiles=resolved_auth_profiles,
                    resolved_cookies=resolved_auth_cookies,
                    cookie_file_path=cookie_file,
                    auth_mode_value=auth_mode,
                    profile_only_flag=auth_profile_only,
                )
                auth_ctx = AuthContext(
                    base_url=effective_target_url,
                    auth_check_url=auth_check_url or effective_auth_url,
                    preferred_browser="edge",
                    profile_dirs=auth_profile_candidates,
                    profile_name=resolved_profile_name,
                    cookie_files=auth_cookie_candidates,
                    username=auth_username,
                    password=auth_password,
                    headless=headless,
                    timeout_sec=30,
                    output_dir=output_dir,
                    attach=attach,
                    auto_attach=auto_attach,
                    attach_host=attach_host,
                    attach_timeout=attach_timeout,
                    fallback_profile_dir=fallback_profile_dir,
                    edge_temp_profile=edge_temp_profile,
                    edge_kill_before=edge_kill_before,
                    show_browser=show_browser,
                    edge_binary=edge_binary_path_resolved,
                    edgedriver_path=edge_driver_env,
                )
                auth_result = authenticate(auth_ctx, modes=auth_modes)
                if not auth_result.ok or not auth_result.driver:
                    if auth_result.need_user_input:
                        print(auth_result.need_user_input.get("message", "Authentication failed."))
                    if auth_result.reason:
                        print(f"[AUTH] {auth_result.reason}")
                    return
                driver = cast("webdriver.Edge", auth_result.driver)
                created_browser = True
                attach_mode = False
                _post_auth_setup()
        else:
            initialize_driver()

        def restart_driver(reason: str) -> None:
            nonlocal driver, created_browser
            if attach_mode:
                print(f"[WARN] Attach mode active; not restarting driver for {reason}.")
                return
            print(f"[WARN] Restarting Edge driver due to {reason}.")
            if created_browser:
                try:
                    driver.quit()
                except Exception:
                    pass
            initialize_driver()

        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        phase_logger = _build_phase_logger(phase_logs)
        realtime_phase_logger = PhaseLogger(enabled=phase_logs)

        def _phase(step_num: int, name: str, details: str = "", started_at: Optional[float] = None) -> None:
            elapsed = f" dt={time.monotonic() - started_at:.2f}s" if started_at is not None else ""
            suffix = f" {details}" if details else ""
            phase_logger.info(f"[{_iso_utc_now()}] [PHASE {step_num:02d} {name}]{suffix}{elapsed}")

        def save_debug_artifacts(handle: str, label: str) -> None:
            safe_label = label.replace(" ", "_").lower()
            html_path = os.path.join(debug_dir, f"{handle}_{safe_label}.html")
            png_path = os.path.join(debug_dir, f"{handle}_{safe_label}.png")
            try:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except Exception as exc:
                print(f"[WARN] Could not save HTML ({label}) for {handle}: {exc}", flush=True)
            try:
                driver.save_screenshot(png_path)
            except Exception as exc:
                print(f"[WARN] Could not save screenshot ({label}) for {handle}: {exc}", flush=True)

        def _probe_company_dom(clicked_selector: str = "") -> dict[str, Any]:
            anchors = driver.find_elements(By.TAG_NAME, "a")
            link_hrefs = [(a.get_attribute("href") or "").strip() for a in anchors[:10]]
            page_text = driver.page_source or ""
            table_candidates = driver.find_elements(By.XPATH, "//table[.//a[contains(@href,'ticket') or contains(@onclick,'ticket')]]")
            first_rows = 0
            if table_candidates:
                first_rows = len(table_candidates[0].find_elements(By.XPATH, ".//tr[td]"))
            panel_visible = False
            for sel in ("#slideid7", "div[id*='slide']", "div.slide"):
                for panel in driver.find_elements(By.CSS_SELECTOR, sel):
                    if panel.is_displayed():
                        panel_visible = True
                        break
                if panel_visible:
                    break
            return {
                "found_showhide_text": "Trouble Ticket Data" in page_text,
                "clicked_selector": clicked_selector,
                "panel_visible": panel_visible,
                "table_found": bool(table_candidates),
                "table_row_count": first_rows,
                "first_10_link_hrefs": link_hrefs,
                "page_title": driver.title,
                "current_url": driver.current_url,
                "anchor_count": len(anchors),
            }

        def _log_fail(phase: str, handle: str, exc: Exception, debug_ctx: dict[str, Any]) -> None:
            probe = _probe_company_dom(clicked_selector=as_str(debug_ctx.get("clicked_selector")))
            print(
                f"[FAIL] phase={phase} exception={exc} current_url={driver.current_url} "
                f"anchors={probe.get('anchor_count')} has_trouble_text={probe.get('found_showhide_text')} "
                f"table_found={probe.get('table_found')}",
                flush=True,
            )

        def search_company(driver: Any, handle: str) -> None:
            search_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#customers")))
            query = f"{handle}:company_data:handle:{handle}"
            search_box.clear()
            search_box.send_keys(query)
            try:
                search_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value='Search ->']")))
            except TimeoutException:
                search_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and contains(@value,'Search')]")))
            try:
                search_btn.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", search_btn)

        def wait_company_handle(driver: Any, handle: str, timeout: int = 20) -> bool:
            def _matches(drv: Any) -> bool:
                th_elements = drv.find_elements(By.XPATH, "//th[contains(normalize-space(), 'Company Handle')]")
                for th in th_elements:
                    try:
                        td = th.find_element(By.XPATH, "following-sibling::td[1]")
                    except Exception:
                        continue
                    if (td.text or "").strip() == handle:
                        return True
                return False
            try:
                WebDriverWait(driver, timeout).until(lambda d: _matches(d))
                return True
            except TimeoutException:
                return False

        def _normalize_ticket_url(href: str, onclick: str) -> Optional[str]:
            href_value = (href or "").strip()
            onclick_value = (onclick or "").strip()
            origin = urllib.parse.urlsplit(driver.current_url)
            base_origin = f"{origin.scheme}://{origin.netloc}" if origin.scheme and origin.netloc else "https://noc-tickets.123.net"
            if href_value:
                if href_value.startswith("http"):
                    return href_value
                return urllib.parse.urljoin(base_origin, href_value)
            if onclick_value and "/ticket/" in onclick_value:
                full_match = re.search(r'https?://[^"\'\s]+/ticket/\d+', onclick_value)
                if full_match:
                    return full_match.group(0)
                id_match = re.search(r"/ticket/(\d+)", onclick_value)
                if id_match:
                    return urllib.parse.urljoin(base_origin, f"/ticket/{id_match.group(1)}")
            return None

        def _extract_ticket_id_from_href(href: str) -> Optional[str]:
            parsed = urllib.parse.urlparse(href or "")
            query_pairs = urllib.parse.parse_qs(parsed.query or "")
            for key in ("ticket_id", "id", "ticket"):
                values = query_pairs.get(key) or []
                for value in values:
                    numeric = re.search(r"\b(\d{12,})\b", value or "")
                    if numeric:
                        return numeric.group(1)
            path_parts = [p for p in (parsed.path or "").split("/") if p]
            for part in reversed(path_parts):
                numeric = re.search(r"\b(\d{12,})\b", part)
                if numeric:
                    return numeric.group(1)
            return None

        def _locate_trouble_ticket_table(driver: Any) -> Optional[Any]:
            tables = driver.find_elements(By.XPATH, "//table")
            for table in tables:
                headers = [h.text.strip().lower() for h in table.find_elements(By.XPATH, ".//tr[1]//*[self::th or self::td]")]
                has_ticket_id = any("ticket id" in header for header in headers)
                has_subject = any("subject" in header for header in headers)
                if has_ticket_id and has_subject:
                    return table
            return None

        def _classify_ticket_link(href: str, link_text: str) -> tuple[bool, Optional[str], str]:
            href_value = (href or "").strip()
            text_value = (link_text or "").strip()
            lowered_href = href_value.lower()
            for excluded in ("/new_ticket", "dsx_circuits.cgi", "customers.cgi", "smb://", "file://"):
                if excluded in lowered_href:
                    return False, None, f"excluded_pattern:{excluded}"

            text_match = re.fullmatch(r"\d{12,}", text_value)
            if text_match:
                return True, text_match.group(0), "text_ticket_id"

            href_ticket_id = _extract_ticket_id_from_href(href_value)
            if href_ticket_id:
                parsed = urllib.parse.urlparse(href_value)
                query_pairs = urllib.parse.parse_qs(parsed.query or "")
                has_explicit_param = False
                for key in ("ticket_id", "id", "ticket"):
                    values = query_pairs.get(key) or []
                    if any(re.search(r"\b\d+\b", value or "") for value in values):
                        has_explicit_param = True
                        break
                if has_explicit_param:
                    return True, href_ticket_id, "href_ticket_param"
                if "/ticket/" in (parsed.path or ""):
                    return True, href_ticket_id, "href_ticket_path"

            return False, None, "missing_ticket_id_pattern"

        def expand_trouble_tickets_section(driver: Any, wait: Any, debug_ctx: dict[str, Any]) -> None:
            selectors = [
                (By.XPATH, "//a[contains(normalize-space(),'Show/Hide Trouble Ticket Data')]"),
                (By.XPATH, "//a[contains(normalize-space(),'Trouble Ticket Data') and contains(@class,'show_hide')]"),
                (By.XPATH, "//a[contains(normalize-space(),'Trouble Ticket Data')]"),
                (By.CSS_SELECTOR, "a.show_hide[rel*='slide'],a.show_hide[rel*='#slideid']"),
                (By.CSS_SELECTOR, "a[rel*='slide'],a[href*='#slideid']"),
            ]
            last_exc = None
            for by, selector in selectors:
                try:
                    elems = driver.find_elements(by, selector)
                    debug_ctx.setdefault("selectors_tried", []).append(f"{by}:{selector} -> {len(elems)}")
                    if not elems:
                        continue
                    toggle = elems[0]
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", toggle)
                    clicked_selector = (toggle.get_attribute("rel") or toggle.get_attribute("href") or selector).strip()
                    debug_ctx["clicked_selector"] = clicked_selector
                    try:
                        toggle.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", toggle)
                    wait.until(lambda d: any(p.is_displayed() for p in d.find_elements(By.CSS_SELECTOR, clicked_selector if clicked_selector.startswith('#') else "div[id*='slide']")))
                    return
                except Exception as exc:
                    last_exc = exc
            raise RuntimeError(f"Unable to expand Trouble Ticket section: {last_exc}")

        def verify_trouble_ticket_rows(driver: Any, timeout: float) -> int:
            end_at = time.monotonic() + timeout
            last_rows = 0
            while time.monotonic() < end_at:
                table = _locate_trouble_ticket_table(driver)
                if table is not None:
                    rows = len(table.find_elements(By.XPATH, ".//tr[td]"))
                    last_rows = max(last_rows, rows)
                    if rows >= 1:
                        print(f"[{_iso_utc_now()}] PHASE EXPAND_TICKETS_VERIFY rows={rows}", flush=True)
                        return rows
                time.sleep(0.5)
            print(f"[{_iso_utc_now()}] PHASE EXPAND_TICKETS_VERIFY rows={last_rows}", flush=True)
            raise TimeoutException(f"Trouble ticket table rows not found within {timeout}s")

        def extract_ticket_urls_from_company_page(driver: Any, debug_ctx: dict[str, Any], log_links: bool = True) -> List[dict[str, Optional[str]]]:
            clicked_selector = as_str(debug_ctx.get("clicked_selector"))
            panel_anchors: List[Any] = []
            if clicked_selector.startswith("#"):
                panel_elems = driver.find_elements(By.CSS_SELECTOR, clicked_selector)
                if panel_elems:
                    panel_anchors = panel_elems[0].find_elements(By.XPATH, ".//a")
            if not panel_anchors:
                panel_anchors = driver.find_elements(By.XPATH, "//a")
            total_anchors_in_panel = len(panel_anchors)

            table = _locate_trouble_ticket_table(driver)
            if table is None:
                debug_ctx["table_row_count"] = 0
                debug_ctx["link_count"] = 0
                debug_ctx["total_anchors_in_panel"] = total_anchors_in_panel
                debug_ctx["anchors_in_table"] = 0
                debug_ctx["accepted_ticket_links"] = 0
                debug_ctx["rejected_links"] = 0
                if log_links:
                    print(
                        f"[TICKET LINKS] total_anchors_in_panel={total_anchors_in_panel} anchors_in_table=0 "
                        "accepted_ticket_links=0 rejected_links=0",
                        flush=True,
                    )
                return []

            links: List[dict[str, Optional[str]]] = []
            seen: set[str] = set()
            row_count = len(table.find_elements(By.XPATH, ".//tr[td]"))
            samples: List[dict[str, str]] = []
            anchors_in_table = table.find_elements(By.XPATH, ".//a")
            rejected_links = 0
            rejected_with_reason: List[tuple[str, str]] = []
            anchors_total = len(anchors_in_table)
            kept_ticket_detail = 0
            kept_new_ticket = 0
            kept_other = 0

            for anchor in anchors_in_table:
                href = anchor.get_attribute("href") or ""
                onclick = anchor.get_attribute("onclick") or ""
                if len(samples) < 10:
                    samples.append({"href": href, "onclick": onclick})
                normalized_url = _normalize_ticket_url(href, onclick)
                if not normalized_url:
                    rejected_links += 1
                    if len(rejected_with_reason) < 5:
                        rejected_with_reason.append(("missing_href_or_onclick_url", ""))
                    continue

                kind = classify_url(normalized_url)
                if kind in {"dsx_circuit", "file_share"}:
                    rejected_links += 1
                    if len(rejected_with_reason) < 5:
                        rejected_with_reason.append((f"filtered:{kind}", normalized_url))
                    continue
                if scrape_ticket_details_enabled and kind == "new_ticket" and not include_new_ticket_links:
                    rejected_links += 1
                    if len(rejected_with_reason) < 5:
                        rejected_with_reason.append(("filtered:new_ticket", normalized_url))
                    continue
                if scrape_ticket_details_enabled and kind == "other":
                    rejected_links += 1
                    if len(rejected_with_reason) < 5:
                        rejected_with_reason.append(("filtered:other", normalized_url))
                    continue

                if normalized_url in seen:
                    continue
                seen.add(normalized_url)
                entry = build_ticket_url_entry(normalized_url)
                links.append(entry)
                if kind == "ticket_detail":
                    kept_ticket_detail += 1
                elif kind == "new_ticket":
                    kept_new_ticket += 1
                else:
                    kept_other += 1

            links = sorted(links, key=lambda item: (_url_kind_priority(as_str(item.get("kind"))), as_str(item.get("url"))))
            kept_total = len(links)
            debug_ctx["table_row_count"] = row_count
            debug_ctx["link_count"] = kept_total
            debug_ctx["panel_anchor_samples"] = samples
            debug_ctx["total_anchors_in_panel"] = total_anchors_in_panel
            debug_ctx["anchors_in_table"] = anchors_total
            debug_ctx["accepted_ticket_links"] = kept_total
            debug_ctx["rejected_links"] = rejected_links
            if log_links and phase_logs:
                realtime_phase_logger.log(
                    f"[{_iso_utc_now()}] PHASE EXTRACT_URLS handle={handle} anchors_total={anchors_total} "
                    f"kept_total={kept_total} kept_ticket_detail={kept_ticket_detail} "
                    f"kept_new_ticket={kept_new_ticket} kept_other={kept_other}"
                )
                accepted_sample = [as_str(item.get("url")) for item in links if as_str(item.get("kind")) == "ticket_detail"][:5]
                realtime_phase_logger.log(
                    f"[{_iso_utc_now()}] PHASE URL_SAMPLES handle={handle} accepted_ticket_detail={accepted_sample} "
                    f"rejected={rejected_with_reason[:5]}"
                )
            return links

        all_tickets: dict[str, List[dict[str, Optional[str]]]] = {}

        def process_handle(handle: str) -> List[dict[str, Optional[str]]]:
            print(f"[HANDLE] Starting {handle}", flush=True)
            debug_log_path = os.path.join(debug_dir, f"debug_log_{handle}.txt")
            debug_lines: List[str] = []
            tickets: List[dict[str, Optional[str]]] = []

            def _dbg(msg: str) -> None:
                line = f"{_iso_utc_now()} {msg}"
                debug_lines.append(line)
                if phase_logs:
                    print(line, flush=True)

            def _write_probe_and_artifacts(reason: str, debug_ctx: dict[str, Any]) -> None:
                probe = _probe_company_dom(clicked_selector=as_str(debug_ctx.get("clicked_selector")))
                probe_path = os.path.join(debug_dir, f"company_{handle}_probe.json")
                with open(probe_path, "w", encoding="utf-8") as pf:
                    json.dump(probe, pf, indent=2)
                if dump_dom_on_fail:
                    _write_text(os.path.join(debug_dir, f"company_{handle}_fail.html"), driver.page_source or "")
                    try:
                        driver.save_screenshot(os.path.join(debug_dir, f"company_{handle}_fail.png"))
                    except Exception:
                        pass
                _dbg(f"failure_reason={reason} probe={probe_path}")

            try:
                _dbg(f"current_url={driver.current_url} handle={handle}")
                t_nav = time.monotonic()
                _phase(1, "NAVIGATE", f"url={driver.current_url}", t_nav)
                t_auth = time.monotonic()
                _phase(2, "AUTH CHECK", f"logged_in={not _is_login_redirect(driver)}", t_auth)
                t0 = time.monotonic()
                _phase(3, "HANDLE PAGE", f"handle={handle} url={driver.current_url}", t0)
                search_company(driver, handle)
                if not wait_company_handle(driver, handle, timeout=20):
                    raise RuntimeError(f"Company handle verification failed for {handle}")

                wait = WebDriverWait(driver, 15)
                debug_ctx: dict[str, Any] = {"handle": handle, "selectors_tried": []}
                expand_ok = False
                for attempt in range(1, 4):
                    try:
                        t_expand = time.monotonic()
                        expand_trouble_tickets_section(driver, wait, debug_ctx)
                        _phase(4, "EXPAND TICKETS", f"selector={debug_ctx.get('clicked_selector','')} attempt={attempt}", t_expand)
                        verify_trouble_ticket_rows(driver, timeout=8)
                        wait.until(lambda d: len(extract_ticket_urls_from_company_page(d, debug_ctx, log_links=False)) > 0 or "no ticket" in (d.page_source or "").lower())
                        expand_ok = True
                        break
                    except (StaleElementReferenceException, TimeoutException, RuntimeError) as exc:
                        _dbg(f"expand_attempt={attempt} exception={exc}")
                        if attempt == 3:
                            _log_fail("EXPAND_TICKETS", handle, exc, debug_ctx)
                            _write_probe_and_artifacts("expand_failed", debug_ctx)
                            raise

                if expand_ok:
                    t_parse = time.monotonic()
                    tickets = extract_ticket_urls_from_company_page(driver, debug_ctx)
                    _phase(5, "PARSE TABLE", f"rows={debug_ctx.get('table_row_count',0)} links={len(tickets)}", t_parse)
                if not tickets:
                    print(f"[TICKET] No URLs found for {handle}", flush=True)
                    _write_probe_and_artifacts("parse_no_urls", debug_ctx)

                if edge_smoke_test:
                    probe = _probe_company_dom(clicked_selector=as_str(debug_ctx.get("clicked_selector")))
                    print(f"[SMOKE] handle={handle} probe={json.dumps(probe, sort_keys=True)}", flush=True)

                all_tickets[handle] = tickets
                out_path = os.path.join(output_dir, f"tickets_{handle}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump({"handle": handle, "tickets": tickets}, f, indent=2)
                print(f"[HANDLE] {handle} tickets={len(tickets)}", flush=True)
            except InvalidSessionIdException as e:
                print(f"[ERROR] Invalid session id while processing {handle}: {e}", flush=True)
                raise
            except Exception as e:
                print(f"[ERROR] Exception for handle {handle}: {e}", flush=True)
            finally:
                with open(debug_log_path, "w", encoding="utf-8") as dbg:
                    dbg.write("\n".join(debug_lines) + "\n")
                print(f"[HANDLE] Finished {handle}. Log: {debug_log_path}", flush=True)
            return tickets

        def is_invalid_session_error(err: Exception) -> bool:
            return "invalid session id" in str(err).lower()

        abort_run = False
        total_ticket_scraped = 0
        total_ticket_skipped = 0
        total_ticket_failed = 0
        noc_tickets_session_state = {"ok": False}
        for handle in handles:
            retries = 0
            while True:
                try:
                    tickets = process_handle(handle)
                    if scrape_ticket_details_enabled:
                        summary = scrape_ticket_details(
                            driver=driver,
                            handle=handle,
                            ticket_urls=tickets,
                            out_dir=output_dir,
                            max_tickets=max_tickets,
                            save_html=save_html,
                            resume=resume,
                            preauth_noc_tickets=preauth_noc_tickets,
                            preauth_url=preauth_url,
                            preauth_timeout=preauth_timeout,
                            preauth_pause=preauth_pause,
                            retry_on_auth_redirect=retry_on_auth_redirect,
                            cookie_store_path=cookie_store_path,
                            load_cookies_before_auth=load_cookies,
                            save_cookies_after_auth=save_cookies and save_cookies_after_auth,
                            auth_timeout=auth_timeout,
                            noc_tickets_authed=noc_tickets_session_state,
                            phase_logger=realtime_phase_logger,
                        )
                        total_ticket_scraped += summary.get("scraped", 0)
                        total_ticket_skipped += summary.get("skipped", 0)
                        total_ticket_failed += summary.get("failed", 0)
                    break
                except InvalidSessionIdException as e:
                    print(f"[WARN] Invalid session id detected for {handle}.")
                    if attach_mode:
                        print("[WARN] Attach mode active; skipping driver restart and aborting remaining handles.")
                        abort_run = True
                        break
                    if retries >= 1:
                        print("[ERROR] Already restarted once; aborting remaining handles.")
                        abort_run = True
                        break
                    retries += 1
                    restart_driver("invalid session id")
                except WebDriverException as e:
                    if is_invalid_session_error(e):
                        print(f"[WARN] Invalid session id detected for {handle}: {e}")
                        if attach_mode:
                            print("[WARN] Attach mode active; skipping driver restart and aborting remaining handles.")
                            abort_run = True
                            break
                        if retries >= 1:
                            print("[ERROR] Already restarted once; aborting remaining handles.")
                            abort_run = True
                            break
                        retries += 1
                        restart_driver("invalid session id")
                        continue
                    raise
            if abort_run:
                break
        if all_tickets:
            all_path = os.path.join(output_dir, "tickets_all.json")
            try:
                with open(all_path, "w", encoding="utf-8") as f:
                    json.dump(all_tickets, f, indent=2)
                print(f"[INFO] Wrote combined tickets to {all_path}")
            except Exception as exc:
                print(f"[WARN] Could not write combined tickets file: {exc}")
        if scrape_ticket_details_enabled:
            print(
                "[TICKET] Overall: "
                f"scraped={total_ticket_scraped} skipped={total_ticket_skipped} failed={total_ticket_failed}"
            )
        if build_kb:
            print(f"[{_iso_utc_now()}] [PHASE 07 BUILD KB] items_written=pending", flush=True)
            if not kb_jsonl:
                kb_jsonl = os.path.join(output_dir, "kb.jsonl")
            build_kb_index(
                out_dir=output_dir,
                resume=resume,
                kb_jsonl=kb_jsonl,
                kb_sqlite=kb_sqlite,
            )
    except KeyboardInterrupt:
        print("[WARN] Interrupted by user (Ctrl+C). Shutting down.")
    finally:
        if no_quit and driver:
            print("[WARN] --no-quit set; leaving browser open.")
        elif driver and created_browser:
            try:
                driver.quit()
            except Exception:
                pass


def _load_config():
    spec = importlib.util.find_spec("webscraper.ultimate_scraper_config")
    if spec is not None:
        return importlib.import_module("webscraper.ultimate_scraper_config")
    config_path = os.path.join(os.path.dirname(__file__), "ultimate_scraper_config.py")
    spec = importlib.util.spec_from_file_location("ultimate_scraper_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load ultimate_scraper_config.py")
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


def add_cookie_persistence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cookie-store", dest="cookie_store", help="Path to persistent cookie store JSON")
    parser.add_argument("--save-cookies-after-auth", dest="save_cookies_after_auth", action="store_true", help="Save cookies after auth flow completes")


def main() -> int:
    # Prefer config defaults, allow CLI overrides, and finally env overrides
    cfg = _load_config()

    default_url = getattr(cfg, "DEFAULT_URL", "https://noc.123.net/customers")
    default_target_url = getattr(
        cfg,
        "DEFAULT_TARGET_URL",
        "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
    )
    default_out = getattr(cfg, "DEFAULT_OUTPUT_DIR", os.path.join("webscraper", "output"))
    default_handles = getattr(cfg, "DEFAULT_HANDLES", ["123NET"])  # list
    default_headless = getattr(cfg, "DEFAULT_HEADLESS", True)

    parser = argparse.ArgumentParser(description="Selenium ticket scraper (config-driven)")
    parser.add_argument("--url", default=default_url, help="Target URL (e.g., customers.cgi)")
    parser.add_argument("--out", default=default_out, help="Output directory")
    parser.add_argument("--handles", nargs="+", default=default_handles, help="One or more customer handles")
    parser.add_argument("--handles-file", help="Path to a file containing handles (one per line; '#' for comments)")
    parser.add_argument("--show", action="store_true", help="Run browser in visible (non-headless) mode")
    parser.add_argument("--vacuum", action="store_true", help="Aggressively crawl internal links after search to save pages")
    parser.add_argument("--aggressive", action="store_true", help="Enable extreme scraping: network logs, infinite scroll, deep vacuum")
    parser.add_argument("--cookie-file", help="Path to Selenium cookies JSON to reuse authenticated session")
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="Use HTTP requests for scraping (Selenium only used to obtain cookies; avoids GUI interactions).",
    )
    parser.add_argument(
        "--attach",
        type=int,
        help="Attach to an existing Edge remote-debugging port (requires launching Edge with --remote-debugging-port; "
        "scraper will not auto-launch a browser in attach mode)",
    )
    parser.add_argument(
        "--auto-attach",
        action="store_true",
        help="If --attach not provided, try to attach to 127.0.0.1:9222 (requires Edge launched with "
        "--remote-debugging-port; scraper will not auto-launch a browser in attach mode)",
    )
    parser.add_argument("--attach-host", default="127.0.0.1", help="Edge debugger host (default 127.0.0.1)")
    parser.add_argument("--attach-timeout", type=float, default=2.0, help="Timeout for Edge debugger probe (seconds)")
    parser.add_argument("--fallback-profile-dir", default="webscraper/edge_profile_tmp", help="Profile dir for fallback Edge launch")
    parser.add_argument("--edge-smoke-test", action="store_true", help="Run a basic Edge driver smoke test and exit")
    parser.add_argument("--target-url", default=default_target_url, help="Target URL to open after driver init")
    parser.add_argument("--auth-dump", action="store_true", help="Run auth diagnostics and dump safe cookie/storage signals")
    parser.add_argument("--auth-pause", action="store_true", help="Pause for manual login before dumping auth signals")
    parser.add_argument("--auth-timeout", type=int, default=180, help="Timeout (seconds) for auth pause")
    parser.add_argument("--auth-url", default=default_target_url, help="URL to open for auth diagnostics")
    parser.add_argument(
        "--auth-check-url",
        default=default_target_url,
        help="URL used by auth orchestration health checks",
    )
    parser.add_argument("--profile-dir", help="Override profile directory for Edge/Chrome (no venv activation required)")
    parser.add_argument("--profile-name", help="Chromium profile name (e.g., Default, Profile 1)")
    parser.add_argument(
        "--auth-profile-only",
        action="store_true",
        help="Only attempt auth using the provided --profile-dir/profile-name (skip other strategies)",
    )
    parser.add_argument(
        "--self-test-auth-strategy",
        action="store_true",
        help="Run auth strategy self-test and exit",
    )
    parser.add_argument("--no-quit", action="store_true", help="Do not quit the driver after auth diagnostics")
    parser.add_argument("--edge-only", action="store_true", help="Force Edge path for this run")
    parser.add_argument(
        "--edge-temp-profile",
        action="store_true",
        help="In auth mode, use a fresh temporary Edge profile under webscraper/output/<run_id>/edge_tmp_profile",
    )
    parser.add_argument(
        "--edge-kill-before",
        action="store_true",
        help="Kill msedge.exe and msedgedriver.exe before launching Edge (Windows only)",
    )
    parser.add_argument(
        "--no-auth-orchestrator",
        action="store_true",
        help="Disable auth orchestration and use legacy auth flow",
    )
    parser.add_argument(
        "--auth-orchestrate",
        action="store_true",
        help="Enable auth orchestration (default on unless disabled)",
    )
    parser.add_argument(
        "--scrape-ticket-details",
        action="store_true",
        help="After collecting ticket links, visit each ticket page and save ticket artifacts",
    )
    parser.add_argument(
        "--tickets-json",
        help="Path to tickets_all.json (defaults to <out>/tickets_all.json if present)",
    )
    parser.add_argument(
        "--include-new-ticket-links",
        action="store_true",
        help="Keep /new_ticket links in extracted output (still sorted after ticket_detail links)",
    )
    parser.add_argument(
        "--kb-dir",
        default=os.path.join("webscraper", "knowledge_base"),
        help="Knowledge base output directory (default: webscraper/knowledge_base)",
    )
    parser.add_argument(
        "--build-kb",
        action="store_true",
        help="Build KB index (kb.jsonl) from scraped ticket artifacts after scraping",
    )
    parser.add_argument(
        "--kb-jsonl",
        help="KB JSONL output path (default: <out>/kb.jsonl)",
    )
    parser.add_argument(
        "--kb-sqlite",
        help="Optional SQLite DB path (if provided, also write KB SQLite)",
    )
    parser.add_argument("--max-tickets", type=int, help="Optional limit for number of tickets to scrape")
    parser.add_argument("--rate-limit", type=float, default=0.5, help="Sleep between ticket pages (seconds)")
    parser.add_argument("--resume", action="store_true", help="Skip tickets already present in sqlite by ticket_id")
    parser.add_argument("--save-html", action="store_true", help="Save raw HTML per ticket_id")
    parser.add_argument("--save-screenshot", action="store_true", help="Save screenshot per ticket_id")
    parser.add_argument("--preauth-noc-tickets", dest="preauth_noc_tickets", action="store_true", help="Enable noc-tickets session warm-up when auth redirects are detected")
    parser.add_argument("--no-preauth-noc-tickets", dest="preauth_noc_tickets", action="store_false", help="Disable noc-tickets session warm-up flow")
    parser.set_defaults(preauth_noc_tickets=None)
    parser.add_argument("--preauth-url", default="https://noc-tickets.123.net/", help="URL used for noc-tickets pre-auth warm-up")
    parser.add_argument("--preauth-timeout", type=int, default=180, help="Timeout in seconds for noc-tickets pre-auth warm-up")
    add_cookie_persistence_args(parser)
    parser.add_argument("--load-cookies", dest="load_cookies", action="store_true", help="Load noc-tickets cookies from --cookie-store before auth warm-up")
    parser.add_argument("--no-load-cookies", dest="load_cookies", action="store_false", help="Disable cookie preload before auth warm-up")
    parser.set_defaults(load_cookies=True)
    parser.add_argument("--save-cookies", dest="save_cookies", action="store_true", help="Enable saving noc-tickets cookies to --cookie-store")
    parser.add_argument("--no-save-cookies", dest="save_cookies", action="store_false", help="Disable noc-tickets cookie persistence")
    parser.set_defaults(save_cookies=True)
    parser.add_argument("--no-save-cookies-after-auth", dest="save_cookies_after_auth", action="store_false", help="Do not save cookies after auth warm-up")
    parser.set_defaults(save_cookies_after_auth=True)
    parser.add_argument("--preauth-pause", dest="preauth_pause", action="store_true", help="Pause for manual login in visible browser during noc-tickets pre-auth")
    parser.add_argument("--no-preauth-pause", dest="preauth_pause", action="store_false", help="Do not pause for manual login during noc-tickets pre-auth")
    parser.set_defaults(preauth_pause=True)
    parser.add_argument("--retry-on-auth-redirect", type=int, default=2, help="Retries per ticket after auth redirect warm-up")
    parser.add_argument("--phase-logs", dest="phase_logs", action="store_true", help="Emit phase-by-phase progress logs")
    parser.add_argument("--no-phase-logs", dest="phase_logs", action="store_false", help="Disable phase logs")
    parser.set_defaults(phase_logs=None)
    parser.add_argument("--debug-dir", help="Directory for per-handle debug artifacts (default: --out)")
    parser.add_argument("--dump-dom-on-fail", dest="dump_dom_on_fail", action="store_true", help="Save fail HTML/PNG/probe artifacts")
    parser.add_argument("--no-dump-dom-on-fail", dest="dump_dom_on_fail", action="store_false", help="Disable fail HTML/PNG/probe artifacts")
    parser.set_defaults(dump_dom_on_fail=True)
    args = parser.parse_args()
    if args.phase_logs is None:
        args.phase_logs = bool(args.show or args.save_html or args.save_screenshot)
    if args.preauth_noc_tickets is None:
        args.preauth_noc_tickets = bool(args.scrape_ticket_details)

    if args.self_test_auth_strategy:
        self_test_auth_strategy_profile_only()
        print("[INFO] Auth strategy self-test passed.")
        return 0

    # Env overrides last
    url = os.environ.get("SCRAPER_URL") or args.url
    out_dir = os.environ.get("SCRAPER_OUT") or args.out
    kb_jsonl = args.kb_jsonl or os.path.join(out_dir, "kb.jsonl")
    cookie_file = os.environ.get("SCRAPER_COOKIE_FILE") or args.cookie_file
    cookie_store_path = os.environ.get("SCRAPER_COOKIE_STORE") or args.cookie_store or cookie_file
    # Determine handles precedence: --handles-file > env > CLI list
    handles_env = os.environ.get("SCRAPER_HANDLES")
    handles = None
    if args.handles_file:
        try:
            with open(args.handles_file, "r", encoding="utf-8") as hf:
                lines = hf.read().splitlines()
                handles = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
            print(f"[INFO] Loaded {len(handles)} handles from {args.handles_file}")
        except Exception as e:
            print(f"[WARN] Could not read handles file '{args.handles_file}': {e}")
            handles = None
    if handles is None:
        handles = [h.strip() for h in handles_env.split(",")] if handles_env else args.handles
    headless_env = os.environ.get("SCRAPER_HEADLESS")
    headless_requested = headless_env == "1"
    headless = default_headless if headless_env is None else (headless_env == "1")
    if args.show:
        headless = False

    def _load_config_credentials() -> tuple[Optional[str], Optional[str]]:
        try:
            from webscraper import webscraper_config
        except Exception:
            return None, None
        try:
            creds = (
                webscraper_config.WEBSCRAPER_CONFIG.get("environments", {})
                .get("default", {})
                .get("credentials", {})
            )
            username = creds.get("username")
            password = creds.get("password")
        except Exception:
            return None, None
        if not username or str(username).upper() == "REDACTED":
            username = None
        if not password or str(password).upper() == "REDACTED":
            password = None
        return username, password

    config_username, config_password = _load_config_credentials()
    auth_username = os.environ.get("SCRAPER_USERNAME") or os.environ.get("SCRAPER_AUTH_USERNAME") or config_username
    auth_password = os.environ.get("SCRAPER_PASSWORD") or os.environ.get("SCRAPER_AUTH_PASSWORD") or config_password
    auth_user_agent = os.environ.get("SCRAPER_AUTH_USER_AGENT") or os.environ.get("SCRAPER_USER_AGENT")
    auth_check_url = os.environ.get("SCRAPER_AUTH_CHECK_URL") or args.auth_check_url or args.auth_url
    auth_mode = os.environ.get("SCRAPER_AUTH_MODE")

    auth_orchestration_cfg = getattr(cfg, "AUTH_ORCHESTRATION", True)
    auth_orchestration_env = os.environ.get("SCRAPER_AUTH_ORCHESTRATION")
    auth_orchestration = auth_orchestration_cfg
    if auth_orchestration_env is not None:
        auth_orchestration = auth_orchestration_env == "1"
    if args.no_auth_orchestrator:
        auth_orchestration = False
    if args.auth_orchestrate:
        auth_orchestration = True

    auth_profile_dirs = getattr(cfg, "AUTH_PROFILE_DIRS", [])
    auth_profile_env = os.environ.get("SCRAPER_PROFILE_DIRS") or os.environ.get("SCRAPER_AUTH_PROFILE_DIRS")
    if auth_profile_env:
        auth_profile_dirs = [item.strip() for item in auth_profile_env.split(",") if item.strip()]
    if not auth_profile_dirs:
        base_dir = os.path.dirname(__file__)
        auth_profile_dirs = [
            os.path.join(base_dir, "edge_profile"),
            os.path.join(base_dir, "edge_profile_fallback"),
            os.path.join(base_dir, "edge_profile_selenium"),
            os.path.join(base_dir, "edge_profile_tmp"),
            os.path.join(base_dir, "edge_profile_tmp_test"),
            os.path.join(base_dir, "chrome_profile"),
            os.path.join(base_dir, "chrome_profile_live"),
        ]

    auth_cookie_files = getattr(cfg, "AUTH_COOKIE_FILES", [])
    auth_cookie_env = os.environ.get("SCRAPER_COOKIE_FILES") or os.environ.get("SCRAPER_AUTH_COOKIE_FILES")
    if auth_cookie_env:
        auth_cookie_files = [item.strip() for item in auth_cookie_env.split(",") if item.strip()]
    if not auth_cookie_files:
        default_cookie_file = getattr(cfg, "DEFAULT_COOKIE_FILE", None)
        auth_cookie_files = [
            p for p in [
                cookie_file,
                default_cookie_file,
                "cookies.json",
                "live_cookies.json",
                "cookies_netscape_format.txt",
            ]
            if p
        ]

    edge_profile_override = None
    if (args.auth_dump or args.auth_pause) and args.edge_temp_profile:
        edge_profile_override = edge_profile_dir(args)

    profile_dir_override = os.path.abspath(args.profile_dir) if args.profile_dir else None
    if args.http_only:
        http_scrape_customers(
            handles=handles,
            output_dir=out_dir,
            cookie_file=cookie_file,
            target_url=args.target_url,
            profile_dir_override=profile_dir_override,
            profile_name=args.profile_name or "Default",
            resolved_profiles=[os.path.abspath(p) for p in auth_profile_dirs],
            resolved_cookies=[os.path.abspath(p) for p in auth_cookie_files if p],
            auth_mode_value=auth_mode,
            auth_profile_only=args.auth_profile_only,
            headless=headless,
            attach=args.attach,
            auto_attach=args.auto_attach,
            attach_host=args.attach_host,
            attach_timeout=args.attach_timeout,
            fallback_profile_dir=args.fallback_profile_dir,
            edge_temp_profile=args.edge_temp_profile,
            edge_kill_before=args.edge_kill_before,
            show_browser=args.show,
            edge_binary_path_resolved=edge_binary_path(),
            edge_driver_env=os.environ.get("EDGEDRIVER_PATH"),
            auth_username=auth_username,
            auth_password=auth_password,
            auth_check_url=auth_check_url,
            auth_user_agent=auth_user_agent,
        )
        return 0

    selenium_scrape_tickets(
        url=url,
        output_dir=out_dir,
        handles=handles,
        headless=headless,
        headless_requested=headless_requested,
        vacuum=args.vacuum,
        aggressive=args.aggressive,
        cookie_file=cookie_file,
        attach=args.attach,
        auto_attach=args.auto_attach,
        attach_host=args.attach_host,
        attach_timeout=args.attach_timeout,
        fallback_profile_dir=args.fallback_profile_dir,
        target_url=args.target_url,
        auth_dump=args.auth_dump,
        auth_pause=args.auth_pause,
        auth_timeout=args.auth_timeout,
        auth_url=args.auth_url,
        profile_dir=args.profile_dir,
        profile_name=args.profile_name,
        no_quit=args.no_quit,
        edge_only=args.edge_only,
        edge_profile_dir_override=edge_profile_override,
        edge_temp_profile=args.edge_temp_profile,
        edge_kill_before=args.edge_kill_before,
        show_browser=args.show,
        auth_orchestration=auth_orchestration,
        auth_profile_dirs=auth_profile_dirs,
        auth_cookie_files=auth_cookie_files,
        auth_username=auth_username,
        auth_password=auth_password,
        auth_check_url=auth_check_url,
        auth_user_agent=auth_user_agent,
        auth_mode=auth_mode,
        auth_profile_only=args.auth_profile_only,
        scrape_ticket_details_enabled=args.scrape_ticket_details,
        tickets_json=args.tickets_json,
        kb_dir=args.kb_dir,
        build_kb=args.build_kb,
        kb_jsonl=kb_jsonl,
        kb_sqlite=args.kb_sqlite,
        max_tickets=args.max_tickets,
        rate_limit=args.rate_limit,
        resume=args.resume,
        save_html=args.save_html,
        save_screenshot=args.save_screenshot,
        phase_logs=args.phase_logs,
        debug_dir=args.debug_dir or out_dir,
        dump_dom_on_fail=args.dump_dom_on_fail,
        edge_smoke_test=args.edge_smoke_test,
        preauth_noc_tickets=args.preauth_noc_tickets,
        preauth_url=args.preauth_url,
        preauth_timeout=args.preauth_timeout,
        preauth_pause=args.preauth_pause,
        retry_on_auth_redirect=args.retry_on_auth_redirect,
        cookie_store_path=cookie_store_path,
        load_cookies=args.load_cookies,
        save_cookies=args.save_cookies,
        save_cookies_after_auth=args.save_cookies_after_auth,
        include_new_ticket_links=args.include_new_ticket_links,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
