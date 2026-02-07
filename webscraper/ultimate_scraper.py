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
import glob
import json
import re
import sqlite3
import time
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Any, List, Optional, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from selenium import webdriver
    from webscraper.auth import AuthMode

try:
    from bs4 import BeautifulSoup
except Exception as exc:
    BeautifulSoup = None
    _BS4_IMPORT_ERROR = exc
else:
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
    path = parsed.path or ""
    if not path:
        return None
    last_segment = path.rstrip("/").split("/")[-1]
    return last_segment or None


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
                profile_hint = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "edge_remote_profile")
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
                profile_hint = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "edge_remote_profile")
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


def save_cookies_json(driver: Any, path: str) -> None:
    try:
        cookies = driver.get_cookies()
        allowed_keys = {"name", "value", "path", "domain", "secure", "httpOnly", "expiry"}
        sanitized = [{k: c[k] for k in c if k in allowed_keys} for c in cookies]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2)
        print(f"[INFO] Saved {len(sanitized)} cookies to {path}")
    except Exception as e:
        print(f"[WARN] Could not save cookies: {e}")


def load_cookies_json(driver: Any, path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        added = 0
        for c in cookies:
            try:
                cookie = {k: c[k] for k in c if k in ("name", "value", "path", "domain", "secure", "httpOnly", "expiry")}
                driver.add_cookie(cookie)
                added += 1
            except Exception:
                continue
        print(f"[INFO] Loaded {added}/{len(cookies)} cookies from {path}")
        return added > 0
    except Exception as e:
        print(f"[WARN] Cookie injection skipped: {e}")
        return False


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
        from webscraper.auth import AuthMode
        return AuthMode
    except ModuleNotFoundError:
        try:
            from auth import AuthMode
            return AuthMode
        except ModuleNotFoundError:
            return None


def _resolve_auth_symbols() -> Optional[tuple[Any, Any, Any]]:
    try:
        from webscraper.auth import AuthContext, AuthMode, authenticate
        return AuthContext, AuthMode, authenticate
    except ModuleNotFoundError:
        try:
            from auth import AuthContext, AuthMode, authenticate
            return AuthContext, AuthMode, authenticate
        except ModuleNotFoundError:
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


def _load_tickets_json(path: str) -> dict[str, List[str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "handle" in data and "tickets" in data:
                handle = str(data.get("handle"))
                tickets = data.get("tickets")
                if handle and isinstance(tickets, list):
                    return {handle: [str(item) for item in tickets if item]}
            return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as exc:
        print(f"[WARN] Could not read tickets json '{path}': {exc}")
    return {}


def _load_ticket_urls_for_handle(output_dir: str, handle: str) -> List[str]:
    handle_path = os.path.join(output_dir, f"tickets_{handle}.json")
    if os.path.exists(handle_path):
        data = _load_tickets_json(handle_path)
        if handle in data:
            return [str(item) for item in data[handle] if item]
    all_path = os.path.join(output_dir, "tickets_all.json")
    if os.path.exists(all_path):
        data = _load_tickets_json(all_path)
        if handle in data:
            return [str(item) for item in data[handle] if item]
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


def scrape_ticket_details(
    driver: Any,
    handle: str,
    ticket_urls: List[str],
    out_dir: str,
    max_tickets: Optional[int],
    save_html: bool,
    resume: bool,
) -> dict:
    bs4 = require_beautifulsoup()
    urls = [u for u in ticket_urls if u]
    if not urls:
        urls = _load_ticket_urls_for_handle(out_dir, handle)
    if not urls:
        print(f"[TICKET] No URLs found for {handle}")
        return {"handle": handle, "scraped": 0, "skipped": 0, "failed": 0, "total": 0}

    ticket_root = os.path.join(out_dir, "tickets", handle)
    os.makedirs(ticket_root, exist_ok=True)

    scraped = 0
    skipped = 0
    failed = 0
    total = 0

    for url in urls:
        if max_tickets is not None and total >= max_tickets:
            break
        total += 1
        ticket_id = parse_ticket_id(url)
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
            driver.get(url)
            _wait_for_ticket_ready(driver, timeout=25)
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

            extracted_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
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
    kb_sqlite: Optional[str] = None,
    max_tickets: Optional[int] = None,
    rate_limit: float = 0.5,
    resume: bool = False,
    save_html: bool = False,
    save_screenshot: bool = False,
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
        TimeoutException,
        WebDriverException,
    )

    os.makedirs(output_dir, exist_ok=True)
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
                injected = load_cookies_json(driver, cookie_file)
                if injected:
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
            # Persist current authenticated session cookies
            cookies_path = os.path.join(output_dir, "selenium_cookies.json")
            save_cookies_json(driver, cookies_path)
            if cookie_file:
                save_cookies_json(driver, cookie_file)

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

        def save_debug_artifacts(handle: str, label: str) -> None:
            safe_label = label.replace(" ", "_").lower()
            html_path = os.path.join(output_dir, f"{handle}_{safe_label}.html")
            png_path = os.path.join(output_dir, f"{handle}_{safe_label}.png")
            try:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except Exception as exc:
                print(f"[WARN] Could not save HTML ({label}) for {handle}: {exc}")
            try:
                driver.save_screenshot(png_path)
            except Exception as exc:
                print(f"[WARN] Could not save screenshot ({label}) for {handle}: {exc}")

        def search_company(driver: Any, handle: str) -> None:
            search_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#customers"))
            )
            query = f"{handle}:company_data:handle:{handle}"
            search_box.clear()
            search_box.send_keys(query)
            time.sleep(0.1)
            try:
                search_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "input[type='submit'][value='Search ->']")
                    )
                )
            except TimeoutException:
                search_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//input[@type='submit' and contains(@value,'Search')]")
                    )
                )
            try:
                search_btn.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", search_btn)

        def wait_company_handle(driver: Any, handle: str, timeout: int = 20) -> bool:
            def _matches(drv: Any) -> bool:
                th_elements = drv.find_elements(
                    By.XPATH, "//th[contains(normalize-space(), 'Company Handle')]"
                )
                for th in th_elements:
                    try:
                        td = th.find_element(By.XPATH, "following-sibling::td[1]")
                    except Exception:
                        continue
                    value = (td.text or "").strip()
                    if value == handle:
                        return True
                return False

            try:
                WebDriverWait(driver, timeout).until(lambda d: _matches(d))
                return True
            except TimeoutException:
                return False

        def reveal_trouble_ticket_data(driver: Any) -> bool:
            try:
                toggle = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.show_hide[rel='#slideid5']"))
                )
            except TimeoutException:
                return False
            try:
                toggle.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", toggle)
            try:
                WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#slideid5"))
                )
                return True
            except TimeoutException:
                return False

        def scrape_ticket_links(driver: Any) -> List[str]:
            links: List[str] = []
            seen = set()
            for link in driver.find_elements(By.CSS_SELECTOR, "#slideid5 a[href*='/ticket/']"):
                href = link.get_attribute("href")
                if not href or href in seen:
                    continue
                seen.add(href)
                links.append(href)
            return links

        all_tickets: dict[str, List[str]] = {}

        def process_handle(handle: str) -> List[str]:
            print(f"[HANDLE] Starting {handle}")
            debug_log_path = os.path.join(output_dir, f"debug_log_{handle}.txt")
            debug_buffer = io.StringIO()
            tickets: List[str] = []
            try:
                with contextlib.redirect_stdout(debug_buffer), contextlib.redirect_stderr(debug_buffer):
                    print(f"[DEBUG] Navigated to: {driver.current_url}")
                    print(f"[DEBUG] Processing handle: {handle}")
                    save_debug_artifacts(handle, "before_search")
                    try:
                        search_company(driver, handle)
                    except TimeoutException as exc:
                        print(f"[ERROR] Search flow failed for {handle}: {exc}")
                        save_debug_artifacts(handle, "search_failed")
                        all_tickets[handle] = []
                        return []
                    if not wait_company_handle(driver, handle, timeout=20):
                        print(f"[WARN] Company handle verification failed for {handle}")
                        save_debug_artifacts(handle, "company_handle_timeout")
                        all_tickets[handle] = []
                        return []
                    save_debug_artifacts(handle, "after_search_loaded")
                    if not reveal_trouble_ticket_data(driver):
                        print(f"[WARN] Trouble Ticket Data toggle missing for {handle}")
                        save_debug_artifacts(handle, "ticket_panel_missing")
                        all_tickets[handle] = []
                        return []
                    save_debug_artifacts(handle, "after_ticket_panel")
                    tickets = scrape_ticket_links(driver)
                    all_tickets[handle] = tickets
                    out_path = os.path.join(output_dir, f"tickets_{handle}.json")
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump({"handle": handle, "tickets": tickets}, f, indent=2)
                    print(f"[HANDLE] {handle} tickets={len(tickets)}")
            except InvalidSessionIdException as e:
                print(f"[ERROR] Invalid session id while processing {handle}: {e}")
                raise
            except Exception as e:
                # Also print to console for immediate visibility
                print(f"[ERROR] Exception for handle {handle}: {e}")
            finally:
                with open(debug_log_path, "w", encoding="utf-8") as dbg:
                    dbg.write(debug_buffer.getvalue())
                print(f"[HANDLE] Finished {handle}. Log: {debug_log_path}")
            return tickets

        def is_invalid_session_error(err: Exception) -> bool:
            return "invalid session id" in str(err).lower()

        abort_run = False
        total_ticket_scraped = 0
        total_ticket_skipped = 0
        total_ticket_failed = 0
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


def main() -> int:
    # Prefer config defaults, allow CLI overrides, and finally env overrides
    try:
        # When executed as a module (python -m webscraper.ultimate_scraper)
        from . import ultimate_scraper_config as cfg
    except Exception:
        # When executed as a plain script (python webscraper/ultimate_scraper.py),
        # ensure the project root is on sys.path, then try absolute import.
        import importlib
        import importlib.util
        import sys
        try:
            cfg = importlib.import_module("webscraper.ultimate_scraper_config")
        except Exception:
            try:
                pkg_dir = os.path.dirname(__file__)
                project_root = os.path.abspath(os.path.join(pkg_dir, os.pardir))
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)
                cfg = importlib.import_module("webscraper.ultimate_scraper_config")
            except Exception:
                # Final fallback: load config directly by file path
                config_path = os.path.join(os.path.dirname(__file__), "ultimate_scraper_config.py")
                spec = importlib.util.spec_from_file_location("ultimate_scraper_config", config_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Could not load ultimate_scraper_config.py")
                cfg = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cfg)
    import argparse
    import sys

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
        help="After collecting ticket links, visit each ticket page and build the knowledge base",
    )
    parser.add_argument(
        "--tickets-json",
        help="Path to tickets_all.json (defaults to <out>/tickets_all.json if present)",
    )
    parser.add_argument(
        "--kb-dir",
        default=os.path.join("webscraper", "knowledge_base"),
        help="Knowledge base output directory (default: webscraper/knowledge_base)",
    )
    parser.add_argument(
        "--kb-sqlite",
        help="SQLite DB path (default: <kb-dir>/hosted_tickets.sqlite)",
    )
    parser.add_argument("--max-tickets", type=int, help="Optional limit for number of tickets to scrape")
    parser.add_argument("--rate-limit", type=float, default=0.5, help="Sleep between ticket pages (seconds)")
    parser.add_argument("--resume", action="store_true", help="Skip tickets already present in sqlite by ticket_id")
    parser.add_argument("--save-html", action="store_true", help="Save raw HTML per ticket_id")
    parser.add_argument("--save-screenshot", action="store_true", help="Save screenshot per ticket_id")
    args = parser.parse_args()

    if args.edge_smoke_test:
        smoke_test_edge_driver()
        return 0
    if args.self_test_auth_strategy:
        self_test_auth_strategy_profile_only()
        print("[INFO] Auth strategy self-test passed.")
        return 0

    # Env overrides last
    url = os.environ.get("SCRAPER_URL") or args.url
    out_dir = os.environ.get("SCRAPER_OUT") or args.out
    cookie_file = os.environ.get("SCRAPER_COOKIE_FILE") or args.cookie_file
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
        kb_sqlite=args.kb_sqlite,
        max_tickets=args.max_tickets,
        rate_limit=args.rate_limit,
        resume=args.resume,
        save_html=args.save_html,
        save_screenshot=args.save_screenshot,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
