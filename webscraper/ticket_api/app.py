from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from webscraper.ticket_api import db


DEFAULT_DB = os.path.join("webscraper", "output", "tickets.sqlite")
OUTPUT_ROOT = os.path.join("webscraper", "output")
SCRAPE_TIMEOUT_SECONDS = 1800
MAX_LOG_LINES = 300


app = FastAPI(title="Ticket History API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    handle: str = Field(min_length=1)
    mode: Literal["latest", "full"] = "latest"
    limit: int | None = Field(default=None, ge=1, le=5000)


class ScrapeBatchRequest(BaseModel):
    handles: list[str] | None = None
    mode: Literal["latest", "full"] = "latest"
    limit: int | None = Field(default=None, ge=1, le=5000)


JOB_LOGS: dict[str, list[str]] = {}
JOB_LOCK = threading.Lock()


def get_db_path() -> str:
    return os.environ.get("TICKETS_DB") or os.environ.get("TICKETS_DB_PATH", DEFAULT_DB)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_job_log(job_id: str, line: str) -> None:
    line = line.strip()
    if not line:
        return
    with JOB_LOCK:
        lines = JOB_LOGS.setdefault(job_id, [])
        lines.append(line)
        if len(lines) > MAX_LOG_LINES:
            del lines[:-MAX_LOG_LINES]


def _scraper_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key, value in os.environ.items():
        if key.startswith("SCRAPER_"):
            env[key] = value
    return env


def _run_scrape_job(job_id: str, handle: str, mode: str, limit: int | None) -> None:
    db_path = get_db_path()
    final_status = "failed"
    final_error: str | None = None
    final_result: dict[str, object] = {
        "handle": handle,
        "mode": mode,
        "limit": limit,
        "status": "failed",
        "errorType": "exception",
        "exitCode": None,
        "command": "",
        "logTail": [],
    }
    progress_completed = 0
    progress_total = 1
    started_at = _iso_now()
    db.update_scrape_job(
        db_path,
        job_id,
        status="running",
        progress_completed=0,
        progress_total=1,
        started_utc=started_at,
    )

    process: subprocess.Popen[str] | None = None
    scrape_script = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"
    command: list[str] = [
        sys.executable,
        str(scrape_script),
        "--db",
        db_path,
        "--out",
        os.path.join(str(Path(OUTPUT_ROOT).resolve()), "scrape_runs"),
        "--handles",
        handle,
    ]
    if mode == "latest":
        command.extend(["--max-tickets", str(limit or 20)])
    elif limit:
        command.extend(["--max-tickets", str(limit)])

    resolved_command = subprocess.list2cmdline(command)
    _append_job_log(job_id, f"Resolved scraper command: {resolved_command}")
    final_result["command"] = resolved_command

    try:
        if not scrape_script.exists():
            _append_job_log(job_id, f"Scrape script not found: {scrape_script}")
            final_error = "missing scrape script"
            final_result.update({
                "error": final_error,
                "errorType": "missing_script",
            })
            return

        _append_job_log(job_id, "Running scraper job")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_scraper_environment(),
        )
        assert process.stdout is not None

        def _stream_logs() -> None:
            assert process is not None and process.stdout is not None
            for line in process.stdout:
                _append_job_log(job_id, line)

        log_thread = threading.Thread(target=_stream_logs, daemon=True)
        log_thread.start()

        try:
            rc = process.wait(timeout=SCRAPE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _append_job_log(job_id, "Scrape timed out. Terminating process.")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _append_job_log(job_id, "Process did not terminate in time. Killing process.")
                process.kill()
                process.wait(timeout=5)
            final_error = "scrape timed out"
            final_result.update(
                {
                    "error": final_error,
                    "errorType": "timeout",
                    "exitCode": None,
                    "logTail": JOB_LOGS.get(job_id, [])[-40:],
                }
            )
            return

        log_thread.join(timeout=5)

        if rc != 0:
            final_error = f"Scraper exited with code {rc}"
            final_result.update(
                {
                    "error": final_error,
                    "exitCode": rc,
                    "errorType": "exit_code",
                    "logTail": JOB_LOGS.get(job_id, [])[-40:],
                }
            )
            progress_completed = 1
        else:
            final_status = "completed"
            final_result.update(
                {"status": "completed", "errorType": None, "exitCode": rc, "logTail": JOB_LOGS.get(job_id, [])[-40:]}
            )
            progress_completed = 1
    except Exception as exc:  # pragma: no cover
        _append_job_log(job_id, "Unhandled scrape exception.")
        if process is not None and process.poll() is None:
            process.terminate()
        final_error = str(exc)
        final_result.update({"error": str(exc), "errorType": "exception", "exitCode": None, "logTail": JOB_LOGS.get(job_id, [])[-40:]})
    finally:
        with JOB_LOCK:
            final_result["logTail"] = JOB_LOGS.get(job_id, [])[-40:]
        final_status = final_status if not final_error else "failed"
        final_result["status"] = final_status
        final_result.setdefault("errorType", "unknown" if final_status == "failed" else None)
        final_result.setdefault("exitCode", None)
        final_result["command"] = resolved_command
        final_result["handle"] = handle
        final_result["mode"] = mode
        final_result["limit"] = limit
        db.update_scrape_job(
            db_path,
            job_id,
            status=final_status,
            progress_completed=progress_completed,
            progress_total=progress_total,
            finished_utc=_iso_now(),
            error_message=final_error,
            result=final_result,
        )


@app.on_event("startup")
def startup() -> None:
    db.ensure_indexes(get_db_path())


@app.get("/health")
def health() -> dict[str, object]:
    db_path = get_db_path()
    stats_payload = db.get_stats(db_path)
    return {
        "status": "ok",
        "version": app.version,
        "db_path": db_path,
        "db_exists": Path(db_path).exists(),
        "last_updated_utc": stats_payload.get("last_updated_utc"),
        "stats": stats_payload,
    }


@app.get("/api/health")
def api_health() -> dict[str, object]:
    return health()


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    safe_limit = max(1, min(limit, 5000))
    handles = db.list_handle_names(get_db_path(), q=q, limit=safe_limit)
    return {"items": handles, "count": len(handles)}


@app.get("/api/handles")
def api_handles(q: str = "", limit: int = 200, offset: int = 0):
    return db.list_handles(get_db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/summary")
def api_handles_summary(
    q: str = "",
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    safe_limit = max(1, min(limit, 5000))
    return db.list_handles_summary(get_db_path(), q=q, limit=safe_limit, offset=offset)


@app.get("/api/handles/{handle}")
def api_handle_detail(handle: str):
    return handle_detail(handle)


@app.get("/handles")
def handles(search: str = "", limit: int = 50, offset: int = 0):
    return db.list_handles(get_db_path(), q=search, limit=limit, offset=offset)


@app.get("/handles/{handle}")
def handle_detail(handle: str):
    row = db.get_handle(get_db_path(), handle)
    if not row:
        raise HTTPException(status_code=404, detail="Handle not found")
    return row


@app.get("/api/handles/{handle}/tickets")
def api_handle_tickets(
    handle: str,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = Query(None, alias="from"),
    to_utc: str | None = Query(None, alias="to"),
    page: int = 1,
    pageSize: int = 50,
    sort: str = "newest",
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        page=page,
        page_size=pageSize,
        sort=sort,
    )


@app.get("/handles/{handle}/tickets")
def handle_tickets(
    handle: str,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = Query(None, alias="from"),
    to_utc: str | None = Query(None, alias="to"),
    page: int = 1,
    pageSize: int = 50,
    sort: str = "newest",
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        page=page,
        page_size=pageSize,
        sort=sort,
    )


@app.get("/api/tickets")
def api_tickets(
    handle: str | None = None,
    q: str | None = None,
    status: str | None = None,
    from_utc: str | None = Query(None, alias="from"),
    to_utc: str | None = Query(None, alias="to"),
    page: int = 1,
    pageSize: int = 50,
    sort: str = "newest",
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        page=page,
        page_size=pageSize,
        sort=sort,
    )


@app.post("/api/scrape")
def api_scrape(req: ScrapeRequest):
    handle = req.handle.strip()
    if not handle:
        raise HTTPException(status_code=400, detail="handle is required")

    if not db.handle_exists(get_db_path(), handle):
        raise HTTPException(status_code=404, detail="Handle not found")

    job_id = str(uuid.uuid4())
    created_at = _iso_now()
    db.create_scrape_job(
        get_db_path(),
        job_id=job_id,
        handle=handle,
        mode=req.mode,
        ticket_limit=req.limit,
        status="queued",
        created_utc=created_at,
    )

    worker = threading.Thread(target=_run_scrape_job, args=(job_id, handle, req.mode, req.limit), daemon=True)
    worker.start()

    return {"jobId": job_id, "status": "queued"}


@app.post("/api/scrape-batch")
def api_scrape_batch(req: ScrapeBatchRequest):
    input_handles = [h.strip() for h in (req.handles or []) if h and h.strip()]
    handles = input_handles if input_handles else db.list_all_handles(get_db_path())
    if not handles:
        raise HTTPException(status_code=404, detail="No handles found to scrape")

    known_handles = set(db.list_all_handles(get_db_path()))
    unknown = [handle for handle in handles if handle not in known_handles]
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown handles: {', '.join(sorted(set(unknown)))}")

    deduped_handles = sorted(set(handles))
    created_at = _iso_now()
    job_ids: list[str] = []

    for handle in deduped_handles:
        job_id = str(uuid.uuid4())
        db.create_scrape_job(
            get_db_path(),
            job_id=job_id,
            handle=handle,
            mode=req.mode,
            ticket_limit=req.limit,
            status="queued",
            created_utc=created_at,
        )
        worker = threading.Thread(target=_run_scrape_job, args=(job_id, handle, req.mode, req.limit), daemon=True)
        worker.start()
        job_ids.append(job_id)

    return {"jobIds": job_ids, "status": "queued"}


@app.get("/api/scrape/{job_id}")
def api_scrape_status(job_id: str):
    job = db.get_scrape_job(get_db_path(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    with JOB_LOCK:
        logs = JOB_LOGS.get(job_id, [])

    return {
        "jobId": job["job_id"],
        "status": job["status"],
        "handle": job["handle"],
        "mode": job["mode"],
        "limit": job["ticket_limit"],
        "progress": {
            "completed": job["progress_completed"],
            "total": job["progress_total"],
        },
        "logs": logs,
        "resultSummary": job.get("result"),
        "error": job.get("error_message"),
        "createdAt": job["created_utc"],
        "startedAt": job.get("started_utc"),
        "finishedAt": job.get("finished_utc"),
    }


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str, handle: str | None = None):
    return ticket(ticket_id=ticket_id, handle=handle)


@app.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(get_db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    artifacts = db.get_artifacts(get_db_path(), row["ticket_id"], row["handle"])
    row["artifacts"] = artifacts
    return row


@app.get("/stats")
def stats():
    return db.get_stats(get_db_path())


@app.get("/api/artifacts")
def api_artifact(path: str):
    return artifact(path=path)


@app.get("/artifacts")
def artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    os.environ["TICKETS_DB"] = args.db
    os.environ["TICKETS_DB_PATH"] = args.db

    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
