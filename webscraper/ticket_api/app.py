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


def _run_scrape_job(job_id: str, handle: str, mode: str, limit: int | None) -> None:
    db_path = get_db_path()
    started_at = _iso_now()
    db.update_scrape_job(
        db_path,
        job_id,
        status="running",
        progress_completed=0,
        progress_total=1,
        started_utc=started_at,
    )

    out_dir = str(Path(OUTPUT_ROOT).resolve())
    scrape_script = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"

    command = [
        sys.executable,
        str(scrape_script),
        "--db",
        db_path,
        "--out",
        os.path.join(out_dir, "scrape_runs"),
        "--handles",
        handle,
    ]
    if mode == "latest":
        command.extend(["--max-tickets", str(limit or 20)])
    elif limit:
        command.extend(["--max-tickets", str(limit)])

    _append_job_log(job_id, "Running scraper job.")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None

        for line in process.stdout:
            _append_job_log(job_id, line)

        rc = process.wait(timeout=SCRAPE_TIMEOUT_SECONDS)
        if rc != 0:
            db.update_scrape_job(
                db_path,
                job_id,
                status="failed",
                progress_completed=1,
                progress_total=1,
                finished_utc=_iso_now(),
                error_message=f"Scraper exited with code {rc}",
                result={"exitCode": rc, "handle": handle, "mode": mode, "limit": limit},
            )
        else:
            db.update_scrape_job(
                db_path,
                job_id,
                status="completed",
                progress_completed=1,
                progress_total=1,
                finished_utc=_iso_now(),
                result={"exitCode": rc, "handle": handle, "mode": mode, "limit": limit},
            )
    except subprocess.TimeoutExpired:
        _append_job_log(job_id, "Scrape timed out.")
        db.update_scrape_job(
            db_path,
            job_id,
            status="failed",
            progress_completed=0,
            progress_total=1,
            finished_utc=_iso_now(),
            error_message="scrape timed out",
            result={"error": "scrape timed out", "handle": handle, "mode": mode, "limit": limit},
        )
    except Exception as exc:  # pragma: no cover
        _append_job_log(job_id, "Unhandled scrape exception.")
        db.update_scrape_job(
            db_path,
            job_id,
            status="failed",
            progress_completed=0,
            progress_total=1,
            finished_utc=_iso_now(),
            error_message=str(exc),
            result={"error": str(exc), "handle": handle, "mode": mode, "limit": limit},
        )


@app.on_event("startup")
def startup() -> None:
    db.ensure_indexes(get_db_path())


@app.get("/health")
def health() -> dict[str, object]:
    db_path = get_db_path()
    stats_payload = db.get_stats(db_path)
    return {"status": "ok", "db_path": db_path, **stats_payload}


@app.get("/api/handles")
def api_handles(q: str = "", limit: int = 200, offset: int = 0):
    return db.list_handles(get_db_path(), q=q, limit=limit, offset=offset)


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

    known_handles = set(db.list_all_handles(get_db_path()))
    if handle not in known_handles:
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
