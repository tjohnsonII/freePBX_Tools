from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    handles: list[str] = Field(default_factory=list)
    mode: Literal["latest", "full"] = "latest"
    maxTickets: int | None = Field(default=None, ge=1, le=5000)


@dataclass
class ScrapeJob:
    job_id: str
    handles: list[str]
    mode: str
    max_tickets: int | None
    status: str = "queued"
    progress: dict[str, int] = field(default_factory=lambda: {"completed": 0, "total": 0})
    logs: list[str] = field(default_factory=list)
    result_summary: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None


JOB_STORE: dict[str, ScrapeJob] = {}
JOB_LOCK = threading.Lock()


def get_db_path() -> str:
    return os.environ.get("TICKETS_DB") or os.environ.get("TICKETS_DB_PATH", DEFAULT_DB)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_job_log(job: ScrapeJob, line: str) -> None:
    line = line.strip()
    if not line:
        return
    job.logs.append(line)
    if len(job.logs) > MAX_LOG_LINES:
        del job.logs[:-MAX_LOG_LINES]


def _run_scrape_job(job: ScrapeJob) -> None:
    job.status = "running"
    job.started_at = _iso_now()
    job.progress = {"completed": 0, "total": len(job.handles)}

    db_path = get_db_path()
    out_dir = str(Path(OUTPUT_ROOT).resolve())

    command = [
        sys.executable,
        "-m",
        "webscraper.ultimate_scraper_legacy",
        "--db",
        db_path,
        "--out",
        out_dir,
        "--handles",
        *job.handles,
    ]
    if job.mode == "latest":
        command.extend(["--max-tickets", str(job.max_tickets or 20)])
    elif job.max_tickets:
        command.extend(["--max-tickets", str(job.max_tickets)])

    _append_job_log(job, f"Running: {' '.join(command)}")

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
            _append_job_log(job, line)
            if "handle=" in line and "PHASE" in line:
                job.progress["completed"] = min(job.progress["completed"] + 1, job.progress["total"])

        rc = process.wait(timeout=SCRAPE_TIMEOUT_SECONDS)
        if rc != 0:
            job.status = "failed"
            job.result_summary = {"exitCode": rc}
        else:
            job.status = "completed"
            job.result_summary = {
                "exitCode": rc,
                "handles": job.handles,
                "mode": job.mode,
                "maxTickets": job.max_tickets,
            }
    except subprocess.TimeoutExpired:
        job.status = "failed"
        job.result_summary = {"error": "scrape timed out"}
        _append_job_log(job, "Scrape timed out.")
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.result_summary = {"error": str(exc)}
        _append_job_log(job, f"Unhandled scrape exception: {exc}")
    finally:
        job.finished_at = _iso_now()


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
    limit: int = 100,
    offset: int = 0,
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        limit=limit,
        offset=offset,
    )


@app.get("/handles/{handle}/tickets")
def handle_tickets(
    handle: str,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = Query(None, alias="from"),
    to_utc: str | None = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0,
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        limit=limit,
        offset=offset,
    )


@app.post("/api/scrape")
def api_scrape(req: ScrapeRequest):
    handles = [h.strip() for h in req.handles if h.strip()]
    if not handles:
        handles = db.list_all_handles(get_db_path())
    if not handles:
        raise HTTPException(status_code=400, detail="No handles to scrape")

    job = ScrapeJob(
        job_id=str(uuid.uuid4()),
        handles=handles,
        mode=req.mode,
        max_tickets=req.maxTickets,
    )
    with JOB_LOCK:
        JOB_STORE[job.job_id] = job

    worker = threading.Thread(target=_run_scrape_job, args=(job,), daemon=True)
    worker.start()

    return {"jobId": job.job_id, "status": job.status}


@app.get("/api/scrape/{job_id}")
def api_scrape_status(job_id: str):
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "jobId": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "logs": job.logs,
        "resultSummary": job.result_summary,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
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
