from __future__ import annotations

import argparse
import json
import os
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
from pydantic import BaseModel

from webscraper.lib.db_path import get_tickets_db_path
from webscraper.ticket_api import db
from webscraper.paths import runs_dir

SCRAPE_TIMEOUT_SECONDS = 3600
OUTPUT_ROOT = str((Path(__file__).resolve().parents[4] / "webscraper" / "var").resolve())
HANDLES_FILE = Path(OUTPUT_ROOT) / "handles.txt"

app = FastAPI(title="Ticket History API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class StartScrapeRequest(BaseModel):
    mode: Literal["all", "one"] = "all"
    handle: str | None = None
    rescrape: bool = False


@dataclass
class QueueJob:
    job_id: str
    run_id: str
    mode: str
    handle: str | None
    rescrape: bool


JOB_QUEUE: list[QueueJob] = []
JOB_QUEUE_LOCK = threading.Lock()
CURRENT_JOB_ID: str | None = None


def db_path() -> str:
    return get_tickets_db_path()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(msg: str, request_id: str | None = None, job_id: str | None = None) -> None:
    rid = f" requestId={request_id}" if request_id else ""
    jid = f" jobId={job_id}" if job_id else ""
    print(f"[{_iso_now()}]{rid}{jid} {msg}", flush=True)


def _read_handles_file() -> list[str]:
    if not HANDLES_FILE.exists():
        HANDLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        HANDLES_FILE.write_text("# one handle per line\n", encoding="utf-8")
        return []
    items = [line.strip() for line in HANDLES_FILE.read_text(encoding="utf-8").splitlines()]
    return [line for line in items if line and not line.startswith("#")]


def _append_event(level: str, message: str, *, handle: str | None = None, job_id: str | None = None, meta: dict[str, Any] | None = None) -> None:
    ts = _iso_now()
    db.add_event(db_path(), ts, level, handle, message, {"job_id": job_id, **(meta or {})})
    if job_id:
        db.add_scrape_event(db_path(), job_id, ts, level, "scrape.progress", message, {"handle": handle, **(meta or {})})
    _log(message, job_id=job_id)


def _build_command(job: QueueJob, handles: list[str]) -> list[str]:
    script = Path(__file__).resolve().parents[4] / "scripts" / "scrape_all_handles.py"
    out_dir = runs_dir() / job.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(script), "--db", db_path(), "--out", str(out_dir)]
    if job.mode == "all":
        cmd += ["--handles", *handles]
    else:
        if not job.handle:
            raise ValueError("handle is required when mode=one")
        cmd += ["--handles", job.handle]
    if job.rescrape:
        cmd.append("--resume")
    return cmd


def _parse_progress_line(line: str) -> tuple[str | None, bool, bool]:
    clean = line.strip()
    handle = None
    if "Handle " in clean and ":" in clean:
        marker = clean.split("Handle ", 1)[1]
        handle = marker.split(":", 1)[0].strip()
    return handle, "[ERROR]" in clean, "[INFO] Handle" in clean


def _job_worker() -> None:
    global CURRENT_JOB_ID
    while True:
        job: QueueJob | None = None
        with JOB_QUEUE_LOCK:
            if JOB_QUEUE:
                job = JOB_QUEUE.pop(0)
                CURRENT_JOB_ID = job.job_id
        if not job:
            time.sleep(0.2)
            continue

        try:
            all_handles = _read_handles_file()
            if not all_handles:
                msg = f"Populate {HANDLES_FILE} with one handle per line before starting scrape."
                db.update_scrape_job(
                    db_path(),
                    job.job_id,
                    status="failed",
                    progress_completed=0,
                    progress_total=0,
                    started_utc=_iso_now(),
                    finished_utc=_iso_now(),
                    error_message=msg,
                    result={"error": msg},
                )
                _append_event("error", msg, job_id=job.job_id)
                continue

            handles = all_handles if job.mode == "all" else [job.handle]  # type: ignore[list-item]
            for handle in handles:
                db.ensure_handle_row(db_path(), handle)

            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="running",
                progress_completed=0,
                progress_total=len(handles),
                started_utc=_iso_now(),
            )
            _append_event("info", f"Started scrape job with {len(handles)} handles", job_id=job.job_id)

            cmd = _build_command(job, handles)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            completed = 0
            errors = 0
            current_handle: str | None = None
            assert proc.stdout is not None
            for line in proc.stdout:
                handle, is_error, is_complete = _parse_progress_line(line)
                if handle and handle != current_handle:
                    current_handle = handle
                    db.update_handle_progress(db_path(), handle, status="running", last_run_id=job.run_id)
                    _append_event("info", f"Starting handle {handle}", handle=handle, job_id=job.job_id)
                if is_error:
                    errors += 1
                    _append_event("error", line.strip(), handle=current_handle, job_id=job.job_id)
                    if current_handle:
                        db.update_handle_progress(db_path(), current_handle, status="error", error=line.strip(), last_run_id=job.run_id)
                if is_complete and current_handle:
                    completed += 1
                    ticket_payload = db.list_tickets(db_path(), handle=current_handle, page=1, page_size=1)
                    total_for_handle = int(ticket_payload.get("totalCount") or 0)
                    db.update_handle_progress(
                        db_path(),
                        current_handle,
                        status="ok",
                        error=None,
                        ticket_count=total_for_handle,
                        last_updated_utc=_iso_now(),
                        last_run_id=job.run_id,
                    )
                    db.update_scrape_job(
                        db_path(),
                        job.job_id,
                        status="running",
                        progress_completed=completed,
                        progress_total=len(handles),
                    )
                    _append_event("info", f"Completed handle {current_handle}, total={total_for_handle}", handle=current_handle, job_id=job.job_id)

            rc = proc.wait(timeout=SCRAPE_TIMEOUT_SECONDS)
            final_status = "completed" if rc == 0 else "failed"
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status=final_status,
                progress_completed=completed,
                progress_total=len(handles),
                finished_utc=_iso_now(),
                error_message=None if rc == 0 else f"scraper exit code {rc}",
                result={"returncode": rc, "errors": errors, "current_handle": current_handle},
            )
            _append_event("info", f"Job finished status={final_status}", job_id=job.job_id)
        except Exception as exc:
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="failed",
                progress_completed=0,
                progress_total=0,
                finished_utc=_iso_now(),
                error_message=str(exc),
                result={"error": str(exc)},
            )
            _append_event("error", f"Unhandled scrape exception: {exc}", job_id=job.job_id)
        finally:
            CURRENT_JOB_ID = None


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


@app.on_event("startup")
def startup() -> None:
    db.ensure_indexes(db_path())
    handles = _read_handles_file()
    for handle in handles:
        db.ensure_handle_row(db_path(), handle)
    stats = db.get_stats(db_path())
    _log(f"DB path: {db_path()}")
    _log(f"DB OK: handles={stats['total_handles']} tickets={stats['total_tickets']}")
    threading.Thread(target=_job_worker, daemon=True).start()


@app.get("/api/handles")
def api_handles(limit: int = Query(default=500, ge=1, le=5000), offset: int = 0):
    items = db.list_handles(db_path(), limit=limit, offset=offset)
    return {"items": sorted(items, key=lambda item: item.get("last_updated_utc") or item.get("finished_utc") or "", reverse=True)}


@app.get("/api/events/latest")
def api_events_latest(limit: int = Query(default=50, ge=1, le=500)):
    items = db.get_latest_events(db_path(), limit=limit)
    return {
        "items": [
            {
                "id": item.get("id"),
                "ts": item.get("created_utc"),
                "level": item.get("level"),
                "handle": item.get("handle"),
                "message": item.get("message"),
                "meta": item.get("meta"),
            }
            for item in items
        ]
    }


@app.post("/api/scrape/start")
def api_scrape_start(req: StartScrapeRequest):
    if req.mode == "one" and not req.handle:
        raise HTTPException(status_code=400, detail="handle is required when mode='one'")

    handles = _read_handles_file()
    if not handles:
        msg = f"No handles configured. Populate {HANDLES_FILE} first."
        _append_event("error", msg)
        raise HTTPException(status_code=400, detail=msg)

    if req.mode == "one" and req.handle and req.handle not in handles:
        raise HTTPException(status_code=404, detail="handle not found in handles file")

    job_id = str(uuid.uuid4())
    run_id = datetime.now(timezone.utc).strftime("api_%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    db.create_scrape_job(
        db_path(),
        job_id=job_id,
        handle=req.handle,
        mode=req.mode,
        ticket_limit=None,
        status="queued",
        created_utc=_iso_now(),
    )
    with JOB_QUEUE_LOCK:
        JOB_QUEUE.append(QueueJob(job_id=job_id, run_id=run_id, mode=req.mode, handle=req.handle, rescrape=req.rescrape))
    _append_event("info", f"Queued scrape job mode={req.mode}", handle=req.handle, job_id=job_id)
    return {"job_id": job_id, "started": True}


@app.get("/api/scrape/status")
def api_scrape_status(job_id: str):
    job = db.get_scrape_job(db_path(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = job.get("result") or {}
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "total_handles": job.get("progress_total", 0),
        "completed": job.get("progress_completed", 0),
        "running": CURRENT_JOB_ID == job_id,
        "errors": int(result.get("errors") or 0),
        "current_handle": result.get("current_handle"),
        "started_utc": job.get("started_utc"),
        "finished_utc": job.get("finished_utc"),
    }


@app.get("/api/handles/{handle}/latest")
def api_handle_latest(handle: str):
    row = db.get_handle_latest(db_path(), handle)
    if not row:
        raise HTTPException(status_code=404, detail="Handle not found")
    return row


@app.get("/api/handles/{handle}/tickets")
def api_handle_tickets(handle: str, limit: int = 50, status: str = "any"):
    return db.list_tickets(db_path(), handle=handle, page=1, page_size=limit, status=status)


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
    return {
        "status": "ok",
        "version": app.version,
        "db_path": db_path(),
        "db_exists": Path(db_path()).exists(),
        "last_updated_utc": stats_payload.get("last_updated_utc"),
        "stats": stats_payload,
    }


@app.get("/health")
def health():
    return api_health()


@app.post("/api/scrape")
def api_scrape_legacy(payload: dict[str, Any]):
    mode = payload.get("mode")
    if mode == "handle":
        mode = "one"
    if mode not in {"all", "one"}:
        raise HTTPException(status_code=400, detail="Unsupported mode for legacy endpoint")
    req = StartScrapeRequest(mode=mode, handle=payload.get("handle"), rescrape=bool(payload.get("rescrape")))
    out = api_scrape_start(req)
    return {"jobId": out["job_id"], "started": out["started"]}


@app.get("/api/scrape/{job_id}/events")
def api_scrape_events(job_id: str):
    def gen():
        last_id = 0
        while True:
            items = db.get_latest_events(db_path(), limit=200)
            fresh = [item for item in reversed(items) if int(item.get("id") or 0) > last_id and (item.get("meta") or {}).get("job_id") == job_id]
            for item in fresh:
                last_id = int(item["id"])
                payload = {
                    "ts": item["created_utc"],
                    "level": item["level"],
                    "event": "scrape.progress",
                    "message": item["message"],
                    "data": item.get("meta") or {},
                }
                yield f"data: {json.dumps(payload)}\\n\\n"
            status = db.get_scrape_job(db_path(), job_id)
            if status and status.get("status") in {"completed", "failed"}:
                break
            time.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


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
