from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from webscraper_manager import __version__

try:
    import typer

    TYPER_AVAILABLE = True
except Exception:
    typer = None  # type: ignore[assignment]
    TYPER_AVAILABLE = False

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:
    Console = Any  # type: ignore[assignment]
    RICH_AVAILABLE = False

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DOCTOR_ISSUES = 10
EXIT_TEST_FAILED = 30

TITLE_TEXT = "FreePBX Webscraper Manager"
SUBTITLE_TEXT = "CLI manager for status, tests, auth, API checks, and start/stop"


@dataclass
class AppState:
    quiet: bool = False
    verbose: bool = False
    in_menu: bool = False
    pure_json_mode: bool = False
    clear_screen: bool = False
    use_preferred_python: bool = True


@dataclass
class Finding:
    check: str
    ok: bool
    details: str
    warning: bool = False


@dataclass
class TestStep:
    name: str
    ok: bool
    details: str
    duration_ms: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_repo_root() -> Path:
    return _repo_root()


def get_preferred_python(repo_root: Path) -> Path:
    first_choice = repo_root / ".venv-webscraper" / "Scripts" / "python.exe"
    if first_choice.is_file():
        return first_choice

    second_choice = repo_root / "webscraper" / ".venv" / "Scripts" / "python.exe"
    if second_choice.is_file():
        return second_choice

    return Path(sys.executable)


def is_running_in_preferred_python(repo_root: Path) -> bool:
    current = Path(sys.executable).resolve()
    preferred = get_preferred_python(repo_root).resolve()
    return current == preferred


def get_runtime_python(state: AppState, repo_root: Path) -> Path:
    if state.use_preferred_python:
        return get_preferred_python(repo_root)
    return Path(sys.executable)


def ensure_manager_dirs() -> tuple[Path, Path, Path]:
    root = find_repo_root()
    manager_dir = root / ".webscraper_manager"
    logs_dir = manager_dir / "logs"
    day_dir = logs_dir / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    return manager_dir, logs_dir, day_dir


def run_subprocess(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def write_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def get_console(state: AppState) -> Console | None:
    if not RICH_AVAILABLE:
        return None
    no_color = bool(os.environ.get("NO_COLOR"))
    return Console(no_color=no_color)


def should_print_banner(state: AppState, json_out: bool, is_help: bool) -> bool:
    if is_help:
        return False
    if state.in_menu:
        return False
    if state.quiet:
        return False
    if json_out:
        return False
    return True


def print_banner(console: Console | None) -> None:
    if console is None:
        print(f"{TITLE_TEXT}\n{SUBTITLE_TEXT}")
        return

    title = Text(TITLE_TEXT, style="bold cyan", justify="center")
    subtitle = Text(SUBTITLE_TEXT, style="bright_black", justify="center")
    banner_body = Text.assemble(title, "\n", subtitle)
    console.print(
        Panel(
            banner_body,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 3),
            expand=True,
        )
    )


def print_findings_table(console: Console | None, findings: list[Finding]) -> None:
    if console is None:
        for finding in findings:
            if finding.warning:
                symbol = "WARN"
            else:
                symbol = "OK" if finding.ok else "FAIL"
            print(f"{finding.check}: {symbol} - {finding.details}")
        return

    table = Table(title="Doctor Checks", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Details", style="bright_black")

    for finding in findings:
        if finding.warning:
            status = "[yellow]⚠️ WARN[/yellow]"
        else:
            status = "[green]✅ OK[/green]" if finding.ok else "[red]❌ FAIL[/red]"
        table.add_row(finding.check, status, finding.details)

    console.print(table)


def print_result_panel(console: Console | None, ok: bool, message: str) -> None:
    if console is None:
        print(message)
        return

    final_style = "green" if ok else "red"
    console.print(
        Panel(
            Text(message, justify="center", style=f"bold {final_style}"),
            border_style=final_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _doctor_findings() -> list[Finding]:
    root = _repo_root()
    current_python = Path(sys.executable)
    preferred_python = get_preferred_python(root)
    matches_preferred = is_running_in_preferred_python(root)
    run_hint = f"Run with: {preferred_python} -m webscraper_manager ..."

    return [
        Finding("repo_root", root.exists(), f"Found repo root at {root}"),
        Finding(
            "webscraper_dir",
            (root / "webscraper").is_dir(),
            f"Expected directory: {root / 'webscraper'}",
        ),
        Finding(
            "webscraper_requirements",
            (root / "webscraper" / "requirements.txt").is_file(),
            f"Expected file: {root / 'webscraper' / 'requirements.txt'}",
        ),
        Finding("current_python", True, str(current_python)),
        Finding("preferred_python", True, str(preferred_python)),
        Finding(
            "python_matches_preferred",
            ok=matches_preferred,
            details="Current interpreter matches preferred interpreter" if matches_preferred else run_hint,
            warning=not matches_preferred,
        ),
    ]


def run_doctor(console: Console | None, state: AppState, json_out: bool) -> tuple[int, dict[str, Any] | None]:
    findings = _doctor_findings()
    ok = all(finding.ok or finding.warning for finding in findings)
    payload = {
        "ok": ok,
        "findings": [asdict(finding) for finding in findings],
    }

    if json_out:
        print(json.dumps(payload, indent=2))
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), payload

    if state.quiet:
        print("Doctor checks passed." if ok else "Doctor checks found issues.")
        return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None

    print_findings_table(console, findings)

    if state.verbose:
        message = f"Verbose: evaluated {len(findings)} checks from root: {_repo_root()}"
        if console is None:
            print(message)
        else:
            console.print(f"[bright_black]{message}[/bright_black]")

    final_message = "Doctor checks passed." if ok else "Doctor checks found issues."
    print_result_panel(console, ok, final_message)
    return (EXIT_OK if ok else EXIT_DOCTOR_ISSUES), None


def _make_step(name: str, ok: bool, details: str, started: float) -> TestStep:
    return TestStep(name=name, ok=ok, details=details, duration_ms=int((time.time() - started) * 1000))


def _is_port_open(host: str, port: int, timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _run_scraper_cli_probe(root: Path, timeout: int, python_exe: Path) -> tuple[bool, str, list[str]]:
    webscraper_dir = root / "webscraper"
    commands_tried: list[str] = []
    if (webscraper_dir / "__main__.py").is_file():
        cmd = [str(python_exe), "-m", "webscraper", "--help"]
        commands_tried.append(" ".join(cmd))
        rc, out, err = run_subprocess(cmd, cwd=root, timeout=timeout)
        text = (out + "\n" + err).strip()
        return rc == 0, text or "Ran webscraper module --help", commands_tried

    if (webscraper_dir / "ultimate_scraper.py").is_file():
        dry_cmd = [str(python_exe), "ultimate_scraper.py", "--dry-run"]
        help_cmd = [str(python_exe), "ultimate_scraper.py", "--help"]
        for cmd in (dry_cmd, help_cmd):
            commands_tried.append(" ".join(cmd))
            rc, out, err = run_subprocess(cmd, cwd=webscraper_dir, timeout=timeout)
            text = (out + "\n" + err).strip()
            if rc == 0:
                return True, text or f"Ran {' '.join(cmd[1:])}", commands_tried

        return False, "webscraper CLI probe failed for --dry-run/--help", commands_tried

    return True, "No webscraper CLI module detected; skipped", commands_tried


def _select_pytest_cwd(root: Path) -> Path:
    webscraper_dir = root / "webscraper"
    if webscraper_dir.is_dir():
        if (webscraper_dir / "tests").is_dir():
            return webscraper_dir
        if (webscraper_dir / "pyproject.toml").is_file() or (webscraper_dir / "pytest.ini").is_file():
            return webscraper_dir
    return root


def _run_pytest_step(path: str | None, timeout: int, python_exe: Path) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    root = find_repo_root()
    commands: list[str] = []
    cmd = [str(python_exe), "-m", "pytest", "-q"]
    if path:
        cmd.append(path)
    commands.append(" ".join(cmd))

    cwd = _select_pytest_cwd(root)
    try:
        rc, out, err = run_subprocess(cmd, cwd=cwd, timeout=timeout)
        ok = rc == 0
        details = (out + "\n" + err).strip() or f"pytest finished rc={rc}"
        step = _make_step("pytest", ok, details, started)
        return step, details, commands
    except FileNotFoundError:
        step = _make_step("pytest", False, "Python executable not found for pytest", started)
        return step, step.details, commands
    except subprocess.TimeoutExpired:
        step = _make_step("pytest", False, f"pytest timed out after {timeout}s", started)
        return step, step.details, commands


def _run_import_probe_step(timeout: int, python_exe: Path, root: Path) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    modules = ["selenium", "requests", "bs4", "lxml"]
    commands: list[str] = []
    cmd = [
        str(python_exe),
        "-c",
        (
            "import importlib,sys; "
            f"mods={modules!r}; "
            "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
            "print('missing=' + ','.join(missing)); "
            "sys.exit(0 if not missing else 1)"
        ),
    ]
    commands.append(" ".join(cmd))
    try:
        rc, out, err = run_subprocess(cmd, cwd=root, timeout=timeout)
    except subprocess.TimeoutExpired:
        step = _make_step("python dependency imports", False, f"Dependency probe timed out after {timeout}s", started)
        return step, step.details, commands

    missing_line = next((line for line in out.splitlines() if line.startswith("missing=")), "missing=")
    missing_values = missing_line.split("=", 1)[1].strip()
    if rc == 0:
        details = "All required imports ok"
        return _make_step("python dependency imports", True, details, started), details, commands

    details = f"Missing imports: {missing_values}" if missing_values else (out + "\n" + err).strip() or f"Dependency probe failed rc={rc}"
    return _make_step("python dependency imports", False, details, started), details, commands


def _run_smoke_steps(timeout: int, verbose: bool, python_exe: Path) -> tuple[list[TestStep], list[str], list[str]]:
    root = find_repo_root()
    steps: list[TestStep] = []
    logs: list[str] = [f"[python] using {python_exe}"]
    commands: list[str] = []

    started = time.time()
    findings = _doctor_findings()
    ok = all(f.ok or f.warning for f in findings)
    details = "; ".join(f"{f.check}={'warn' if f.warning else ('ok' if f.ok else 'fail')}" for f in findings)
    steps.append(_make_step("doctor", ok, details, started))
    logs.append(f"[doctor] {details}")

    dep_step, dep_details, dep_commands = _run_import_probe_step(timeout=timeout, python_exe=python_exe, root=root)
    steps.append(dep_step)
    commands.extend(dep_commands)
    logs.append(f"[deps] {dep_details}")

    started = time.time()
    cli_ok, cli_details, cli_commands = _run_scraper_cli_probe(root, timeout=timeout, python_exe=python_exe)
    commands.extend(cli_commands)
    steps.append(_make_step("webscraper CLI probe", cli_ok, cli_details, started))
    logs.append(f"[cli-probe] {cli_details}")

    started = time.time()
    if _is_port_open("127.0.0.1", 8787):
        cmd = [
            str(python_exe),
            "-c",
            (
                "import urllib.request; "
                "u=urllib.request.urlopen('http://127.0.0.1:8787/api/events/latest?limit=1', timeout=5); "
                "print(u.status)"
            ),
        ]
        commands.append(" ".join(cmd))
        try:
            rc, out, err = run_subprocess(cmd, cwd=root, timeout=min(timeout, 10))
            api_ok = rc == 0
            api_details = (out + "\n" + err).strip() or "API probe completed"
        except subprocess.TimeoutExpired:
            api_ok = False
            api_details = "API probe timed out"
    else:
        api_ok = True
        api_details = "Port 8787 closed; API probe skipped"
    steps.append(_make_step("api reachability (optional)", api_ok, api_details, started))
    logs.append(f"[api] {api_details}")

    if verbose:
        logs.append("[verbose] smoke steps complete")

    return steps, logs, commands


def _run_scraper_sanity_step(timeout: int, python_exe: Path) -> tuple[TestStep, str, list[str]]:
    started = time.time()
    root = find_repo_root()
    webscraper_dir = root / "webscraper"
    commands: list[str] = []

    if not (webscraper_dir / "ultimate_scraper.py").is_file():
        step = _make_step("scraper sanity run", True, "ultimate_scraper.py not found; skipped", started)
        return step, step.details, commands

    cmd = [str(python_exe), "ultimate_scraper.py", "--dry-run"]
    commands.append(" ".join(cmd))
    try:
        rc, out, err = run_subprocess(cmd, cwd=webscraper_dir, timeout=timeout)
        if rc != 0:
            help_cmd = [str(python_exe), "ultimate_scraper.py", "--help"]
            commands.append(" ".join(help_cmd))
            rc, out, err = run_subprocess(help_cmd, cwd=webscraper_dir, timeout=timeout)
        ok = rc == 0
        details = (out + "\n" + err).strip() or f"scraper sanity finished rc={rc}"
        return _make_step("scraper sanity run", ok, details, started), details, commands
    except subprocess.TimeoutExpired:
        step = _make_step("scraper sanity run", False, f"scraper sanity timed out after {timeout}s", started)
        return step, step.details, commands


def _format_test_summary(steps: list[TestStep], total_ms: int, log_path: Path, pure_json_mode: bool) -> str:
    payload = {
        "ok": all(step.ok for step in steps),
        "steps": [asdict(step) for step in steps],
        "duration_ms": total_ms,
        "log_file": str(log_path),
    }
    if pure_json_mode:
        return json.dumps(payload, indent=2)

    lines = ["", "Test summary:"]
    for step in steps:
        symbol = "✅ PASS" if step.ok else "❌ FAIL"
        lines.append(f"- {symbol} {step.name} ({step.duration_ms}ms)")
        lines.append(f"  {step.details}")
    lines.append(f"Total duration: {total_ms}ms")
    lines.append(f"Log file: {log_path}")
    return "\n".join(lines)


def _run_test_smoke(state: AppState, timeout: int) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_smoke_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)

    log_lines: list[str] = [f"command: test smoke --timeout {timeout}", f"python: {python_exe}"]

    try:
        steps, logs, commands = _run_smoke_steps(timeout=timeout, verbose=state.verbose, python_exe=python_exe)
        log_lines.extend(f"subprocess: {cmd}" for cmd in commands)
        log_lines.extend(logs)
    except Exception as exc:
        details = f"Unhandled error in smoke test: {exc}"
        if state.verbose:
            details = f"{details}\n{traceback.format_exc()}"
        steps = [TestStep(name="smoke test execution", ok=False, details=details, duration_ms=0)]
        log_lines.append(details)

    total_ms = int((time.time() - started) * 1000)
    log_lines.append("\n" + _format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=False))
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(_format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=state.pure_json_mode))

    ok = all(step.ok for step in steps)
    return (EXIT_OK if ok else EXIT_TEST_FAILED), steps, log_path


def _run_test_pytest(state: AppState, timeout: int, path: str | None = None) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_pytest_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)

    log_lines: list[str] = [f"command: test pytest --timeout {timeout} path={path or ''}".strip(), f"python: {python_exe}"]

    step, details, commands = _run_pytest_step(path=path, timeout=timeout, python_exe=python_exe)
    log_lines.extend(f"subprocess: {cmd}" for cmd in commands)
    log_lines.append(details)

    total_ms = int((time.time() - started) * 1000)
    steps = [step]
    log_lines.append("\n" + _format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=False))
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(_format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=state.pure_json_mode))

    return (EXIT_OK if step.ok else EXIT_TEST_FAILED), steps, log_path


def _run_test_all(state: AppState, timeout: int, keep_going: bool, pytest_path: str | None = None) -> tuple[int, list[TestStep], Path]:
    started = time.time()
    _, _, day_dir = ensure_manager_dirs()
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = day_dir / f"test_all_{timestamp}.log"
    root = find_repo_root()
    python_exe = get_runtime_python(state, root)

    steps: list[TestStep] = []
    log_lines: list[str] = [f"command: test all --timeout {timeout} --keep-going={keep_going}", f"python: {python_exe}"]

    smoke_steps, smoke_logs, smoke_commands = _run_smoke_steps(timeout=min(timeout, 30), verbose=state.verbose, python_exe=python_exe)
    steps.extend(smoke_steps)
    log_lines.extend(f"subprocess: {cmd}" for cmd in smoke_commands)
    log_lines.extend(smoke_logs)

    failed = any(not step.ok for step in smoke_steps)

    root = find_repo_root()
    has_tests = (root / "tests").is_dir() or (root / "webscraper" / "tests").is_dir()
    should_try_pytest = has_tests

    if should_try_pytest and (keep_going or not failed):
        pytest_step, pytest_details, pytest_commands = _run_pytest_step(path=pytest_path, timeout=timeout, python_exe=python_exe)
        steps.append(pytest_step)
        log_lines.extend(f"subprocess: {cmd}" for cmd in pytest_commands)
        log_lines.append(pytest_details)
        failed = failed or (not pytest_step.ok)
    elif not should_try_pytest:
        steps.append(TestStep(name="pytest", ok=True, details="No tests folder detected; skipped", duration_ms=0))

    if keep_going or not failed:
        sanity_step, sanity_details, sanity_commands = _run_scraper_sanity_step(timeout=min(timeout, 45), python_exe=python_exe)
        steps.append(sanity_step)
        log_lines.extend(f"subprocess: {cmd}" for cmd in sanity_commands)
        log_lines.append(sanity_details)
        failed = failed or (not sanity_step.ok)

    total_ms = int((time.time() - started) * 1000)
    log_lines.append("\n" + _format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=False))
    write_log(log_path, "\n".join(log_lines) + "\n")

    if not state.quiet:
        print(_format_test_summary(steps, total_ms=total_ms, log_path=log_path, pure_json_mode=state.pure_json_mode))

    return (EXIT_OK if not failed else EXIT_TEST_FAILED), steps, log_path


def run_version(console: Console | None, state: AppState) -> None:
    if state.quiet:
        print(__version__)
        return
    if console is None:
        print(__version__)
        return
    console.print(
        Panel(
            Text(f"webscraper_manager {__version__}", justify="center", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def _set_flag_from_source(ctx: Any, name: str, value: bool) -> bool | None:
    try:
        source = ctx.get_parameter_source(name)
        if source is not None and source.name != "DEFAULT":
            return value
    except Exception:
        if value:
            return value
    return None


def _clear_screen(state: AppState) -> None:
    if not state.clear_screen:
        return
    if os.name == "nt":
        os.system("cls")
        return
    os.system("clear")


def _read_line(prompt: str) -> str:
    return input(prompt).strip().lower()


def _confirm_quit() -> bool:
    try:
        answer = _read_line("Quit? [y/N] ")
    except KeyboardInterrupt:
        print()
        return False
    return answer in {"y", "yes"}


def render_menu(console: Console | None, state: AppState) -> None:
    _clear_screen(state)
    print_banner(console)
    clear_status = "ON" if state.clear_screen else "OFF"
    pure_json_status = "ON" if state.pure_json_mode else "OFF"
    preferred_status = "ON" if state.use_preferred_python else "OFF"
    root = find_repo_root()
    runtime_python = get_runtime_python(state, root)
    preferred_match = "YES" if runtime_python.resolve() == get_preferred_python(root).resolve() else "NO"

    if console is None:
        print(f"\nToggles: pure_json_mode: {pure_json_status} | clear: {clear_status} | use_preferred_python: {preferred_status}")
        print("\nMenu")
        print("[1] Doctor (normal)")
        print("[2] Doctor (quiet)")
        print("[3] Doctor (global quiet before command)")
        print("[4] Doctor (json)")
        print("[5] Version")
        print("[6] Test Run (smoke)")
        print("[7] Full Test Run (all)")
        print("[8] Pytest")
        print("[r] Refresh")
        print(f"[t] Toggle pure JSON mode (currently {pure_json_status})")
        print(f"[p] Toggle use preferred python (currently {preferred_status})")
        print("[q] Quit")
        print(f"\npython: {runtime_python.name} (preferred: {preferred_match})")
        return

    table = Table(title="Menu", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Option", justify="center", no_wrap=True)
    table.add_column("Command", style="white", no_wrap=True)
    table.add_column("Description", style="bright_black")
    table.caption = f"pure_json_mode: {pure_json_status} | clear: {clear_status} | use_preferred_python: {preferred_status}"
    table.add_row("1", "Doctor (normal)", "Same as: doctor")
    table.add_row("2", "Doctor (quiet)", "Same as: doctor --quiet")
    table.add_row("3", "Doctor (global quiet before command)", "Same as: --quiet doctor")
    table.add_row("4", "Doctor (json)", "Same as: doctor --json")
    table.add_row("5", "Version", "Same as: --version")
    table.add_row("6", "Test Run (smoke)", "Same as: test smoke")
    table.add_row("7", "Full Test Run (all)", "Same as: test all")
    table.add_row("8", "Pytest", "Same as: test pytest")
    table.add_row("r", "Refresh", "Redraw the menu")
    table.add_row("t", "Toggle pure JSON mode", f"Currently: {pure_json_status}")
    table.add_row("p", "Toggle use preferred python", f"Currently: {preferred_status}")
    table.add_row("q", "Quit", "Exit menu (with confirmation)")
    console.print(table)
    console.print(f"[bright_black]python: {runtime_python.name} (preferred: {preferred_match})[/bright_black]")


def _run_menu_action(console: Console | None, state: AppState, choice: str) -> int:
    if choice == "1":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "2":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "3":
        action_state = AppState(
            quiet=True,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _ = run_doctor(console, action_state, json_out=False)
        return code
    if choice == "4":
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        if not state.pure_json_mode:
            print("Running: doctor --json")
        code, _ = run_doctor(console, action_state, json_out=True)
        return code
    if choice == "5":
        action_state = AppState(
            quiet=state.quiet,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        run_version(console, action_state)
        return EXIT_OK
    if choice == "6":
        if not state.pure_json_mode:
            print("Running: test smoke")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_smoke(action_state, timeout=30)
        return code
    if choice == "7":
        if not state.pure_json_mode:
            print("Running: test all")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_all(action_state, timeout=300, keep_going=False)
        return code
    if choice == "8":
        if not state.pure_json_mode:
            print("Running: test pytest")
        action_state = AppState(
            quiet=False,
            verbose=state.verbose,
            in_menu=True,
            pure_json_mode=state.pure_json_mode,
            clear_screen=state.clear_screen,
            use_preferred_python=state.use_preferred_python,
        )
        code, _, _ = _run_test_pytest(action_state, timeout=300, path=None)
        return code
    return EXIT_USAGE


def pause_for_user() -> None:
    print()
    print("Press Enter to return to menu…")
    try:
        if not sys.stdin.isatty():
            print("(No interactive stdin; returning to menu in 2s...)")
            time.sleep(2)
            return
        input()
    except EOFError:
        print("(No interactive stdin; returning to menu in 2s...)")
        time.sleep(2)
    except KeyboardInterrupt:
        print()
        return


def run_menu(state: AppState) -> int:
    state.in_menu = True
    console = get_console(state)

    while True:
        render_menu(console, state)
        try:
            choice = _read_line("\nSelect an option [1-8, r, t, p, q]: ")
        except KeyboardInterrupt:
            print()
            continue

        if choice == "r":
            continue

        if choice == "t":
            state.pure_json_mode = not state.pure_json_mode
            mode = "ON" if state.pure_json_mode else "OFF"
            print(f"pure_json_mode: {mode}")
            continue

        if choice == "p":
            state.use_preferred_python = not state.use_preferred_python
            mode = "ON" if state.use_preferred_python else "OFF"
            print(f"use_preferred_python: {mode}")
            continue

        if choice == "q":
            if _confirm_quit():
                return EXIT_OK
            continue

        if choice not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
            print("Invalid selection. Enter 1, 2, 3, 4, 5, 6, 7, 8, r, t, p, or q.")
            continue

        try:
            _run_menu_action(console, state, choice)
        except KeyboardInterrupt:
            if not state.pure_json_mode:
                print("Canceled.")
            continue

        pause_for_user()


def _build_state_from_ctx(ctx: Any, quiet: bool, verbose: bool, use_preferred_python: bool = True) -> AppState:
    state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()

    quiet_override = _set_flag_from_source(ctx, "quiet", quiet)
    verbose_override = _set_flag_from_source(ctx, "verbose", verbose)
    preferred_override = _set_flag_from_source(ctx, "use_preferred_python", use_preferred_python)

    if quiet_override is not None:
        state.quiet = quiet_override
    if verbose_override is not None:
        state.verbose = verbose_override
    if preferred_override is not None:
        state.use_preferred_python = preferred_override
    return state


if TYPER_AVAILABLE:
    app = typer.Typer(help="Manage webscraper workflows", no_args_is_help=True)
    test_app = typer.Typer(help="Run webscraper test suites", no_args_is_help=True)

    def _version_callback(value: bool) -> None:
        if not value:
            return
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        raise typer.Exit(EXIT_OK)

    @app.callback(invoke_without_command=False)
    def _root(
        ctx: typer.Context,
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output (no banner)."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
        use_preferred_python: bool = typer.Option(
            True,
            "--use-preferred-python/--no-use-preferred-python",
            help="Use preferred webscraper venv interpreter for subprocess actions.",
        ),
    ) -> None:
        del version
        if ctx.resilient_parsing:
            return
        ctx.obj = AppState(quiet=quiet, verbose=verbose, use_preferred_python=use_preferred_python)

    @app.command()
    def doctor(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Output JSON only."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        json_override = _set_flag_from_source(ctx, "json_output", json_output)
        use_json = bool(json_override) if json_override is not None else json_output

        if should_print_banner(state, json_out=use_json, is_help=False):
            print_banner(get_console(state))

        code, _ = run_doctor(get_console(state), state, json_out=use_json)
        if code:
            raise typer.Exit(code)

    @test_app.command("smoke")
    def test_smoke(
        ctx: typer.Context,
        timeout: int = typer.Option(30, "--timeout", min=1, help="Timeout in seconds for smoke checks."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_smoke(state, timeout=timeout)
        raise typer.Exit(code)

    @test_app.command("pytest")
    def test_pytest(
        ctx: typer.Context,
        path: str | None = typer.Option(None, "--path", help="Optional pytest path selection."),
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for pytest run."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_pytest(state, timeout=timeout, path=path)
        raise typer.Exit(code)

    @test_app.command("all")
    def test_all(
        ctx: typer.Context,
        timeout: int = typer.Option(300, "--timeout", min=1, help="Timeout in seconds for full test run."),
        keep_going: bool = typer.Option(False, "--keep-going", help="Continue running steps after failures."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        code, _, _ = _run_test_all(state, timeout=timeout, keep_going=keep_going, pytest_path=None)
        raise typer.Exit(code)

    app.add_typer(test_app, name="test")

    @app.command()
    def menu(
        ctx: typer.Context,
        clear_screen: bool = typer.Option(
            False,
            "--clear",
            "--clear-screen",
            help="Clear the screen at the start of each menu render.",
        ),
        no_clear: bool = typer.Option(False, "--no-clear", help="Do not clear the screen between menu draws."),
        quiet: bool = typer.Option(False, "--quiet", help="Minimal output for menu actions."),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
    ) -> None:
        state = _build_state_from_ctx(ctx, quiet=quiet, verbose=verbose, use_preferred_python=True)
        state.clear_screen = bool(clear_screen and not no_clear)
        code = run_menu(state)
        if code:
            raise typer.Exit(code)


def _argparse_fallback(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])

    root = argparse.ArgumentParser(prog="webscraper_manager", description="Manage webscraper workflows")
    root.add_argument("--version", action="store_true", help="Show version and exit")
    root.add_argument("--use-preferred-python", action=argparse.BooleanOptionalAction, default=True, help="Use preferred webscraper venv interpreter for subprocess actions")

    subparsers = root.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Run doctor checks")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only")
    doctor_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    doctor_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    menu_parser = subparsers.add_parser("menu", help="Open interactive menu")
    menu_parser.add_argument("--clear", "--clear-screen", action="store_true", dest="clear_screen", help="Clear the screen when drawing the menu")
    menu_parser.add_argument("--no-clear", action="store_true", help="Do not clear the screen")
    menu_parser.add_argument("--quiet", action="store_true", help="Minimal output for menu actions")
    menu_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    test_parser = subparsers.add_parser("test", help="Run test workflows")
    test_subparsers = test_parser.add_subparsers(dest="test_command")

    smoke_parser = test_subparsers.add_parser("smoke", help="Run smoke tests")
    smoke_parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    smoke_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    smoke_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    all_parser = test_subparsers.add_parser("all", help="Run full test suite")
    all_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    all_parser.add_argument("--keep-going", action="store_true", help="Continue despite failures")
    all_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    all_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    pytest_parser = test_subparsers.add_parser("pytest", help="Run pytest")
    pytest_parser.add_argument("--path", type=str, default=None, help="Optional pytest path")
    pytest_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    pytest_parser.add_argument("--quiet", action="store_true", help="Minimal output")
    pytest_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    root.add_argument("--quiet", action="store_true", help="Minimal output")
    root.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = root.parse_args(argv)

    if args.version:
        run_version(get_console(AppState(quiet=True)), AppState(quiet=True))
        return EXIT_OK

    if args.command == "menu":
        state = AppState(
            quiet=bool(args.quiet),
            verbose=bool(args.verbose),
            clear_screen=bool(args.clear_screen and not args.no_clear),
            use_preferred_python=bool(args.use_preferred_python),
        )
        return run_menu(state)

    if args.command == "doctor":
        state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
        if should_print_banner(state, json_out=bool(args.json_output), is_help=False):
            print_banner(get_console(state))
        code, _ = run_doctor(get_console(state), state, json_out=bool(args.json_output))
        return code

    if args.command == "test":
        if args.test_command == "smoke":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_smoke(state, timeout=int(args.timeout))
            return code
        if args.test_command == "all":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_all(state, timeout=int(args.timeout), keep_going=bool(args.keep_going), pytest_path=None)
            return code
        if args.test_command == "pytest":
            state = AppState(quiet=bool(args.quiet), verbose=bool(args.verbose), use_preferred_python=bool(args.use_preferred_python))
            code, _, _ = _run_test_pytest(state, timeout=int(args.timeout), path=args.path)
            return code
        test_parser.print_help()
        return EXIT_USAGE

    root.print_help()
    return EXIT_USAGE if argv else EXIT_OK


def main() -> None:
    argv = sys.argv[1:]
    if TYPER_AVAILABLE:
        app()
        return

    try:
        raise SystemExit(_argparse_fallback(argv))
    except KeyboardInterrupt:
        raise


if __name__ == "__main__":
    main()

# Test commands
# python -m webscraper_manager menu --no-clear
# python -m webscraper_manager doctor --quiet
# python -m webscraper_manager test smoke
# python -m webscraper_manager test all
# python -m webscraper_manager test pytest
# python -m webscraper_manager --version
