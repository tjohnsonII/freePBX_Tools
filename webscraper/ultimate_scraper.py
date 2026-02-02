"""
Ultimate Scraper (minimal baseline)

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
import time
import urllib.request
from datetime import datetime
from typing import Any, List, Optional, cast

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


def classes_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v if x).strip()
    return str(v).strip()


def edge_debug_is_up(host: str, port: int, timeout: float) -> bool:
    try:
        url = f"http://{host}:{port}/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


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


def selenium_scrape_tickets(
    url: str,
    output_dir: str,
    handles: List[str],
    headless: bool = True,
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
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import (
        InvalidSessionIdException,
        NoSuchElementException,
        SessionNotCreatedException,
        WebDriverException,
    )

    def require_beautifulsoup():
        if BeautifulSoup is None:
            raise RuntimeError(
                "BeautifulSoup (bs4) is required for HTML parsing. Install with `pip install beautifulsoup4`."
            ) from _BS4_IMPORT_ERROR
        return BeautifulSoup

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
    EDGEDRIVER = os.environ.get("EDGEDRIVER_PATH")
    edge_driver_env = EDGEDRIVER
    edge_binary_path_resolved = edge_binary_path()
    profile_dir_override = os.path.abspath(profile_dir) if profile_dir else None
    edge_profile_env = edge_profile_dir_override or os.environ.get("EDGE_PROFILE_DIR")
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

    effective_target_url = target_url or url
    effective_auth_url = auth_url or effective_target_url
    resolved_profile_name = profile_name or "Default"
    auth_mode = auth_dump or auth_pause
    enable_auth_orchestration = auth_orchestration and not auth_mode
    allow_manual_prompts = not enable_auth_orchestration
    if auth_mode or show_browser:
        headless = False
    if edge_temp_profile and not auth_mode:
        print("[INFO] --edge-temp-profile is only applied in auth mode; ignoring for this run.")

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

    def _confirm_edge_processes(edge_args: List[str], profile_dir: str) -> None:
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if _edge_processes_exist():
                return
            time.sleep(0.2)
        raise EdgeStartupError(
            "Edge appears to have exited immediately after startup.",
            edge_args=edge_args,
            profile_dir=profile_dir,
            edge_binary=edge_binary_path_resolved,
        )

    def _make_temp_profile_dir() -> str:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{run_id}_{os.getpid()}"
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "output", run_id))
        temp_dir = os.path.join(base, "edge_tmp_profile")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def _build_edge_options(profile_dir: Optional[str]) -> tuple["EdgeOptions", List[str]]:
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
        if profile_dir:
            edge_options.add_argument(f"--user-data-dir={profile_dir}")
            edge_args.append(f"--user-data-dir={profile_dir}")
            edge_options.add_argument(f"--profile-directory={resolved_profile_name}")
            edge_args.append(f"--profile-directory={resolved_profile_name}")
        if headless:
            edge_options.add_argument("--headless=new")
            edge_args.append("--headless=new")
            edge_options.add_argument("--disable-gpu")
            edge_args.append("--disable-gpu")
            edge_options.add_argument("--no-sandbox")
            edge_args.append("--no-sandbox")
        return edge_options, edge_args

    def create_driver() -> tuple["webdriver.Edge", bool, bool]:
        plan = []
        if attach:
            plan.append(("ATTACH_EXPLICIT", attach))
        if auto_attach and not attach:
            plan.append(("ATTACH_AUTO", 9222))
        plan.append(("LAUNCH_FALLBACK", None))

        edgedriver_path = _validate_path("EdgeDriver", edge_driver_env or EDGEDRIVER)
        last_error: Optional[Exception] = None

        for mode, port in plan:
            edge_options, edge_args = _build_edge_options(None)

            if mode in ("ATTACH_EXPLICIT", "ATTACH_AUTO"):
                attach_port = cast(int, port)
                if not edge_debug_is_up(attach_host, attach_port, attach_timeout):
                    last_error = RuntimeError(f"Edge debug endpoint not reachable at {attach_host}:{attach_port}")
                    print(f"[WARN] {mode} failed: {last_error}")
                    continue
                edge_options.add_experimental_option("debuggerAddress", f"{attach_host}:{attach_port}")
                print(f"[INFO] Edge args: {edge_args}")
                try:
                    service = EdgeService(log_output=os.path.join(output_dir, "msedgedriver.log"))
                    new_driver = webdriver.Edge(service=service, options=edge_options)
                    _confirm_edge_processes(edge_args, resolved_edge_profile_dir)
                except Exception as exc:
                    last_error = exc
                    print(f"[WARN] {mode} failed: {exc}")
                    continue
                print(f"[INFO] Driver init mode: {mode}")
                print(f"[INFO] Edge attached. Session id: {new_driver.session_id}")
                found = switch_to_target_tab(
                    new_driver,
                    effective_target_url,
                    url_contains="secure.123.net/cgi-bin/web_interface/admin/",
                )
                if not found:
                    try:
                        new_driver.get(effective_target_url)
                    except Exception:
                        pass
                return new_driver, False, True

            if mode == "LAUNCH_FALLBACK":
                _kill_edge_processes()
                fallback_dir = resolved_edge_profile_dir
                try:
                    os.makedirs(fallback_dir, exist_ok=True)
                except Exception as e:
                    print(f"[WARN] Could not create fallback Edge profile directory '{fallback_dir}': {e}")
                edge_options, edge_args = _build_edge_options(fallback_dir)
                print(f"[INFO] Edge args: {edge_args}")
                attempted_lock_cleanup = False
                temp_profile_used = False
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
                        try:
                            new_driver.get(effective_target_url)
                        except Exception:
                            pass
                        return new_driver, True, False
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
                            edge_options, edge_args = _build_edge_options(temp_dir)
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

    driver = cast("webdriver.Edge", None)
    created_browser = False
    attach_mode = False
    cookies_path: Optional[str] = None
    resolved_auth_profiles = [
        os.path.abspath(p) for p in (auth_profile_dirs or []) if p
    ]
    resolved_auth_cookies = [
        os.path.abspath(p) for p in (auth_cookie_files or []) if p
    ]

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

        driver, created_browser, attach_mode = create_driver()
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

    def initialize_driver() -> None:
        nonlocal driver, created_browser, attach_mode, cookies_path
        if enable_auth_orchestration:
            from webscraper.auth import AuthContext, authenticate

            auth_profile_dir = profile_dir_override or edge_profile_env
            auth_profile_dir = os.path.abspath(auth_profile_dir) if auth_profile_dir else None
            auth_profile_fallbacks = [p for p in resolved_auth_profiles if p != auth_profile_dir]
            auth_cookie_candidates = []
            if cookie_file:
                auth_cookie_candidates.append(cookie_file)
            auth_cookie_candidates.extend(resolved_auth_cookies)
            auth_ctx = AuthContext(
                base_url=effective_target_url,
                preferred_browser="edge",
                profile_dir=auth_profile_dir,
                profile_fallback_dirs=auth_profile_fallbacks,
                cookie_files=auth_cookie_candidates,
                username=auth_username,
                password=auth_password,
                user_agent=auth_user_agent,
                headless=headless,
                timeout_sec=30,
                auth_check_url=auth_check_url or effective_auth_url,
            )
            auth_result = authenticate(auth_ctx)
            if not auth_result.ok or not auth_result.driver:
                if auth_result.need_user_input:
                    print(auth_result.need_user_input.get("message", "Authentication failed."))
                raise SystemExit(2)
            driver = auth_result.driver
            created_browser = True
            attach_mode = False
        else:
            driver, created_browser, attach_mode = create_driver()

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
                    from selenium.webdriver.support import expected_conditions as EC
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
                from selenium.webdriver.support import expected_conditions as EC
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
                        cells = [c.get_text(strip=True) for c in tr.find_all(["td","th"])]
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

    try:
        if auth_dump:
            run_auth_diagnostics()
            return
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

        def process_handle(handle: str) -> None:
            print(f"[HANDLE] Starting {handle}")
            debug_log_path = os.path.join(output_dir, f"debug_log_{handle}.txt")
            html_path = os.path.join(output_dir, f"debug_html_{handle}.html")
            debug_buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(debug_buffer), contextlib.redirect_stderr(debug_buffer):
                    print(f"[DEBUG] Navigated to: {driver.current_url}")
                    print(f"[DEBUG] Processing handle: {handle}")
                    # Try multiple selectors for the search box with short waits
                    print("[STEP] Probing search box selectors...")
                    # Prefer config-driven selectors if available
                    try:
                        from webscraper.ultimate_scraper_config import (
                            SEARCH_INPUT_SELECTORS,
                            DROPDOWN_CONTAINER_SELECTORS,
                            DROPDOWN_ITEM_SELECTORS,
                            SEARCH_BUTTON_SELECTORS,
                            SHOW_HIDE_TT_SELECTORS,
                            XPATH_FALLBACKS,
                            MAX_VACUUM_LINKS,
                            MAX_SCROLL_STEPS,
                            AGGRESSIVE_SKIP_PATTERNS,
                        )
                        search_selectors = [(By.CSS_SELECTOR, s) for s in SEARCH_INPUT_SELECTORS]
                        dropdown_container_selectors = DROPDOWN_CONTAINER_SELECTORS
                        dropdown_item_selectors = DROPDOWN_ITEM_SELECTORS
                        dropdown_selector_css = ", ".join(DROPDOWN_ITEM_SELECTORS)
                        search_btn_selector = ", ".join(SEARCH_BUTTON_SELECTORS)
                        showhide_selector = ", ".join(SHOW_HIDE_TT_SELECTORS)
                        xpath_fallbacks = XPATH_FALLBACKS
                        max_vacuum_links = MAX_VACUUM_LINKS
                        max_scroll_steps = MAX_SCROLL_STEPS
                        skip_patterns = [p.lower() for p in AGGRESSIVE_SKIP_PATTERNS]
                    except Exception:
                        search_selectors = [
                            (By.CSS_SELECTOR, "input#customers"),
                            (By.CSS_SELECTOR, "input[name='customer']"),
                            (By.CSS_SELECTOR, "input[name='customer_handle']"),
                        ]
                        dropdown_container_selectors = ["ul.ui-autocomplete", "div.ui-autocomplete"]
                        dropdown_item_selectors = ["li.ui-menu-item a", "a.ui-corner-all"]
                        dropdown_selector_css = "li.ui-menu-item a, a.ui-corner-all"
                        search_btn_selector = "input[type='submit'][value*='Search'], button[type='submit']"
                        showhide_selector = "a.show_hide[rel='#slideid5']"
                        xpath_fallbacks = {"search_input": [], "dropdown_items": [], "search_button": []}
                        max_vacuum_links = 200
                        max_scroll_steps = 50
                        skip_patterns = ["new_ticket", "create", "delete", "logout"]

                    selectors = search_selectors or [
                        (By.ID, "customers"),
                        (By.NAME, "customer"),
                        (By.NAME, "customer_handle"),
                        (By.CSS_SELECTOR, "input#customers, input[name='customer'], input[name='customer_handle']"),
                    ]
                    search_box = None
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    for by, sel in selectors:
                        try:
                            search_box = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((by, sel))
                            )
                            print(f"[FOUND] Search box using {by}='{sel}'")
                            break
                        except Exception:
                            pass
                    # Try XPath fallbacks if CSS failed
                    if search_box is None:
                        for xp in xpath_fallbacks.get("search_input", []):
                            try:
                                search_box = WebDriverWait(driver, 3).until(
                                    EC.presence_of_element_located((By.XPATH, xp))
                                )
                                print(f"[FOUND] Search box via XPath='{xp}'")
                                break
                            except Exception:
                                pass
                    if search_box is None:
                        print("[WARN] No search box found. Page may require login/MFA.")
                        if allow_manual_prompts:
                            print(
                                "[ACTION REQUIRED] Complete login in the opened browser, then press Enter here to continue..."
                            )
                            try:
                                input()
                            except Exception:
                                pass
                            # Retry once after manual login
                            for by, sel in selectors:
                                try:
                                    search_box = WebDriverWait(driver, 3).until(
                                        EC.presence_of_element_located((by, sel))
                                    )
                                    print(f"[FOUND] Search box after login using {by}='{sel}'")
                                    break
                                except Exception:
                                    pass
                        else:
                            print("[WARN] Manual auth prompt skipped (auth orchestration enabled).")
                        if search_box is None:
                            # Dump all inputs to debug log to help selector discovery
                            print("[STEP] Dumping form element attributes for selector discovery...")
                            try:
                                inputs = driver.find_elements(By.CSS_SELECTOR, "input, select, textarea")
                                print(f"[DEBUG] Found {len(inputs)} form elements; dumping attributes...")
                                for i, el in enumerate(inputs):
                                    try:
                                        attrs = [
                                            ("id", el.get_attribute("id")),
                                            ("name", el.get_attribute("name")),
                                            ("type", el.get_attribute("type")),
                                            ("class", el.get_attribute("class")),
                                            ("placeholder", el.get_attribute("placeholder")),
                                        ]
                                        print("[FORM] "+"; ".join([f"{k}='{v}'" for k, v in attrs if v]))
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            print("[ERROR] Still could not find a search box; saving HTML and continuing.")

                    # Save full HTML snapshot for inspection
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print(f"[DEBUG] Saved HTML to {html_path}")
                    # If we have a search box, perform dropdown + search flow
                    if search_box is not None:
                        print("[STEP] Typing query and capturing dropdown suggestions...")
                        try:
                            # Build fielded query per landing-page help
                            query = f"company_handle:{handle}"
                            # Clear, type query
                            search_box.clear()
                            search_box.send_keys(query)
                            # Force value set in case of JS-driven inputs
                            driver.execute_script("arguments[0].value = arguments[1];", search_box, query)
                            # Dispatch input/change events to trigger listeners
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", search_box)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", search_box)
                            print(f"[INFO] Typed query: {query}")

                            # Ensure search type is set to 'Tickets' using exact id when available
                            try:
                                from selenium.webdriver.support.ui import Select
                                set_ok = False
                                try:
                                    idx = driver.find_element(By.ID, "index_to_search")
                                    Select(idx).select_by_visible_text("Tickets")
                                    # Also set via JS and dispatch change to trigger listeners
                                    driver.execute_script("arguments[0].value = 'Tickets'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", idx)
                                    print("[INFO] Search type set to 'Tickets'")
                                    set_ok = True
                                except Exception:
                                    # Fallback: scan any select elements
                                    select_elems = driver.find_elements(By.CSS_SELECTOR, "select")
                                    for sel in select_elems:
                                        try:
                                            opt_texts = [o.text.strip() for o in Select(sel).options]
                                            if any(t.lower()=="tickets" for t in opt_texts):
                                                Select(sel).select_by_visible_text("Tickets")
                                                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", sel)
                                                print("[INFO] Search type set to 'Tickets' (fallback)")
                                                set_ok = True
                                                break
                                        except Exception:
                                            continue
                                if not set_ok:
                                    print("[WARN] Could not set search type; proceeding with default")
                            except Exception:
                                print("[WARN] Search type selection failed; proceeding anyway")

                            # Wait for dropdown items to appear and capture them
                            from selenium.common.exceptions import StaleElementReferenceException
                            dropdown_items = []
                            # Force the autocomplete to open (click + slight keydown), then capture items
                            try:
                                from selenium.webdriver.common.keys import Keys
                                search_box.click()
                                # Nudge UI to open suggestions without submitting
                                search_box.send_keys(Keys.ARROW_DOWN)
                            except Exception:
                                pass
                            # Wait for dropdown container with display:block then capture items
                            for _ in range(40):  # up to ~8s
                                try:
                                    # Prefer visible container
                                    visible_menu = None
                                    try:
                                        visible_menu = driver.find_element(By.CSS_SELECTOR, "ul.ui-autocomplete[style*='display: block'], div.ui-autocomplete[style*='display: block']")
                                    except Exception:
                                        visible_menu = None
                                    if visible_menu:
                                        dropdown_items = visible_menu.find_elements(By.CSS_SELECTOR, dropdown_selector_css)
                                    else:
                                        dropdown_items = driver.find_elements(By.CSS_SELECTOR, dropdown_selector_css)
                                    container = None
                                    for cont_sel in dropdown_container_selectors:
                                        try:
                                            container = driver.find_element(By.CSS_SELECTOR, cont_sel)
                                            break
                                        except Exception:
                                            continue
                                    if container:
                                        found = []
                                        for item_sel in dropdown_item_selectors:
                                            try:
                                                found.extend(container.find_elements(By.CSS_SELECTOR, item_sel))
                                            except Exception:
                                                continue
                                        dropdown_items = found
                                    else:
                                        dropdown_items = driver.find_elements(By.CSS_SELECTOR, dropdown_selector_css)
                                    if dropdown_items:
                                        break
                                except Exception:
                                    pass
                                import time
                                time.sleep(0.2)

                            # Save dropdown debug
                            dd_path = os.path.join(output_dir, f"debug_dropdown_items_{handle}.txt")
                            with open(dd_path, "w", encoding="utf-8") as f:
                                for i, item in enumerate(dropdown_items):
                                    try:
                                        info = f"Dropdown {i+1}: text='{item.text}', href='{item.get_attribute('href')}'"
                                    except StaleElementReferenceException:
                                        info = f"Dropdown {i+1}: [STALE ELEMENT]"
                                    print(info)
                                    f.write(info+"\n")

                            # Select the first dropdown option if autocomplete appears (optional)
                            matched = False
                            try:
                                # Wait for dropdown list container to be visible
                                from selenium.webdriver.support import expected_conditions as EC
                                from selenium.webdriver.common.action_chains import ActionChains
                                # Ensure the menu is open and items are visible
                                try:
                                    WebDriverWait(driver, 8).until(
                                        EC.visibility_of_element_located((By.CSS_SELECTOR, "ul.ui-autocomplete[style*='display: block'], div.ui-autocomplete[style*='display: block']"))
                                    )
                                except Exception:
                                    pass
                                WebDriverWait(driver, 8).until(
                                    EC.visibility_of_any_elements_located((By.CSS_SELECTOR, dropdown_selector_css))
                                )
                                # Prefer the first visible, clickable item
                                first_item = None
                                for item in dropdown_items:
                                    try:
                                        if item.is_displayed():
                                            first_item = item
                                            break
                                    except Exception:
                                        continue
                                if first_item is None and dropdown_items:
                                    first_item = dropdown_items[0]
                                if first_item:
                                    # Move to element and click via JS to avoid overlay issues
                                    try:
                                        ActionChains(driver).move_to_element(first_item).pause(0.1).perform()
                                    except Exception:
                                        pass
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_item)
                                    driver.execute_script("arguments[0].click();", first_item)
                                    print(f"[INFO] Selected first dropdown item: '{first_item.text.strip()}'")
                                    matched = True
                                else:
                                    print("[WARN] No dropdown items available to select.")
                                # If still not matched, attempt XPath-based click on first item
                                if not matched:
                                    for xp in xpath_fallbacks.get("dropdown_items", []):
                                        try:
                                            xp_item = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
                                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", xp_item)
                                            driver.execute_script("arguments[0].click();", xp_item)
                                            print(f"[INFO] Selected dropdown item via XPath: {xp}")
                                            matched = True
                                            break
                                        except Exception:
                                            continue
                            except Exception as e:
                                print(f"[ERROR] Selecting dropdown item failed: {e}")
                            # If no autocomplete selection, proceed to Search click
                            if not matched:
                                print("[INFO] Proceeding without dropdown selection; will try Search click.")

                            # Click Search button regardless of dropdown selection
                            print("[STEP] Triggering Search...")
                            # Aggressive network logging disabled
                            clicked = False
                            # Direct JS click on the known hidden button id
                            try:
                                driver.execute_script("document.getElementById('submit').click();")
                                print("[INFO] Triggered document.getElementById('submit').click()")
                                clicked = True
                            except Exception:
                                pass
                            # jQuery-based click if available
                            if not clicked:
                                try:
                                    driver.execute_script("if (window.$) { $('#submit').click(); }")
                                    print("[INFO] Triggered jQuery $('#submit').click()")
                                    clicked = True
                                except Exception:
                                    pass
                            # Fallbacks via selector lookup and Enter key
                            if not clicked:
                                try:
                                    search_btn = WebDriverWait(driver, 6).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, search_btn_selector))
                                    )
                                    driver.execute_script("arguments[0].click();", search_btn)
                                    print("[INFO] Clicked Search via selector fallback")
                                    clicked = True
                                except Exception:
                                    pass
                            if not clicked:
                                try:
                                    from selenium.webdriver.common.keys import Keys
                                    search_box.send_keys(Keys.ENTER)
                                    print("[INFO] Pressed Enter in search box (fallback)")
                                    clicked = True
                                except Exception:
                                    pass

                            # Save immediate post-click snapshot and console
                            try:
                                post_html = driver.page_source
                                post_path = os.path.join(output_dir, f"post_click_{handle}.html")
                                with open(post_path, "w", encoding="utf-8") as f:
                                    f.write(post_html)
                                print(f"[DEBUG] Saved post-click snapshot to {post_path}")
                                dump_browser_console(f"post_click_{handle}")
                            except Exception:
                                pass

                            # Discover and log form details to understand navigation
                            try:
                                form = None
                                try:
                                    form = search_box.find_element(By.XPATH, "ancestor::form")
                                except Exception:
                                    form = None
                                if form:
                                    try:
                                        action = form.get_attribute("action")
                                        method = (form.get_attribute("method") or "GET").upper()
                                        inputs_in_form = form.find_elements(By.CSS_SELECTOR, "input, select")
                                        print(f"[FORM] method={method} action={action} inputs={len(inputs_in_form)}")
                                        for el in inputs_in_form:
                                            try:
                                                nm = el.get_attribute("name")
                                                id_ = el.get_attribute("id")
                                                val = el.get_attribute("value")
                                                print(f"[FIELD] name='{nm}' id='{id_}' value='{val}'")
                                            except Exception:
                                                continue
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            # Wait for results: AJAX populates #search_results with div.search_record and updates #stats
                            print("[STEP] Waiting for AJAX search results...")
                            try:
                                WebDriverWait(driver, 20).until(
                                    lambda d: (
                                        len(d.find_elements(By.CSS_SELECTOR, "#search_results .search_record")) > 0 or
                                        len(d.find_elements(By.CSS_SELECTOR, "#search_results a")) > 0 or
                                        (lambda s: isinstance(s, str) and "found" in s.lower())(d.execute_script("return (document.getElementById('stats')||{}).innerText || ''"))
                                    )
                                )
                                print("[INFO] AJAX search results detected")
                            except Exception:
                                print("[WARN] Could not confirm AJAX results; saving snapshot and continuing")

                            # Aggressive: infinite scroll to trigger lazy loading and collect all results
                            if aggressive:
                                print("[AGGR] Starting infinite scroll collector...")
                                try:
                                    import time
                                    prev_len = 0
                                    for i in range(max_scroll_steps):
                                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                        time.sleep(0.25)
                                        curr_len = len(driver.find_elements(By.CSS_SELECTOR, "#search_results .search_record, #search_results a"))
                                        if curr_len <= prev_len:
                                            # try small up-down jiggle to trigger scroll handlers
                                            driver.execute_script("window.scrollTo(0, 0);")
                                            time.sleep(0.1)
                                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                            time.sleep(0.2)
                                            curr_len = len(driver.find_elements(By.CSS_SELECTOR, "#search_results .search_record, #search_results a"))
                                            if curr_len <= prev_len:
                                                break
                                        prev_len = curr_len
                                    print(f"[AGGR] Scroll complete; collected {prev_len} result elements")
                                except Exception as e:
                                    print(f"[WARN] Infinite scroll failed: {e}")

                            # Optional deep vacuum crawl: visit internal links and save pages
                            if vacuum or aggressive:
                                print("[VACUUM] Starting internal link crawl...")
                                from urllib.parse import urlparse, urljoin
                                base_url = driver.current_url
                                parsed = urlparse(base_url)
                                origin = f"{parsed.scheme}://{parsed.netloc}"
                                # Collect links from current page HTML
                                vacuum_links = set()
                                try:
                                    page_html = driver.page_source
                                    bs4 = require_beautifulsoup()
                                    vsoup = bs4(page_html, "html.parser")
                                    for a in vsoup.find_all("a", href=True):
                                        href = as_str(a.get("href"))
                                        if not href:
                                            continue
                                        abs_href = urljoin(base_url, href)
                                        # Skip ticket creation endpoints
                                        lh = abs_href.lower()
                                        if any(sp in lh for sp in skip_patterns):
                                            continue
                                        # Internal links only (same origin or relative)
                                        if abs_href.startswith(origin):
                                            vacuum_links.add(abs_href)
                                    # Also collect JS-driven endpoints visible in network log
                                    if aggressive:
                                        try:
                                            logs = driver.execute_script("return window.__netlog || [];") or []
                                            for rec in logs:
                                                url_ = (rec or {}).get('url') or ''
                                                if url_ and url_.startswith(origin) and not any(sp in url_.lower() for sp in skip_patterns):
                                                    vacuum_links.add(url_)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                # Visit links with a practical cap
                                max_links = max_vacuum_links if aggressive else max_vacuum_links
                                visited = set()
                                for i, link in enumerate(list(vacuum_links)):
                                    if i >= max_links:
                                        print(f"[VACUUM] Reached crawl cap ({max_links}); stopping.")
                                        break
                                    if link in visited:
                                        continue
                                    visited.add(link)
                                    try:
                                        driver.execute_script("window.open(arguments[0], '_blank');", link)
                                        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
                                        new_handle = [h for h in driver.window_handles if h != driver.current_window_handle][-1]
                                        driver.switch_to.window(new_handle)
                                        WebDriverWait(driver, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                                        vac_html = driver.page_source
                                        vac_path = os.path.join(output_dir, f"vacuum_{handle}_{i+1}.html")
                                        with open(vac_path, "w", encoding="utf-8") as f:
                                            f.write(vac_html)
                                        print(f"[VACUUM] Saved {link} -> {vac_path}")
                                        # Save per-page network log too
                                        if aggressive:
                                            try:
                                                page_logs = driver.execute_script("return window.__netlog || [];") or []
                                                import json
                                                npath = os.path.join(output_dir, f"vacuum_netlog_{handle}_{i+1}.json")
                                                with open(npath, "w", encoding="utf-8") as nf:
                                                    json.dump(page_logs, nf, indent=2)
                                            except Exception:
                                                pass
                                    finally:
                                        try:
                                            driver.close()
                                        except Exception:
                                            pass
                                        try:
                                            # Switch back to original tab (first handle flow)
                                            driver.switch_to.window(driver.window_handles[0])
                                        except Exception:
                                            pass

                                # If clicking Search triggers an alert, dismiss it and retry once
                                try:
                                    from selenium.common.exceptions import TimeoutException
                                    WebDriverWait(driver, 2).until(EC.alert_is_present())
                                    alert = driver.switch_to.alert
                                    print(f"[WARN] Alert appeared after Search click: {alert.text}")
                                    alert.accept()
                                    print("[INFO] Alert dismissed; retrying Search click once.")
                                    try:
                                        search_btn = WebDriverWait(driver, 8).until(
                                            EC.element_to_be_clickable((By.CSS_SELECTOR, search_btn_selector))
                                        )
                                        search_btn.click()
                                        print("[INFO] Clicked Search button (retry)")
                                    except Exception:
                                        print("[ERROR] Retry Search click failed")
                                except TimeoutException:
                                    pass

                                # Wait for navigation or presence of company info
                                print("[STEP] Waiting for navigation/company page...")
                                page_loaded = False
                                for _ in range(30):
                                    import time
                                    time.sleep(0.2)
                                    try:
                                        if "customers.cgi" not in driver.current_url:
                                            page_loaded = True
                                            break
                                        info_box = driver.find_elements(By.CSS_SELECTOR, "div.company-info, table.company-info, #company-info")
                                        if info_box:
                                            page_loaded = True
                                            break
                                    except Exception:
                                        pass
                                if not page_loaded:
                                    print("[WARN] Company page may not have loaded; proceeding to save snapshot anyway.")

                                # Click 'Show/Hide Trouble Ticket Data' and then save/post-parse
                                print("[STEP] Expanding Trouble Ticket Data...")
                                try:
                                    showhide = WebDriverWait(driver, 10).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, showhide_selector))
                                    )
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", showhide)
                                    driver.execute_script("arguments[0].click();", showhide)
                                    print("[INFO] Clicked 'Show/Hide Trouble Ticket Data' link")
                                    import time
                                    time.sleep(0.8)
                                except Exception:
                                    # Try alternative text-based selector
                                    try:
                                        alt = driver.find_elements(By.XPATH, "//a[contains(.,'Trouble Ticket Data')] | //button[contains(.,'Trouble Ticket Data')]")
                                        if alt:
                                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", alt[0])
                                            driver.execute_script("arguments[0].click();", alt[0])
                                            print("[INFO] Clicked Show/Hide via text-based XPath")
                                            import time
                                            time.sleep(0.8)
                                        else:
                                            print("[WARN] Could not click 'Show/Hide Trouble Ticket Data' link; proceeding anyway.")
                                    except Exception:
                                        print("[WARN] Could not click 'Show/Hide Trouble Ticket Data' link; proceeding anyway.")

                                # Parse current page, then iterate pagination to collect all pages
                                def parse_current_page(save_path_prefix: str):
                                    html = driver.page_source
                                    post_path_local = os.path.join(output_dir, f"{save_path_prefix}_{handle}.html")
                                    with open(post_path_local, "w", encoding="utf-8") as f:
                                        f.write(html)
                                    print(f"[DEBUG] Saved post-search HTML to {post_path_local}")
                                    bs4 = require_beautifulsoup()
                                    soup_local = bs4(html, "html.parser")
                                    tables_local = soup_local.find_all("table")
                                    matching_rows_local = []
                                    tickets_local = []
                                    for table in tables_local:
                                        for tr in table.find_all("tr"):
                                            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                                            if any(handle in c for c in cells):
                                                matching_rows_local.append(cells)
                                            for a in tr.find_all("a", href=True):
                                                href = as_str(a.get("href"))
                                                if not href:
                                                    continue
                                                text = a.get_text(strip=True)
                                                href_l = href.lower()
                                                # Only collect existing ticket view links, not new ticket creation
                                                is_existing_ticket = (
                                                    "noc-tickets.123.net/ticket/" in href_l or
                                                    ("/ticket/" in href_l and "new_ticket" not in href_l)
                                                )
                                                if is_existing_ticket or text.isdigit():
                                                    tickets_local.append({
                                                        "id": text,
                                                        "href": href,
                                                        "row": cells
                                                    })
                                    return post_path_local, matching_rows_local, tickets_local

                                # Parse first page
                                page_index = 1
                                post_path, matching_rows, tickets = parse_current_page("debug_post_search_page1")

                                # Attempt pagination: find Next and iterate until disabled/not found
                                print("[STEP] Checking for pagination...")
                                try:
                                    # Try to use config if available
                                    try:
                                        from webscraper.ultimate_scraper_config import PAGINATION_CONTAINER_SELECTORS, PAGINATION_NEXT_SELECTORS
                                    except Exception:
                                        PAGINATION_CONTAINER_SELECTORS = ["ul.pagination", "nav.pagination", "div.pagination"]
                                        PAGINATION_NEXT_SELECTORS = [
                                            "a[aria-label='Next']",
                                            "button[aria-label='Next']",
                                            "a.page-link[rel='next']",
                                            "button.page-link[rel='next']",
                                        ]

                                    def find_next_button():
                                        # Prefer searching inside a pagination container
                                        for cont_sel in PAGINATION_CONTAINER_SELECTORS:
                                            try:
                                                container = driver.find_element(By.CSS_SELECTOR, cont_sel)
                                                for next_sel in PAGINATION_NEXT_SELECTORS:
                                                    try:
                                                        btn = container.find_element(By.CSS_SELECTOR, next_sel)
                                                        if btn and btn.is_enabled():
                                                            return btn
                                                    except Exception:
                                                        continue
                                            except Exception:
                                                continue
                                        # Fallback: global search
                                        for next_sel in PAGINATION_NEXT_SELECTORS:
                                            try:
                                                btn = driver.find_element(By.CSS_SELECTOR, next_sel)
                                                if btn and btn.is_enabled():
                                                    return btn
                                            except Exception:
                                                continue
                                        return None

                                    while True:
                                        next_btn = find_next_button()
                                        if not next_btn:
                                            print("[INFO] No pagination Next button found.")
                                            break
                                        # Check disabled state via aria-disabled or class
                                        try:
                                            aria_disabled = (next_btn.get_attribute("aria-disabled") or "").lower()
                                            classes = (next_btn.get_attribute("class") or "").lower()
                                            if aria_disabled == "true" or "disabled" in classes:
                                                print("[INFO] Next button is disabled; stopping pagination.")
                                                break
                                        except Exception:
                                            pass
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                                        driver.execute_script("arguments[0].click();", next_btn)
                                        print(f"[INFO] Clicked Next to page {page_index+1}")
                                        # Simple wait
                                        import time
                                        time.sleep(0.7)
                                        page_index += 1
                                        _, m_rows, tix = parse_current_page(f"debug_post_search_page{page_index}")
                                        matching_rows.extend(m_rows)
                                        tickets.extend(tix)
                                except Exception as e:
                                    print(f"[WARN] Pagination handling failed: {e}")

                                # Visit each ticket link to scrape details
                                ticket_details = []
                                try:
                                    from urllib.parse import urljoin
                                    base = driver.current_url
                                    original_window = driver.current_window_handle
                                    # Try to reuse cookies for ticket domain by injecting prior cookies
                                    # Derive ticket domain base from first ticket href if present
                                    ticket_base_url = None
                                    for t in tickets:
                                        href0 = t.get("href")
                                        if href0 and href0.startswith("http"):
                                            # Use scheme+host
                                            try:
                                                from urllib.parse import urlparse
                                                pu = urlparse(href0)
                                                ticket_base_url = f"{pu.scheme}://{pu.netloc}"
                                                break
                                            except Exception:
                                                pass
                                    if ticket_base_url and cookies_path:
                                        try:
                                            base_url = driver.current_url
                                            driver.get(ticket_base_url)
                                        except Exception:
                                            base_url = None
                                        load_cookies_json(driver, cookies_path)
                                        if base_url:
                                            try:
                                                driver.get(base_url)
                                            except Exception:
                                                pass

                                    # Helper: requests session from Selenium cookies for attachment downloads
                                    def build_requests_session_from_driver(base_url: str):
                                        try:
                                            import requests
                                            s = requests.Session()
                                            for c in driver.get_cookies():
                                                try:
                                                    name = c.get('name')
                                                    value = c.get('value')
                                                    if isinstance(name, str) and isinstance(value, str) and name and value:
                                                        s.cookies.set(name, value, domain=c.get('domain'), path=c.get('path'))
                                                except Exception:
                                                    pass
                                            # Basic headers
                                            s.headers.update({
                                                "User-Agent": "Mozilla/5.0 (AggressiveScraper)",
                                            })
                                            return s
                                        except Exception:
                                            return None

                                    req_session = build_requests_session_from_driver(ticket_base_url or driver.current_url)
                                    for t in tickets:
                                        href = as_str(t.get("href"))
                                        if not href:
                                            continue
                                        # Skip creation endpoints like new_ticket
                                        if "new_ticket" in href.lower():
                                            continue
                                        target = urljoin(base, href)
                                        try:
                                            # Open in new tab to preserve context
                                            driver.execute_script("window.open(arguments[0], '_blank');", target)
                                            WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
                                            new_handle = [h for h in driver.window_handles if h != original_window][-1]
                                            driver.switch_to.window(new_handle)
                                            # Basic wait for page to load
                                            WebDriverWait(driver, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                                            # If we hit a sign-in page, prompt user to complete auth once
                                            try:
                                                page_text = (driver.page_source or '').lower()
                                                curr_url = driver.current_url.lower()
                                                needs_login = any(keyword in page_text for keyword in [
                                                    'sign in', 'login', 'password', 'username'
                                                ]) or ('login' in curr_url or 'sign' in curr_url)
                                                if needs_login:
                                                    print(f"[AUTH] Ticket page requires authentication: {driver.current_url}")
                                                    print("[ACTION REQUIRED] Complete sign-in in the visible tab, then press Enter here to continue.")
                                                    try:
                                                        input()
                                                    except Exception:
                                                        pass
                                                    # Wait again for content post-auth
                                                    WebDriverWait(driver, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                                            except Exception:
                                                pass
                                            ticket_html = driver.page_source
                                            # Save raw ticket HTML
                                            safe_id = (t.get("id") or "ticket").replace("/", "_").replace(" ", "_")
                                            ticket_path = os.path.join(output_dir, f"ticket_{handle}_{safe_id}.html")
                                            with open(ticket_path, "w", encoding="utf-8") as f:
                                                f.write(ticket_html)
                                            # Parse structured fields commonly present
                                            bs4 = require_beautifulsoup()
                                            tsoup = bs4(ticket_html, 'html.parser')
                                            title = tsoup.title.string if tsoup.title else None
                                            # Extract header block "Company: ... Id: ... Subj: ..."
                                            header_text = None
                                            try:
                                                header_div = tsoup.find('div', class_=lambda c: True) or tsoup.find('body')
                                                header_text = header_div.get_text(" ", strip=True) if header_div else ""
                                            except Exception:
                                                pass
                                            # Specific fields via label proximity
                                            def find_label_value(label):
                                                # Search for the label text and return the closest following input/span text
                                                lbl = tsoup.find(lambda tag: tag.name in ['td','th','div','span','label'] and label.lower() in (tag.get_text(strip=True) or '').lower())
                                                if not lbl:
                                                    return None
                                                # Check siblings and next elements
                                                for sib in lbl.find_all_next(['input','span','div','td']):
                                                    if sib.name != 'input':
                                                        val = sib.get_text(strip=True)
                                                    else:
                                                        raw_val = sib.get('value')
                                                        if raw_val is None:
                                                            val = ""
                                                        elif isinstance(raw_val, (list, tuple)):
                                                            val = " ".join(str(x) for x in raw_val).strip()
                                                        else:
                                                            val = str(raw_val).strip()
                                                    if val:
                                                        return val
                                                return None
                                            # Common fields
                                            ticket_id = None
                                            subject = None
                                            status = find_label_value('Status')
                                            type_ = find_label_value('Type')
                                            external_id = find_label_value('External ID')
                                            born_updated = find_label_value('Born/Updated')
                                            resolved_ts = find_label_value('Resolved Timestamp')
                                            address = find_label_value('Address')
                                            # Ticket ID often appears in URL path /ticket/<id>
                                            try:
                                                from urllib.parse import urlparse
                                                pu = urlparse(driver.current_url)
                                                parts = pu.path.strip('/').split('/')
                                                if len(parts) >= 2 and parts[-2] == 'ticket':
                                                    ticket_id = parts[-1]
                                            except Exception:
                                                pass
                                            # Subject near "Subj:" marker
                                            try:
                                                subj_el = tsoup.find(string=lambda s: isinstance(s, str) and 'Subj:' in s)
                                                if subj_el:
                                                    # Subject may be after Subj: in same parent
                                                    parent_text = subj_el.parent.get_text(' ', strip=True) if subj_el and subj_el.parent else ""
                                                    subject = parent_text.split('Subj:')[-1].strip()
                                            except Exception:
                                                pass

                                            # Extract attachments (record links only)
                                            attachments = []
                                            try:
                                                from webscraper.ultimate_scraper_config import ATTACHMENT_PATTERNS
                                            except Exception:
                                                ATTACHMENT_PATTERNS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".zip", "attachment", "download"]
                                            from urllib.parse import urljoin
                                            for a in tsoup.find_all('a', href=True):
                                                href = as_str(a.get("href"))
                                                if not href:
                                                    continue
                                                text = a.get_text(strip=True)
                                                lh = href.lower()
                                                if any(p in lh for p in ATTACHMENT_PATTERNS):
                                                    abs_url = urljoin(driver.current_url, href)
                                                    att_name = text or abs_url.split('/')[-1]
                                                    att_rec = {"name": att_name, "href": abs_url, "path": None}
                                                    attachments.append(att_rec)

                                            # Aggressive: extract comments/timeline entries
                                            comments = []
                                            try:
                                                from webscraper.ultimate_scraper_config import COMMENT_CONTAINER_SELECTORS, COMMENT_ITEM_SELECTORS
                                            except Exception:
                                                COMMENT_CONTAINER_SELECTORS = [".comments", ".notes", ".activity", ".history", ".timeline"]
                                                COMMENT_ITEM_SELECTORS = ["li", "div.comment", "tr"]
                                            containers = []
                                            for sel in COMMENT_CONTAINER_SELECTORS:
                                                containers.extend(tsoup.select(sel))
                                            for cont in containers:
                                                items = []
                                                for item_sel in COMMENT_ITEM_SELECTORS:
                                                    items.extend(cont.select(item_sel))
                                                for it in items:
                                                    try:
                                                        text = it.get_text(" ", strip=True)
                                                        # Heuristics for author and timestamp
                                                        author = None
                                                        ts = None
                                                        # Look for elements with class names
                                                        name_el = it.find(class_=lambda c: c and ('author' in c or 'user' in c))
                                                        if name_el:
                                                            author = name_el.get_text(strip=True)
                                                        time_el = it.find(class_=lambda c: c and ('time' in c or 'date' in c))
                                                        if time_el:
                                                            ts = time_el.get_text(strip=True)
                                                        comments.append({"author": author, "timestamp": ts, "text": text})
                                                    except Exception:
                                                        continue
                                            ticket_details.append({
                                                "id": ticket_id or t.get("id"),
                                                "href": target,
                                                "title": title,
                                                "subject": subject,
                                                "status": status,
                                                "type": type_,
                                                "external_id": external_id,
                                                "born_updated": born_updated,
                                                "resolved_timestamp": resolved_ts,
                                                "address": address,
                                                "header_text": header_text,
                                                "raw_html_path": ticket_path,
                                                "attachments": attachments,
                                                "comments": comments,
                                            })
                                        except Exception as te:
                                            print(f"[WARN] Ticket fetch failed for {target}: {te}")
                                        finally:
                                            try:
                                                driver.close()
                                            except Exception:
                                                pass
                                            try:
                                                driver.switch_to.window(original_window)
                                            except Exception:
                                                pass
                                except Exception as e:
                                    print(f"[WARN] Ticket detail scraping encountered an error: {e}")

                                # Save aggregated results
                                try:
                                    result = {
                                        "handle": handle,
                                        "url": driver.current_url,
                                        "matching_rows": matching_rows,
                                        "tickets": tickets,
                                        "ticket_details": ticket_details,
                                        "raw_html_path": post_path,
                                        "pages": page_index,
                                    }
                                    import json
                                    out_path = os.path.join(output_dir, f"scrape_results_{handle}.json")
                                    with open(out_path, "w", encoding="utf-8") as f:
                                        json.dump(result, f, indent=2)
                                    print(f"[INFO] Saved scrape results to {out_path}")
                                except Exception as e:
                                    print(f"[ERROR] Could not write aggregated results: {e}")

                                # Also append CSV exports (aggregated and per-handle)
                                try:
                                    import csv
                                    csv_fields = [
                                        "handle","id","href","title","subject","status","type","external_id","born_updated","resolved_timestamp","address","attachments_count","comments_count"
                                    ]
                                    agg_csv = os.path.join(output_dir, "tickets_aggregated.csv")
                                    per_csv = os.path.join(output_dir, f"tickets_{handle}.csv")
                                    def write_rows(path, rows, header):
                                        exists = os.path.exists(path)
                                        with open(path, "a", newline="", encoding="utf-8") as cf:
                                            w = csv.DictWriter(cf, fieldnames=header)
                                            if not exists:
                                                w.writeheader()
                                            for r in rows:
                                                w.writerow(r)
                                    rows = []
                                    for td in ticket_details:
                                        rows.append({
                                            "handle": handle,
                                            "id": td.get("id"),
                                            "href": td.get("href"),
                                            "title": td.get("title"),
                                            "subject": td.get("subject"),
                                            "status": td.get("status"),
                                            "type": td.get("type"),
                                            "external_id": td.get("external_id"),
                                            "born_updated": td.get("born_updated"),
                                            "resolved_timestamp": td.get("resolved_timestamp"),
                                            "address": td.get("address"),
                                            "attachments_count": len(td.get("attachments", [])),
                                            "comments_count": len(td.get("comments", [])),
                                        })
                                    write_rows(agg_csv, rows, csv_fields)
                                    write_rows(per_csv, rows, csv_fields)
                                    print(f"[INFO] Appended {len(rows)} rows to CSV exports")
                                except Exception as e:
                                    print(f"[WARN] CSV export failed: {e}")
                        except Exception as e:
                            print(f"[ERROR] Dropdown/search flow failed: {e}")
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

        def is_invalid_session_error(err: Exception) -> bool:
            return "invalid session id" in str(err).lower()

        abort_run = False
        for handle in handles:
            retries = 0
            while True:
                try:
                    process_handle(handle)
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
    except KeyboardInterrupt:
        print("[WARN] Interrupted by user (Ctrl+C). Shutting down.")
    finally:
        if driver and created_browser:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    # Prefer config defaults, allow CLI overrides, and finally env overrides
    try:
        # When executed as a module (python -m webscraper.ultimate_scraper)
        from . import ultimate_scraper_config as cfg
    except Exception:
        # When executed as a plain script (python webscraper/ultimate_scraper.py),
        # ensure the project root is on sys.path, then try absolute import.
        import importlib, importlib.util, sys, os
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
    parser.add_argument("--attach", type=int, help="Attach to existing Edge debugger port (e.g. 9222)")
    parser.add_argument("--auto-attach", action="store_true", help="If attach not provided, try to attach to 127.0.0.1:9222")
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
    args = parser.parse_args()

    if args.edge_smoke_test:
        smoke_test_edge_driver()
        sys.exit(0)

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

    auth_orchestration_cfg = getattr(cfg, "AUTH_ORCHESTRATION", True)
    auth_orchestration_env = os.environ.get("SCRAPER_AUTH_ORCHESTRATION")
    auth_orchestration = auth_orchestration_cfg
    if auth_orchestration_env is not None:
        auth_orchestration = auth_orchestration_env == "1"
    if args.no_auth_orchestrator:
        auth_orchestration = False

    auth_profile_dirs = getattr(cfg, "AUTH_PROFILE_DIRS", [])
    auth_profile_env = os.environ.get("SCRAPER_AUTH_PROFILE_DIRS")
    if auth_profile_env:
        auth_profile_dirs = [item.strip() for item in auth_profile_env.split(",") if item.strip()]

    auth_cookie_files = getattr(cfg, "AUTH_COOKIE_FILES", [])
    auth_cookie_env = os.environ.get("SCRAPER_COOKIE_FILES") or os.environ.get("SCRAPER_AUTH_COOKIE_FILES")
    if auth_cookie_env:
        auth_cookie_files = [item.strip() for item in auth_cookie_env.split(",") if item.strip()]

    edge_profile_override = None
    if (args.auth_dump or args.auth_pause) and args.edge_temp_profile:
        edge_profile_override = edge_profile_dir(args)

    selenium_scrape_tickets(
        url=url,
        output_dir=out_dir,
        handles=handles,
        headless=headless,
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
    )
