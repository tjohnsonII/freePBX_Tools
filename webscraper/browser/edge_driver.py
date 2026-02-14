import os
import json
import time
import urllib.request
from datetime import datetime
from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from selenium import webdriver

PROFILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "edge_profile_tmp"))


def _validate_path(label: str, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return path
    print(f"[WARN] {label} not found at '{path}'. Falling back to auto-detect.")
    return None

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

    def kill_edge_processes(edge_kill_before: bool = True) -> None:
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
            return "msedge.exe" in names or "msedgedriver.exe" in names
        if os.name == "nt":
            import subprocess

            try:
                output = subprocess.check_output(["tasklist"], text=True, errors="ignore").lower()
            except Exception:
                return False
            return "msedge.exe" in output or "msedgedriver.exe" in output
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
            kill_edge_processes(edge_kill_before)
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

    def kill_edge_processes(edge_kill_before: bool = True) -> None:
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
            return "msedge.exe" in names or "msedgedriver.exe" in names
        if os.name == "nt":
            import subprocess

            try:
                output = subprocess.check_output(["tasklist"], text=True, errors="ignore").lower()
            except Exception:
                return False
            return "msedge.exe" in output or "msedgedriver.exe" in output
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
            kill_edge_processes(edge_kill_before)
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


def _edge_processes_exist() -> bool:
    try:
        import psutil  # type: ignore

        names = {str((p.info.get("name") or "")).lower() for p in psutil.process_iter(["name"])}
        return "msedge.exe" in names or "msedgedriver.exe" in names
    except Exception:
        pass
    if os.name == "nt":
        import subprocess

        try:
            output = subprocess.check_output(["tasklist"], text=True, errors="ignore").lower()
            return "msedge.exe" in output or "msedgedriver.exe" in output
        except Exception:
            return False
    return True


def kill_edge_processes(edge_kill_before: bool = True) -> None:
    if not edge_kill_before:
        return
    if os.name != "nt":
        print("[INFO] --edge-kill-before ignored on non-Windows platform.")
        return
    import subprocess

    for proc in ("msedge.exe", "msedgedriver.exe"):
        subprocess.run(["taskkill", "/F", "/IM", proc], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


__all__ = [
    "EdgeStartupError",
    "edge_binary_path",
    "create_edge_driver",
    "kill_edge_processes",
    "probe_edge_debugger",
    "edge_debug_targets",
    "switch_to_target_tab",
]
