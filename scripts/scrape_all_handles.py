#!/usr/bin/env python3
"""Batch scrape many handles and persist ticket history to SQLite."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webscraper.db import finish_run, init_db, record_artifact, set_run_failure_reason, start_run, upsert_handle, upsert_tickets
from webscraper.paths import tickets_db_path, runtime_profile_dir
from webscraper.run_manager import RunManager
from webscraper.utils.io import safe_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch handle scraper with SQLite persistence")
    parser.add_argument("--handles", nargs="+", help="(Legacy) Handles to scrape (supports comma/whitespace separation)")
    parser.add_argument("--handles-file", help="(Legacy) Path to newline-delimited handle file")
    parser.add_argument("--handle", help="Scrape a single handle (debug override)")
    parser.add_argument("--handles-csv", default="./123NET Admin.csv", help="CSV source of truth for handles")
    parser.add_argument(
        "--status",
        nargs="+",
        default=["production_billed", "production"],
        help="Allowed Status.1 values (comma and/or whitespace separated)",
    )
    parser.add_argument("--all-handles", action="store_true", help="Force CSV all-handles mode (default behavior)")
    parser.add_argument("--max-handles", type=int, help="Limit number of handles processed")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--db", default=str(tickets_db_path()))
    parser.add_argument("--out", default=os.path.join("webscraper", "output"))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge")

    parser.add_argument("--profile-dir")
    parser.add_argument("--profile-name")
    parser.add_argument("--auth-profile-only", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--rate-limit", type=float)
    parser.add_argument("--max-tickets", type=int)
    parser.add_argument("--scrape-ticket-details", action="store_true")
    parser.add_argument("--save-html", action="store_true")
    parser.add_argument("--save-screenshot", action="store_true")
    parser.add_argument("--dump-dom-on-fail", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--phase-logs", action="store_true")
    parser.add_argument("--attach-debugger")
    parser.add_argument("--no-profile-launch", action="store_true")
    parser.add_argument(
        "--child-extra-args",
        nargs=argparse.REMAINDER,
        default=None,
        help="Additional args appended verbatim to the child scraper command",
    )
    return parser.parse_args()


def read_handles(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    handles = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return handles


def parse_handles_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    handles: list[str] = []
    for raw in values:
        for token in re.split(r"[\s,]+", raw.strip()):
            if token:
                handles.append(token)
    return handles


def resolve_handles(args: argparse.Namespace) -> list[str]:
    explicit_handle = getattr(args, "handle", None)
    if explicit_handle:
        return [str(explicit_handle).strip().upper()]

    if getattr(args, "handles", None):
        handles = parse_handles_values(args.handles)
    elif getattr(args, "handles_file", None):
        handles = read_handles(args.handles_file)
    else:
        statuses = set(parse_handles_values(getattr(args, "status", None)))
        if not statuses:
            statuses = {"production_billed", "production"}
        handles = load_handles_from_csv(getattr(args, "handles_csv", "./123NET Admin.csv"), statuses)

    handles = [h.strip().upper() for h in handles if h and h.strip()]
    if args.max_handles is not None:
        handles = handles[: max(0, args.max_handles)]
    return handles


def _status_rank(status: str) -> int:
    normalized = (status or "").strip().lower()
    if normalized == "production_billed":
        return 2
    if normalized == "production":
        return 1
    return 0


def load_handles_from_csv(csv_path: str, allowed_statuses: set[str]) -> list[str]:
    path = Path(csv_path)
    if not path.exists():
        print(f"[ERROR] Handles CSV not found: {path}")
        return []

    best_rows: dict[str, tuple[int, int]] = {}
    statuses = {s.strip().lower() for s in allowed_statuses if s.strip()}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "Handle" not in (reader.fieldnames or []):
            print(f"[ERROR] CSV is missing required column 'Handle': {path}")
            return []
        for row_index, row in enumerate(reader, start=1):
            raw_handle = (row.get("Handle") or "").strip().upper()
            if not raw_handle:
                continue
            status = (row.get("Status.1") or "").strip().lower()
            if statuses and status not in statuses:
                continue
            candidate = (_status_rank(status), row_index)
            current = best_rows.get(raw_handle)
            if current is None or candidate[0] > current[0] or (candidate[0] == current[0] and row_index < current[1]):
                best_rows[raw_handle] = candidate

    return sorted(best_rows.keys())


def build_scraper_cmd(args: argparse.Namespace, handle: str | list[str], handle_out: Path) -> list[str]:
    handle_value = handle[0] if isinstance(handle, list) else handle
    browser = getattr(args, "browser", "edge")
    cmd = [sys.executable, "-m", "webscraper.ultimate_scraper", "--handles", str(handle_value), "--out", str(handle_out)]
    resolved_profile_dir = args.profile_dir or str(runtime_profile_dir(browser))
    passthrough_flags = {
        "--profile-dir": resolved_profile_dir,
        "--profile-name": args.profile_name,
        "--rate-limit": args.rate_limit,
        "--max-tickets": args.max_tickets,
    }
    for flag, value in passthrough_flags.items():
        if value is not None:
            cmd.extend([flag, str(value)])

    for flag in [
        "--auth-profile-only",
        "--scrape-ticket-details",
        "--save-html",
        "--save-screenshot",
        "--dump-dom-on-fail",
        "--resume",
        "--phase-logs",
        "--no-profile-launch",
    ]:
        if getattr(args, flag.lstrip("-").replace("-", "_")):
            cmd.append(flag)

    if args.show:
        cmd.append("--show")

    if args.attach_debugger:
        cmd.extend(["--attach-debugger", args.attach_debugger])
    cmd.extend(["--browser", browser])

    if args.child_extra_args:
        cmd.extend(args.child_extra_args)

    return cmd


def _write_child_failure_logs(handle_out: Path, cmd: list[str], stdout: str | None, stderr: str | None) -> None:
    (handle_out / "child_cmd.txt").write_text(subprocess.list2cmdline(cmd), encoding="utf-8")
    (handle_out / "child_stdout.txt").write_text(stdout or "", encoding="utf-8")
    (handle_out / "child_stderr.txt").write_text(stderr or "", encoding="utf-8")


def _artifact_type(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return ext or "file"


def _load_ticket_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_ticket_json_candidates(batch_out: Path) -> list[Path]:
    preferred = batch_out / "tickets_all.json"
    if preferred.exists():
        return [preferred]
    return sorted(batch_out.rglob("tickets*.json"))


def _extract_handle_ticket_map(payload: Any) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    if isinstance(payload, dict):
        if "handle" in payload and isinstance(payload.get("tickets"), list):
            handle = str(payload.get("handle") or "").strip()
            if handle:
                mapped[handle] = [row for row in payload.get("tickets", []) if isinstance(row, dict)]
            return mapped
        for handle, rows in payload.items():
            if isinstance(rows, list):
                mapped[str(handle)] = [row for row in rows if isinstance(row, dict)]
    return mapped


def _collect_per_ticket_rows(batch_out: Path, handle: str) -> list[dict[str, Any]]:
    ticket_root = batch_out / "tickets" / handle
    detail_rows: list[dict[str, Any]] = []
    if ticket_root.exists():
        for ticket_json in ticket_root.glob("*/ticket.json"):
            payload = _load_ticket_json(ticket_json)
            if isinstance(payload, dict):
                detail_rows.append(payload)
    return detail_rows


def _record_batch_artifacts(db_path: str, run_id: str, batch_out: Path, batch_handle_set: set[str]) -> None:
    for artifact in batch_out.rglob("*"):
        if not artifact.is_file():
            continue
        lower_name = artifact.name.lower()
        match = re.search(r"(?:_|^)([a-z0-9]+)(?:_|\.)", lower_name)
        handle = match.group(1).upper() if match else "_batch"
        if handle not in batch_handle_set:
            handle = "_batch"
        record_artifact(
            db_path=db_path,
            run_id=run_id,
            handle=handle,
            ticket_id="_batch",
            artifact_type=_artifact_type(artifact),
            path=str(artifact),
        )


def _batch_redirected_to_gateway(batch_out: Path) -> bool:
    for path in batch_out.glob("redirect_debug_*.json"):
        payload = _load_ticket_json(path)
        if isinstance(payload, dict) and payload.get("failure_reason") == "redirect_to_gateway":
            return True
    return False


def parseTicketsFromArtifact(handle_artifacts_path: Path, job_id: str, handle: str) -> list[dict[str, Any]]:
    tickets_path = handle_artifacts_path / "tickets_list.json"
    if not tickets_path.exists():
        raise FileNotFoundError(f"Missing artifact for job={job_id} handle={handle}: {tickets_path}")
    payload = _load_ticket_json(tickets_path)
    if isinstance(payload, dict):
        rows_payload = payload.get("tickets")
    else:
        rows_payload = payload
    if not isinstance(rows_payload, list):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        err_path = handle_artifacts_path / f"parse_error_{ts}.json"
        safe_write_json(err_path, {"schema_version": 1, "payload": payload})
        raise ValueError(f"tickets_list.json parse failure for job={job_id} handle={handle}; dumped raw to {err_path}")

    normalized: list[dict[str, Any]] = []
    for row in rows_payload:
        if not isinstance(row, dict):
            continue
        ticket_id = row.get("ticket_id") or row.get("ticket_num")
        normalized.append(
            {
                "ticket_id": str(ticket_id) if ticket_id else None,
                "handle": handle,
                "title": row.get("title") or row.get("subject"),
                "status": row.get("status"),
                "created_at": row.get("created_utc") or row.get("opened_utc"),
                "updated_at": row.get("updated_utc") or row.get("created_utc"),
                "raw_json": json.dumps(row, sort_keys=True),
                "raw_text": str(row),
                **row,
            }
        )
    return normalized


def process_batch_output(db_path: str, run_id: str, batch_out: Path, batch_handles: list[str]) -> tuple[set[str], set[str], dict[str, int]]:
    successes: set[str] = set()
    failures: set[str] = set()
    counts: dict[str, int] = {}

    all_data: dict[str, list[dict[str, Any]]] = {}
    json_candidates = _find_ticket_json_candidates(batch_out)
    for candidate in json_candidates:
        payload = _load_ticket_json(candidate)
        extracted = _extract_handle_ticket_map(payload)
        if extracted:
            for handle, rows in extracted.items():
                all_data.setdefault(handle, []).extend(rows)
            record_artifact(db_path, run_id, "_batch", "_batch", "json", str(candidate), notes="parsed_ticket_json")

    for handle in batch_handles:
        handle_tickets = all_data.get(handle, [])
        detail_rows = _collect_per_ticket_rows(batch_out, handle)
        upsert_handle(db_path, handle, "processing")
        handle_artifacts = batch_out / handle
        handle_artifacts.mkdir(parents=True, exist_ok=True)
        tickets_list_path = handle_artifacts / "tickets_list.json"
        tickets_list_payload = detail_rows if detail_rows else handle_tickets
        safe_write_json(
            tickets_list_path,
            {
                "schema_version": 1,
                "handle": handle,
                "tickets": tickets_list_payload,
            },
        )

        debug_log = handle_artifacts / "debug.log"
        debug_log.write_text(
            f"tickets_list.json exists={tickets_list_path.exists()} size={tickets_list_path.stat().st_size}\n",
            encoding="utf-8",
        )

        try:
            rows_to_store = parseTicketsFromArtifact(handle_artifacts, run_id, handle)
        except Exception as exc:
            debug_log.write_text(debug_log.read_text(encoding="utf-8") + traceback.format_exc(), encoding="utf-8")
            rows_to_store = []
            print(f"[ERROR] parse failure for {handle}: {exc}")

        inserted = upsert_tickets(db_path, run_id, handle, rows_to_store)
        counts[handle] = len(rows_to_store)

        if rows_to_store:
            upsert_handle(db_path, handle, "success")
            successes.add(handle)
        else:
            reason = f"no tickets parsed; artifacts captured at {handle_artifacts}"
            upsert_handle(db_path, handle, "failed", reason)
            failures.add(handle)
            print(f"[EVENT] handle.no_tickets handle={handle} artifacts={handle_artifacts}")

        ticket_root = batch_out / "tickets" / handle
        if ticket_root.exists():
            for artifact in ticket_root.glob("*/*"):
                if not artifact.is_file():
                    continue
                ticket_id = artifact.parent.name
                predictable = handle_artifacts / f"ticket_{ticket_id}{artifact.suffix or '.html'}"
                if not predictable.exists():
                    shutil.copy2(artifact, predictable)
                record_artifact(db_path, run_id, handle, ticket_id, _artifact_type(artifact), str(predictable))

        print(f"[INFO] Handle {handle}: parsed_rows={len(rows_to_store)} upserted={inserted}")

    _record_batch_artifacts(db_path, run_id, batch_out, set(batch_handles))
    if _batch_redirected_to_gateway(batch_out):
        set_run_failure_reason(db_path, run_id, "redirect_to_gateway")
    return successes, failures, counts


def _copy_if_exists(src: Path, dst: Path) -> str | None:
    if not src.exists() or not src.is_file():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)


def collect_contract_artifacts(run_dir: Path, batch_out: Path, handle: str) -> dict[str, str | None]:
    handle_root = run_dir / "handles" / handle
    debug = _copy_if_exists(batch_out / f"debug_log_{handle}.txt", handle_root / "debug_log.txt")
    html = _copy_if_exists(batch_out / f"handle_page_{handle}.html", handle_root / "handle_page.html")
    png = _copy_if_exists(batch_out / f"handle_page_{handle}.png", handle_root / "handle_page.png")
    probe = _copy_if_exists(batch_out / f"company_{handle}_probe.json", handle_root / "company_probe.json")
    tickets = _copy_if_exists(batch_out / handle / "tickets_list.json", handle_root / "tickets.json")
    return {
        "debug_log": str(Path(debug).relative_to(run_dir)) if debug else None,
        "handle_page_html": str(Path(html).relative_to(run_dir)) if html else None,
        "handle_page_png": str(Path(png).relative_to(run_dir)) if png else None,
        "company_probe_json": str(Path(probe).relative_to(run_dir)) if probe else None,
        "tickets_json": str(Path(tickets).relative_to(run_dir)) if tickets else None,
    }


def main() -> int:
    args = parse_args()
    handles = resolve_handles(args)
    if not handles:
        print("[ERROR] No handles found.")
        return 1

    init_db(args.db)

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root_out = Path(args.out) / run_stamp
    root_out.mkdir(parents=True, exist_ok=True)

    browser = getattr(args, "browser", "edge")
    run_manager = RunManager(source=f"scripts/scrape_all_handles.py:{browser}", handles=handles)
    run_manager.initialize()
    run_id = start_run(args.db, vars(args))

    total_successes: set[str] = set()
    total_failures: set[str] = set()

    try:
        total = len(handles)
        for idx, handle in enumerate(handles, start=1):
            handle_out = root_out / handle
            handle_out.mkdir(parents=True, exist_ok=True)
            cmd = build_scraper_cmd(args, handle, handle_out)
            print(f"[INFO] Child command: {subprocess.list2cmdline(cmd)}")

            try:
                timed_out = False
                proc: subprocess.CompletedProcess[str] | None = None
                timeout_stdout = ""
                timeout_stderr = ""
                try:
                    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.timeout_seconds)
                    if proc.stdout:
                        print(proc.stdout)
                    if proc.stderr:
                        print(proc.stderr, file=sys.stderr)
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    timeout_stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
                    timeout_stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
                    print(f"[ERROR] Handle {handle} timed out after {args.timeout_seconds}s", file=sys.stderr)

                processed = process_batch_output(args.db, run_id, handle_out, [handle])
                if len(processed) == 3:
                    successes, failures, ticket_counts = processed
                else:
                    successes, failures = processed
                    ticket_counts = {}
                total_successes.update(successes)
                total_failures.update(failures)
                artifacts = collect_contract_artifacts(root_out, handle_out, handle)
                run_manager.mark_started(handle)
                if handle in successes:
                    run_manager.update_handle(handle, "ok", None, artifacts, ticket_counts.get(handle, 0))
                    print(f"[{idx}/{total}] Handle {handle} ... OK")
                else:
                    run_manager.update_handle(handle, "failed", "no tickets parsed", artifacts, ticket_counts.get(handle, 0))
                    print(f"[{idx}/{total}] Handle {handle} ... FAIL (no tickets parsed)")

                if timed_out:
                    _write_child_failure_logs(handle_out, cmd, timeout_stdout, timeout_stderr)
                    err = f"scraper timed out after {args.timeout_seconds}s"
                    upsert_handle(args.db, handle, "failed", err)
                    total_failures.add(handle)
                    print(f"[{idx}/{total}] Handle {handle} ... FAIL ({err})")
                    continue

                if proc and proc.returncode != 0:
                    _write_child_failure_logs(handle_out, cmd, proc.stdout, proc.stderr)
                    err = f"scraper exit code {proc.returncode}"
                    upsert_handle(args.db, handle, "failed", err)
                    total_failures.add(handle)
                    print(f"[{idx}/{total}] Handle {handle} ... FAIL ({err})")
            except Exception as exc:
                err = str(exc)
                upsert_handle(args.db, handle, "failed", err)
                total_failures.add(handle)
                print(f"[{idx}/{total}] Handle {handle} ... FAIL ({err})")
                continue

    finally:
        finish_run(args.db, run_id)

    if total_successes and not total_failures:
        return 0
    if total_successes and total_failures:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
