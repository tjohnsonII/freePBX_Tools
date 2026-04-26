#!/usr/bin/env python3
"""Scrape Manager — start, resume, monitor, and stop the webscraper.

Usage:
    python scrape_manager.py              # interactive menu
    python scrape_manager.py start        # start fresh scrape
    python scrape_manager.py resume       # resume from last checkpoint
    python scrape_manager.py monitor      # monitor latest active job
    python scrape_manager.py monitor JOB  # monitor a specific job
    python scrape_manager.py stop         # cancel active job
    python scrape_manager.py jobs         # list recent jobs
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import requests
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Config ────────────────────────────────────────────────────────────────────

_port = os.getenv("WEBSCRAPER_PORT", "8789")
API_BASE = f"http://localhost:{_port}"
POLL_INTERVAL = 2  # seconds between monitor refreshes

console = Console()

_TERMINAL_STATES = {"completed", "failed", "cancelled", "done", "error"}

# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _get(path: str, **kwargs: Any) -> Any:
    r = requests.get(f"{API_BASE}{path}", timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()


def _post(path: str, **kwargs: Any) -> Any:
    r = requests.post(f"{API_BASE}{path}", timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()


def _check_server() -> bool:
    try:
        _get("/api/health")
        return True
    except Exception:
        return False


# ── Formatting helpers ────────────────────────────────────────────────────────


def _state_markup(state: str) -> str:
    colors = {
        "running": "bold green",
        "queued": "yellow",
        "completed": "bold green",
        "done": "bold green",
        "failed": "bold red",
        "cancelled": "dim",
        "error": "bold red",
    }
    c = colors.get(state, "white")
    return f"[{c}]{state}[/]"


def _bar(done: int, total: int, width: int = 36) -> str:
    if total <= 0:
        return f"[dim]{'░' * width}[/] 0/0"
    filled = min(width, int(width * done / total))
    pct = int(100 * done / total)
    bar = f"[green]{'█' * filled}[/][dim]{'░' * (width - filled)}[/]"
    return f"{bar} {done}/{total} ({pct}%)"


def _short_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso[:19].replace("T", " ")


# ── Job fetching ──────────────────────────────────────────────────────────────


def _fetch_jobs(limit: int = 20) -> list[dict]:
    data = _get("/api/jobs")
    items = data if isinstance(data, list) else data.get("items", [])
    return items[:limit]


def _fetch_job(job_id: str) -> dict:
    return _get(f"/api/jobs/{job_id}")


def _fetch_events(job_id: str, limit: int = 25) -> list[dict]:
    data = _get(f"/api/jobs/{job_id}/events", params={"limit": limit})
    return data.get("events", []) if isinstance(data, dict) else data


def _active_job(jobs: list[dict]) -> dict | None:
    for state in ("running", "queued"):
        match = next((j for j in jobs if j.get("current_state") == state), None)
        if match:
            return match
    return None


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_start(fresh: bool = True) -> None:
    if not _check_server():
        console.print(Panel(
            "[red]API server not reachable.[/]\n\n"
            "Start it with:  [bold]bash start_client.sh[/]",
            title="Connection Error", border_style="red",
        ))
        sys.exit(1)

    payload: dict = {}

    if not fresh:
        try:
            state = _get("/api/scrape/state")
            last = state.get("last_completed_handle")
        except Exception as exc:
            console.print(f"[red]Could not read scrape state:[/] {exc}")
            sys.exit(1)

        if last:
            console.print(f"[cyan]Last completed handle:[/] [bold]{last}[/]")
            console.print(f"[dim]Updated:[/] {_short_ts(state.get('updated_utc'))}\n")
            payload = {"resume_from_handle": last}
        else:
            console.print("[yellow]No resume checkpoint found — starting from the beginning.[/]\n")

    try:
        data = _post("/api/scrape/start", json=payload)
    except requests.HTTPError as exc:
        console.print(f"[red]Start failed:[/] {exc.response.text}")
        sys.exit(1)

    job_id: str = data["job_id"]
    total: int = data.get("handles_total", 0)
    resume_from = data.get("resume_from_handle")

    lines = [f"[green]Job queued:[/] [bold]{job_id}[/]", f"Handles to scrape: [bold]{total}[/]"]
    if resume_from:
        lines.append(f"Resuming after: [cyan]{resume_from}[/]")
    lines.append("")
    lines.append(
        "[yellow]A Chrome window will open. Log in to 123.net when prompted.[/]\n"
        "[dim]The scraper will begin automatically once login is detected.[/]"
    )
    console.print(Panel("\n".join(lines), title="Scrape Started", border_style="green"))

    _monitor_job(job_id)


def cmd_monitor(job_id: str | None = None) -> None:
    if not _check_server():
        console.print("[red]API server not reachable.[/]")
        sys.exit(1)

    if job_id is None:
        try:
            jobs = _fetch_jobs()
        except Exception as exc:
            console.print(f"[red]Error fetching jobs:[/] {exc}")
            sys.exit(1)
        active = _active_job(jobs)
        if active:
            job_id = active["job_id"]
        elif jobs:
            job_id = jobs[0]["job_id"]
            console.print(f"[yellow]No active job — showing latest:[/] {job_id[:16]}...")
        else:
            console.print("[yellow]No jobs found. Run 'start' first.[/]")
            return

    _monitor_job(job_id)


def _monitor_job(job_id: str) -> None:
    console.print(f"[dim]Monitoring job:[/] {job_id}\n[dim]Press Ctrl+C to detach.[/]\n")

    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while True:
                try:
                    job = _fetch_job(job_id)
                    events = _fetch_events(job_id, limit=18)
                except Exception as exc:
                    live.update(Panel(f"[red]Fetch error:[/] {exc}", title="Monitor"))
                    time.sleep(POLL_INTERVAL)
                    continue

                live.update(_build_monitor_panel(job, events))

                state = job.get("current_state", "")
                if state in _TERMINAL_STATES:
                    break

                time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n[dim]Detached from monitor (job is still running).[/]")
        return

    state = job.get("current_state", "unknown")
    if state in ("completed", "done"):
        written = job.get("records_written", 0)
        console.print(f"\n[bold green]Scrape completed.[/] {written} handles processed.")
    elif state == "cancelled":
        console.print("\n[yellow]Job was cancelled.[/]")
    else:
        err = job.get("error_message", "")
        console.print(f"\n[bold red]Job {state}.[/]" + (f" {err}" if err else ""))


def _build_monitor_panel(job: dict, events: list[dict]) -> Panel:
    state = job.get("current_state", "unknown")
    step = job.get("current_step", "")
    done = job.get("records_written", 0) or 0
    total = job.get("records_found", 0) or 0
    err = job.get("error_message")

    # Info table
    info = Table(box=None, show_header=False, padding=(0, 1), expand=False)
    info.add_column("k", style="bold cyan", width=14)
    info.add_column("v")
    info.add_row("Status", _state_markup(state))
    info.add_row("Step", Text(step or "—", overflow="fold"))
    info.add_row("Progress", _bar(done, total))
    info.add_row("Started", _short_ts(job.get("started_at")))
    if job.get("completed_at"):
        info.add_row("Finished", _short_ts(job.get("completed_at")))
    if err:
        info.add_row("Error", f"[red]{err}[/]")

    # Login hint while waiting
    extra_lines: list[str] = []
    if state in ("queued", "running") and step and "login" in step.lower():
        extra_lines.append(
            "\n[yellow]Waiting for login.[/] Open the Chrome window and log in to 123.net."
        )
    elif state == "queued":
        extra_lines.append("\n[yellow]Waiting for browser launch...[/]")

    # Event log
    event_rows: list[str] = []
    for ev in events[-15:]:
        ts = _short_ts(ev.get("ts_utc"))
        msg = ev.get("message", "")
        level = ev.get("level", "info")
        color = {"error": "red", "warning": "yellow"}.get(level, "cyan")
        event_rows.append(f"[dim]{ts}[/]  [{color}]{msg}[/]")

    event_panel = Panel(
        "\n".join(event_rows) if event_rows else "[dim]No events yet[/]",
        title="Events",
        border_style="dim",
    )

    border = (
        "green" if state in ("completed", "done")
        else "red" if state in ("failed", "error")
        else "dim" if state == "cancelled"
        else "yellow"
    )

    body_parts: list[Any] = [info]
    if extra_lines:
        body_parts.append(Text.from_markup("".join(extra_lines)))
    body_parts.append(event_panel)

    return Panel(
        Group(*body_parts),
        title=f"[bold]Scrape Monitor[/]  [dim]{job.get('job_id', '')[:16]}[/]",
        border_style=border,
    )


def cmd_stop() -> None:
    if not _check_server():
        console.print("[red]API server not reachable.[/]")
        sys.exit(1)

    try:
        jobs = _fetch_jobs()
        active = _active_job(jobs)
        if not active:
            console.print("[yellow]No active scrape job found.[/]")
            return
        job_id = active["job_id"]
        state = active.get("current_state", "")
        done = active.get("records_written", 0) or 0
        total = active.get("records_found", 0) or 0
        console.print(f"Active job: [bold]{job_id[:16]}[/]... ({state}, {done}/{total} handles)")
    except Exception as exc:
        console.print(f"[red]Error fetching jobs:[/] {exc}")
        sys.exit(1)

    confirm = input("Cancel this job? [y/N] ").strip().lower()
    if confirm != "y":
        console.print("[dim]Aborted.[/]")
        return

    try:
        data = _post("/api/scrape/cancel", json={"job_id": job_id})
        console.print(f"[cyan]{data.get('message', 'Cancel requested.')}[/]")
        console.print("[dim]The job will stop after the current handle finishes.[/]")
    except requests.HTTPError as exc:
        console.print(f"[red]Cancel failed:[/] {exc.response.text}")


def cmd_jobs() -> None:
    if not _check_server():
        console.print("[red]API server not reachable.[/]")
        sys.exit(1)

    try:
        jobs = _fetch_jobs(20)
    except Exception as exc:
        console.print(f"[red]Error fetching jobs:[/] {exc}")
        sys.exit(1)

    if not jobs:
        console.print("[yellow]No jobs found.[/]")
        return

    t = Table(title="Recent Scrape Jobs", box=box.ROUNDED, show_lines=False)
    t.add_column("Job ID", style="dim", width=10)
    t.add_column("State", width=12)
    t.add_column("Progress", width=12)
    t.add_column("Step", width=28)
    t.add_column("Started", width=18)
    t.add_column("Finished", width=18)

    for j in jobs:
        jid = (j.get("job_id") or "")[:8]
        state = j.get("current_state") or "unknown"
        done = j.get("records_written", 0) or 0
        total = j.get("records_found", 0) or 0
        step = (j.get("current_step") or "")[:26]
        started = _short_ts(j.get("started_at"))
        finished = _short_ts(j.get("completed_at"))
        progress = f"{done}/{total}" if total else "—"
        t.add_row(jid, _state_markup(state), progress, step, started, finished)

    console.print(t)


# ── Interactive menu ──────────────────────────────────────────────────────────


def cmd_interactive() -> None:
    while True:
        console.rule("[bold cyan]Scrape Manager[/]")
        console.print("  [bold]1[/]  Start new scrape")
        console.print("  [bold]2[/]  Resume from last checkpoint")
        console.print("  [bold]3[/]  Monitor active job")
        console.print("  [bold]4[/]  Stop active job")
        console.print("  [bold]5[/]  List recent jobs")
        console.print("  [bold]q[/]  Quit\n")

        try:
            choice = input("Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if choice == "1":
            cmd_start(fresh=True)
        elif choice == "2":
            cmd_start(fresh=False)
        elif choice == "3":
            try:
                job_id_input = input("Job ID (leave blank for latest): ").strip() or None
            except (EOFError, KeyboardInterrupt):
                job_id_input = None
            cmd_monitor(job_id_input)
        elif choice == "4":
            cmd_stop()
        elif choice == "5":
            cmd_jobs()
        elif choice in ("q", "quit", "exit"):
            console.print("[dim]Goodbye.[/]")
            break
        else:
            console.print("[yellow]Unknown option.[/]")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scrape_manager",
        description="Manage FreePBX webscraper jobs from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("start", help="Start a fresh scrape job")
    sub.add_parser("resume", help="Resume from the last saved checkpoint")

    p_monitor = sub.add_parser("monitor", help="Monitor a scrape job (default: latest active)")
    p_monitor.add_argument("job_id", nargs="?", default=None, help="Job ID to monitor")

    sub.add_parser("stop", help="Cancel the active scrape job (graceful — finishes current handle)")
    sub.add_parser("jobs", help="List recent scrape jobs")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(fresh=True)
    elif args.command == "resume":
        cmd_start(fresh=False)
    elif args.command == "monitor":
        cmd_monitor(args.job_id)
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "jobs":
        cmd_jobs()
    else:
        cmd_interactive()


if __name__ == "__main__":
    main()
