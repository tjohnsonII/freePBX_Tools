#!/usr/bin/env python3
"""Batch scrape many handles and persist ticket history to SQLite."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webscraper.db import (
    export_tickets_by_handle,
    finish_run,
    get_handle_state,
    init_db,
    mark_handle_attempt,
    mark_handle_error,
    mark_handle_success,
    record_artifact,
    set_run_failure_reason,
    start_run,
    upsert_handle,
    upsert_tickets,
)
from webscraper.handles_loader import load_handles_from_csv
from webscraper.paths import tickets_db_path, runtime_profile_dir
from webscraper.run_manager import RunManager
from webscraper.utils.io import safe_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch handle scraper with SQLite persistence")
    parser.add_argument("--handles", nargs="+", help="Optional explicit handles (comma/whitespace separated)")
    parser.add_argument("--handles-file", help="(Legacy) Path to newline-delimited handle file")
    parser.add_argument("--handle", help="Scrape a single handle (debug override)")
    parser.add_argument("--handles-csv", default="webscraper/123NET Admin.csv", help="CSV source of truth for handles")
    parser.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    parser.add_argument("--full", action="store_true", help="Shorthand for --mode full")
    parser.add_argument("--dry-run", action="store_true", help="Load handles and print a quick summary, then exit")
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
    args = parser.parse_args()
    if args.full:
        args.mode = "full"
    return args


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
        handles = [str(explicit_handle)]
    elif getattr(args, "handles", None):
        handles = parse_handles_values(args.handles)
    elif getattr(args, "handles_file", None):
        handles = read_handles(args.handles_file)
    else:
        handles = load_handles_from_csv(getattr(args, "handles_csv", "webscraper/123NET Admin.csv"))

    normalized: list[str] = []
    seen: set[str] = set()
    for handle in handles:
        value = handle.strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    if args.max_handles is not None:
        normalized = normalized[: max(0, args.max_handles)]
    return normalized


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    random_part = os.urandom(3).hex()
    return f"{stamp}_{random_part}"


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _first_run_cutoff() -> str:
    return _iso_utc(datetime.now(timezone.utc) - timedelta(days=90)) or ""


def _max_updated(rows: list[dict[str, Any]]) -> str | None:
    latest: datetime | None = None
    for row in rows:
        updated = _parse_utc(row.get("updated_at") or row.get("updated_utc") or row.get("updated"))
        if updated and (latest is None or updated > latest):
            latest = updated
    return _iso_utc(latest)


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
            handle = str(payload.get("handle") or "").strip().upper()
            if handle:
                mapped[handle] = [row for row in payload.get("tickets", []) if isinstance(row, dict)]
            return mapped
        for handle, rows in payload.items():
            if isinstance(rows, list):
                mapped[str(handle).strip().upper()] = [row for row in rows if isinstance(row, dict)]
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
                "subject": row.get("subject") or row.get("title"),
                "status": row.get("status"),
                "created_utc": row.get("created_utc") or row.get("opened_utc"),
                "updated_utc": row.get("updated_utc") or row.get("created_utc"),
                "url": row.get("url") or row.get("ticket_url"),
                "raw_json": json.dumps(row, sort_keys=True),
                **row,
            }
        )
    return normalized


def process_batch_output(
    db_path: str,
    run_id: str,
    batch_out: Path,
    batch_handles: list[str],
    *,
    since_cutoff: str | None = None,
) -> tuple[set[str], set[str], dict[str, dict[str, int | str | None]]]:
    successes: set[str] = set()
    failures: set[str] = set()
    stats: dict[str, dict[str, int | str | None]] = {}

    cutoff_dt = _parse_utc(since_cutoff)
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

        tickets_list_payload = detail_rows if detail_rows else handle_tickets
        safe_write_json(
            handle_artifacts / "tickets_list.json",
            {"schema_version": 1, "handle": handle, "tickets": tickets_list_payload},
        )

        try:
            parsed_rows = parseTicketsFromArtifact(handle_artifacts, run_id, handle)
        except Exception as exc:
            (handle_artifacts / "debug.log").write_text(traceback.format_exc(), encoding="utf-8")
            parsed_rows = []
            print(f"[ERROR] parse failure for {handle}: {exc}")

        seen = len(parsed_rows)
        filtered_rows: list[dict[str, Any]] = []
        skipped = 0
        for row in parsed_rows:
            updated_dt = _parse_utc(row.get("updated_utc") or row.get("updated_at") or row.get("updated"))
            if cutoff_dt and updated_dt and updated_dt <= cutoff_dt:
                skipped += 1
                continue
            filtered_rows.append(row)

        upserted = upsert_tickets(db_path, run_id, handle, filtered_rows)
        if parsed_rows:
            upsert_handle(db_path, handle, "success")
            successes.add(handle)
        else:
            reason = f"no tickets parsed; artifacts captured at {handle_artifacts}"
            upsert_handle(db_path, handle, "failed", reason)
            failures.add(handle)

        stats[handle] = {
            "seen": seen,
            "processed": len(filtered_rows),
            "upserted": upserted,
            "skipped": skipped,
            "max_updated_utc": _max_updated(filtered_rows),
        }

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

    _record_batch_artifacts(db_path, run_id, batch_out, set(batch_handles))
    if _batch_redirected_to_gateway(batch_out):
        set_run_failure_reason(db_path, run_id, "redirect_to_gateway")
    return successes, failures, stats


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


def _resolve_since_for_handle(args: argparse.Namespace, db_path: str, handle: str) -> str | None:
    if args.mode == "full":
        return None
    state = get_handle_state(db_path, handle)
    if state and state.get("last_max_updated_utc"):
        return str(state["last_max_updated_utc"])
    return _first_run_cutoff()


def _write_final_tickets_json(db_path: str, output_root: Path, run_id: str) -> Path:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_utc": _iso_utc(datetime.now(timezone.utc)),
        "handles": export_tickets_by_handle(db_path),
    }
    target = output_root / "tickets_all.json"
    safe_write_json(target, payload)
    return target


def main() -> int:
    args = parse_args()
    handles = resolve_handles(args)
    if args.dry_run:
        print(f"count={len(handles)}")
        print(f"first_10={handles[:10]}")
        return 0
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

    run_token = make_run_id()
    run_id = start_run(args.db, {**vars(args), "run_token": run_token})

    total_successes: set[str] = set()
    total_failures: set[str] = set()

    try:
        total = len(handles)
        for idx, handle in enumerate(handles, start=1):
            since = _resolve_since_for_handle(args, args.db, handle)
            mark_handle_attempt(args.db, handle)
            print(f"Handle {idx}/{total}: {handle} (since={since or 'FULL'})")

            batch_out = root_out / f"batch_{idx:03d}"
            batch_out.mkdir(parents=True, exist_ok=True)
            cmd = build_scraper_cmd(args, handle, batch_out)

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

                successes, failures, ticket_stats = process_batch_output(
                    args.db,
                    run_id,
                    batch_out,
                    [handle],
                    since_cutoff=since,
                )
                total_successes.update(successes)
                total_failures.update(failures)

                stats = ticket_stats.get(handle, {"seen": 0, "processed": 0, "upserted": 0, "skipped": 0, "max_updated_utc": None})
                print(
                    f"seen={stats['seen']}, processed={stats['processed']}, upserted={stats['upserted']}, skipped={stats['skipped']}"
                )

                artifacts = collect_contract_artifacts(root_out, batch_out, handle)
                run_manager.mark_started(handle)
                if handle in successes:
                    run_manager.update_handle(handle, "ok", None, artifacts, int(stats.get("processed", 0)))
                    mark_handle_success(
                        args.db,
                        handle,
                        run_id=run_id,
                        max_updated_utc=str(stats.get("max_updated_utc") or "") or None,
                        seen_count=int(stats.get("seen", 0)),
                        upserted_count=int(stats.get("upserted", 0)),
                    )
                else:
                    run_manager.update_handle(handle, "failed", "no tickets parsed", artifacts, int(stats.get("processed", 0)))
                    mark_handle_error(args.db, handle, "no tickets parsed")

                if timed_out:
                    _write_child_failure_logs(batch_out, cmd, timeout_stdout, timeout_stderr)
                    err = f"scraper timed out after {args.timeout_seconds}s"
                    upsert_handle(args.db, handle, "failed", err)
                    mark_handle_error(args.db, handle, err)
                    total_failures.add(handle)
                    continue

                if proc and proc.returncode != 0:
                    _write_child_failure_logs(batch_out, cmd, proc.stdout, proc.stderr)
                    err = f"scraper exit code {proc.returncode}"
                    upsert_handle(args.db, handle, "failed", err)
                    mark_handle_error(args.db, handle, err)
                    total_failures.add(handle)
            except Exception as exc:
                err = str(exc)
                upsert_handle(args.db, handle, "failed", err)
                mark_handle_error(args.db, handle, err)
                total_failures.add(handle)
                print(f"[{idx}/{total}] Handle {handle} ... FAIL ({err})")
                continue

    finally:
        finish_run(args.db, run_id)

    all_json = _write_final_tickets_json(args.db, Path(args.out), run_id)
    print(f"[INFO] Wrote consolidated tickets JSON: {all_json}")

    if total_successes and not total_failures:
        return 0
    if total_successes and total_failures:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
