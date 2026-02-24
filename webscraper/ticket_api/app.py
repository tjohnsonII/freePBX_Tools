from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from webscraper.lib.db_path import get_tickets_db_path
from webscraper.ticket_api import db

OUTPUT_ROOT = os.path.join("webscraper", "output")
ARTIFACT_ROOT = os.path.join(OUTPUT_ROOT, "artifacts")
SCRAPE_TIMEOUT_SECONDS = 1800

app = FastAPI(title="Ticket History API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class ScrapeRequest(BaseModel):
    mode: Literal["all", "handle", "ticket"] = "handle"
    handle: str | None = None
    ticketId: str | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)
    dryRun: bool = False


@dataclass
class QueueJob:
    job_id: str
    payload: ScrapeRequest


JOB_QUEUE: "queue.Queue[QueueJob]" = queue.Queue()
JOB_EVENTS: dict[str, list[dict[str, Any]]] = {}
JOB_EVENT_LOCK = threading.Lock()


def db_path() -> str:
    return get_tickets_db_path()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(msg: str, request_id: str | None = None, job_id: str | None = None) -> None:
    rid = f" requestId={request_id}" if request_id else ""
    jid = f" jobId={job_id}" if job_id else ""
    print(f"[{_iso_now()}]{rid}{jid} {msg}", flush=True)


def emit_job_event(job_id: str, level: str, event: str, message: str, data: dict[str, Any] | None = None) -> None:
    payload = {"ts": _iso_now(), "level": level, "event": event, "message": message, "data": data or {}}
    with JOB_EVENT_LOCK:
        JOB_EVENTS.setdefault(job_id, []).append(payload)
        JOB_EVENTS[job_id] = JOB_EVENTS[job_id][-500:]
    db.add_scrape_event(db_path(), job_id, payload["ts"], level, event, message, payload["data"])
    _log(f"{event}: {message}", job_id=job_id)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    _log(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)", request_id=request_id)
    response.headers["X-Request-Id"] = request_id
    return response


def _build_command(job: QueueJob) -> tuple[list[str], str, list[str]]:
    req = job.payload
    out_dir = str((Path(ARTIFACT_ROOT) / job.job_id).resolve())
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"
    cmd = [sys.executable, str(script), "--db", db_path(), "--out", out_dir]
    handles: list[str] = []
    if req.mode == "all":
        cmd += ["--handles-file", str((Path(__file__).resolve().parents[2] / "webscraper" / "output" / "all_handles.txt").resolve())]
    elif req.mode == "handle":
        if not req.handle:
            raise HTTPException(status_code=400, detail="handle is required for mode=handle")
        handles = [req.handle.strip()]
        cmd += ["--handles", req.handle.strip()]
    elif req.mode == "ticket":
        if not req.handle or not req.ticketId:
            raise HTTPException(status_code=400, detail="handle and ticketId are required for mode=ticket")
        handles = [req.handle.strip()]
        cmd += ["--handles", req.handle.strip(), "--max-tickets", str(req.limit or 50)]
    if req.limit and req.mode != "ticket":
        cmd += ["--max-tickets", str(req.limit)]
    if req.dryRun:
        cmd += ["--child-extra-args", "--dry-run"]
    return cmd, out_dir, handles


def _job_worker() -> None:
    while True:
        queued = JOB_QUEUE.get()
        job_id = queued.job_id
        req = queued.payload
        try:
            cmd, out_dir, _ = _build_command(queued)
            db.update_scrape_job(db_path(), job_id, status="running", progress_completed=0, progress_total=1, started_utc=_iso_now())
            emit_job_event(job_id, "info", "job.started", "Scrape job started", {"command": cmd, "artifactsPath": out_dir})
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=SCRAPE_TIMEOUT_SECONDS)
            if proc.stdout:
                for line in proc.stdout.splitlines()[-100:]:
                    emit_job_event(job_id, "info", "scrape.stdout", line)
            if proc.stderr:
                for line in proc.stderr.splitlines()[-100:]:
                    emit_job_event(job_id, "warn", "scrape.stderr", line)

            status = "completed" if proc.returncode == 0 else "failed"
            err = None if proc.returncode == 0 else f"scraper exit code {proc.returncode}"
            summary = {"returncode": proc.returncode, "artifactsPath": out_dir}
            if req.mode == "ticket" and req.ticketId:
                hit = db.get_ticket(db_path(), req.ticketId, req.handle)
                if not hit:
                    status = "failed"
                    err = f"ticket {req.ticketId} not parsed from artifacts at {out_dir}"
                    emit_job_event(job_id, "error", "ticket.missing", err, {"ticketId": req.ticketId, "path": out_dir})
            db.update_scrape_job(db_path(), job_id, status=status, progress_completed=1, progress_total=1, finished_utc=_iso_now(), error_message=err, result=summary)
            emit_job_event(job_id, "info", "job.finished", status, {"error": err})
        except Exception as exc:
            db.update_scrape_job(db_path(), job_id, status="failed", progress_completed=1, progress_total=1, finished_utc=_iso_now(), error_message=str(exc), result={"error": str(exc)})
            emit_job_event(job_id, "error", "job.exception", str(exc))
        finally:
            JOB_QUEUE.task_done()


@app.on_event("startup")
def startup() -> None:
    db.ensure_indexes(db_path())
    with db.get_conn(db_path()) as conn:
        pragmas = {
            "journal_mode": conn.execute("PRAGMA journal_mode;").fetchone()[0],
            "synchronous": conn.execute("PRAGMA synchronous;").fetchone()[0],
            "busy_timeout": conn.execute("PRAGMA busy_timeout;").fetchone()[0],
        }
    stats = db.get_stats(db_path())
    _log(f"DB path: {db_path()}")
    _log(f"SQLite PRAGMA: {json.dumps(pragmas)}")
    _log(f"DB OK: handles={stats['total_handles']} tickets={stats['total_tickets']}")
    threading.Thread(target=_job_worker, daemon=True).start()


@app.get("/api/debug/db")
def api_debug_db():
    return db.get_debug_db_payload(db_path())


@app.get("/api/debug/last-run")
def api_debug_last_run():
    latest = db.get_latest_scrape_job(db_path())
    if not latest:
        return {"job": None, "events": []}
    events = db.get_scrape_events(db_path(), latest["job_id"], limit=50)
    return {"job": latest, "events": events}


@app.get("/api/handles")
def api_handles(q: str = "", limit: int = 200, offset: int = 0):
    return db.list_handles(db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    items = db.list_handle_names(db_path(), q=q, limit=limit)
    return {"items": items, "count": len(items)}


@app.get("/api/handles/{handle}/tickets")
def api_handle_tickets(handle: str, limit: int = 50, status: str = "any"):
    return db.list_tickets(db_path(), handle=handle, page=1, page_size=limit, status=status)


@app.post("/api/scrape")
def api_scrape(req: ScrapeRequest):
    if req.mode in {"handle", "ticket"} and req.handle and not db.handle_exists(db_path(), req.handle):
        raise HTTPException(status_code=404, detail="Handle not found")
    job_id = str(uuid.uuid4())
    db.create_scrape_job(db_path(), job_id=job_id, handle=req.handle, mode=req.mode, ticket_limit=req.limit, status="queued", created_utc=_iso_now(), ticket_id=req.ticketId)
    JOB_QUEUE.put(QueueJob(job_id=job_id, payload=req))
    emit_job_event(job_id, "info", "job.queued", "Job queued", {"mode": req.mode, "handle": req.handle, "ticketId": req.ticketId})
    return {"jobId": job_id}




@app.get("/api/scrape/{job_id}")
def api_scrape_status_legacy(job_id: str):
    status = api_scrape_status(job_id)
    events = db.get_scrape_events(db_path(), job_id, limit=50)
    return {**status, "logs": [f"{e['ts_utc']} {e['event']} {e['message']}" for e in events]}
@app.get("/api/scrape/{job_id}/status")
def api_scrape_status(job_id: str):
    job = db.get_scrape_job(db_path(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"jobId": job["job_id"], "status": job["status"], "startedAt": job.get("started_utc"), "finishedAt": job.get("finished_utc"), "summary": job.get("result"), "error": job.get("error_message")}


@app.get("/api/scrape/{job_id}/events")
def api_scrape_events(job_id: str):
    def gen():
        sent = 0
        while True:
            events = db.get_scrape_events(db_path(), job_id, limit=500)
            while sent < len(events):
                item = events[sent]
                payload = {"ts": item["ts_utc"], "level": item["level"], "event": item["event"], "message": item["message"], "data": item.get("data")}
                yield f"data: {json.dumps(payload)}\n\n"
                sent += 1
            job = db.get_scrape_job(db_path(), job_id)
            if job and job["status"] in {"completed", "failed"} and sent >= len(events):
                break
            time.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/tickets")
def api_tickets(handle: str | None = None, q: str | None = None, status: str | None = None, page: int = 1, pageSize: int = 50):
    return db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=pageSize)


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row["artifacts"] = db.get_artifacts(db_path(), row["ticket_id"], row["handle"])
    return row


@app.get("/api/artifacts")
def api_artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


@app.get("/api/health")
def api_health():
    stats_payload = db.get_stats(db_path())
    return {"status": "ok", "version": app.version, "db_path": db_path(), "db_exists": Path(db_path()).exists(), "last_updated_utc": stats_payload.get("last_updated_utc"), "stats": stats_payload}




@app.get("/health")
def health():
    return api_health()

@app.get("/handles")
def handles(search: str = "", limit: int = 50, offset: int = 0):
    return db.list_handles(db_path(), q=search, limit=limit, offset=offset)

@app.get("/handles/{handle}")
def handle_detail(handle: str):
    row = db.get_handle(db_path(), handle)
    if not row:
        raise HTTPException(status_code=404, detail="Handle not found")
    return row

@app.get("/handles/{handle}/tickets")
def handle_tickets(handle: str, limit: int = 50, status: str = "any"):
    return db.list_tickets(db_path(), handle=handle, page=1, page_size=limit, status=status)

@app.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, handle: str | None = None):
    return api_ticket(ticket_id=ticket_id, handle=handle)

@app.get("/artifacts")
def artifact(path: str):
    return api_artifact(path=path)
def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=db_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    os.environ["TICKETS_DB_PATH"] = str(Path(args.db).resolve())
    import uvicorn
    uvicorn.run("webscraper.ticket_api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
