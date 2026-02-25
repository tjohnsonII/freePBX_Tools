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
from webscraper.handles_loader import load_handles
from webscraper.paths import runs_dir
from webscraper.ticket_api import db
from webscraper.vpbx.handles import VpbxConfig, fetch_handles

SCRAPE_TIMEOUT_SECONDS = 3600
OUTPUT_ROOT = str((Path(__file__).resolve().parents[4] / "webscraper" / "var").resolve())

app = FastAPI(title="Ticket History API", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class StartScrapeRequest(BaseModel):
    mode: Literal["all", "one"] = "all"
    handle: str | None = None
    rescrape: bool = False
    refresh_handles: bool = True


class BatchScrapeRequest(BaseModel):
    handles: list[str]
    mode: str = "latest"
    limit: int = 10


@dataclass
class QueueJob:
    job_id: str
    run_id: str
    mode: str
    handle: str | None
    rescrape: bool
    refresh_handles: bool


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


def _get_required_env() -> tuple[VpbxConfig | None, str | None]:
    base_url = (os.getenv("VPBX_BASE_URL") or "https://secure.123.net").strip()
    username = (os.getenv("VPBX_USERNAME") or "").strip()
    password = (os.getenv("VPBX_PASSWORD") or "").strip()
    missing = [name for name, value in [("VPBX_USERNAME", username), ("VPBX_PASSWORD", password)] if not value]
    if missing:
        return None, f"Missing required environment variables: {', '.join(missing)}"
    return VpbxConfig(base_url=base_url, username=username, password=password), None


def _append_event(level: str, message: str, *, handle: str | None = None, job_id: str | None = None, meta: dict[str, Any] | None = None) -> None:
    ts = _iso_now()
    db.add_event(db_path(), ts, level, handle, message, {"job_id": job_id, **(meta or {})})
    if job_id:
        db.add_scrape_event(db_path(), job_id, ts, level, "scrape.progress", message, {"handle": handle, **(meta or {})})
    _log(message, job_id=job_id)


def _build_command(job: QueueJob, handle: str) -> list[str]:
    script = Path(__file__).resolve().parents[4] / "scripts" / "scrape_all_handles.py"
    out_dir = runs_dir() / job.run_id / handle
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(script), "--db", db_path(), "--out", str(out_dir), "--handles", handle]
    if job.rescrape:
        cmd.append("--resume")
    return cmd


def _discover_handles(config: VpbxConfig, job_id: str) -> list[str]:
    _append_event("info", "Starting handle discovery from vpbx.cgi", job_id=job_id)
    rows = fetch_handles(config)
    count = db.upsert_discovered_handles(db_path(), rows)
    _append_event("info", f"Discovered {count} handles from vpbx.cgi", job_id=job_id)
    return [str(row.get("handle")) for row in rows if row.get("handle")]


def _run_one_handle(job: QueueJob, handle: str) -> tuple[int, int]:
    db.ensure_handle_row(db_path(), handle)
    db.update_handle_progress(db_path(), handle, status="running", error=None, last_updated_utc=_iso_now(), last_run_id=job.run_id)
    _append_event("info", f"Starting handle {handle}", handle=handle, job_id=job.job_id)

    cmd = _build_command(job, handle)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    error_lines = 0
    for line in proc.stdout:
        cleaned = line.strip()
        if cleaned:
            _log(f"[{handle}] {cleaned}", job_id=job.job_id)
        if "[ERROR]" in cleaned:
            error_lines += 1
            _append_event("error", cleaned, handle=handle, job_id=job.job_id)
    rc = proc.wait(timeout=SCRAPE_TIMEOUT_SECONDS)

    ticket_payload = db.list_tickets(db_path(), handle=handle, page=1, page_size=1)
    total_for_handle = int(ticket_payload.get("totalCount") or 0)
    if rc == 0:
        db.update_handle_progress(
            db_path(),
            handle,
            status="ok",
            error=None,
            ticket_count=total_for_handle,
            last_updated_utc=_iso_now(),
            last_run_id=job.run_id,
        )
        _append_event("info", f"Completed handle {handle}, total={total_for_handle}", handle=handle, job_id=job.job_id)
    else:
        msg = f"scraper exit code {rc}"
        db.update_handle_progress(
            db_path(),
            handle,
            status="error",
            error=msg,
            ticket_count=total_for_handle,
            last_updated_utc=_iso_now(),
            last_run_id=job.run_id,
        )
        _append_event("error", f"Handle {handle} failed: {msg}", handle=handle, job_id=job.job_id)
    return rc, error_lines


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

        completed = 0
        errors = 0
        try:
            config, err = _get_required_env()
            if err or not config:
                raise RuntimeError(err or "Missing VPBX configuration")

            handles: list[str]
            if job.refresh_handles:
                discovered = _discover_handles(config, job.job_id)
                handles = discovered if job.mode == "all" else [job.handle or ""]
            elif job.mode == "all":
                handles = db.list_all_handles(db_path())
            else:
                handles = [job.handle or ""]

            handles = [h for h in handles if h]
            if job.mode == "one" and job.handle and job.handle not in handles:
                handles = [job.handle]

            if not handles:
                raise RuntimeError("No handles available to scrape. Run with refresh_handles=true and valid VPBX credentials.")

            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="running",
                progress_completed=0,
                progress_total=len(handles),
                started_utc=_iso_now(),
            )
            _append_event("info", f"Started scrape job with {len(handles)} handles", job_id=job.job_id)

            for handle in handles:
                try:
                    rc, line_errors = _run_one_handle(job, handle)
                    errors += line_errors + (1 if rc != 0 else 0)
                except Exception as exc:  # continue to next handle by requirement
                    errors += 1
                    db.update_handle_progress(
                        db_path(), handle, status="error", error=str(exc), last_updated_utc=_iso_now(), last_run_id=job.run_id
                    )
                    _append_event("error", f"Handle {handle} exception: {exc}", handle=handle, job_id=job.job_id)
                finally:
                    completed += 1
                    db.update_scrape_job(
                        db_path(),
                        job.job_id,
                        status="running",
                        progress_completed=completed,
                        progress_total=len(handles),
                    )

            final_status = "completed" if errors == 0 else "failed"
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status=final_status,
                progress_completed=completed,
                progress_total=len(handles),
                finished_utc=_iso_now(),
                error_message=None if errors == 0 else f"{errors} scrape errors",
                result={"errors": errors},
            )
            _append_event("info", f"Job finished status={final_status}", job_id=job.job_id)
        except Exception as exc:
            db.update_scrape_job(
                db_path(),
                job.job_id,
                status="failed",
                progress_completed=completed,
                progress_total=max(completed, 1),
                finished_utc=_iso_now(),
                error_message=str(exc),
                result={"error": str(exc)},
            )
            _append_event("error", f"Unhandled scrape exception: {exc}", job_id=job.job_id)
        finally:
            CURRENT_JOB_ID = None


def _scrape_script_path() -> Path:
    return Path(__file__).resolve().parents[4] / "scripts" / "scrape_all_handles.py"


def _run_scrape_job(job_id: str, handle: str, mode: str, limit: int) -> None:
    script = _scrape_script_path()
    start_ts = _iso_now()
    db.update_scrape_job(
        db_path(),
        job_id,
        status="running",
        progress_completed=0,
        progress_total=1,
        started_utc=start_ts,
        error_message=None,
    )
    if not script.exists():
        result = {
            "status": "failed",
            "errorType": "missing_script",
            "error": f"Missing scraper script: {script}",
            "logTail": [],
        }
        db.update_scrape_job(
            db_path(),
            job_id,
            status="failed",
            progress_completed=1,
            progress_total=1,
            finished_utc=_iso_now(),
            error_message=result["error"],
            result=result,
        )
        return

    cmd = [sys.executable, str(script), "--db", db_path(), "--handles", handle, "--mode", mode, "--limit", str(limit)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if proc.returncode == 0:
        db.update_scrape_job(
            db_path(),
            job_id,
            status="completed",
            progress_completed=1,
            progress_total=1,
            finished_utc=_iso_now(),
            error_message=None,
            result={"status": "completed", "logTail": lines[-50:]},
        )
        return

    result = {
        "status": "failed",
        "errorType": "scrape_failed",
        "error": f"scraper exit code {proc.returncode}",
        "logTail": lines[-50:],
    }
    db.update_scrape_job(
        db_path(),
        job_id,
        status="failed",
        progress_completed=1,
        progress_total=1,
        finished_utc=_iso_now(),
        error_message=result["error"],
        result=result,
    )


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
    handles = load_handles()
    if not handles:
        _log("No handles found from CSV or handles.txt.")
    else:
        for handle in handles:
            db.ensure_handle_row(db_path(), handle)
        _log(f"Loaded {len(handles)} handles.")
    stats = db.get_stats(db_path())
    _log(f"DB path: {db_path()}")
    _log(f"DB OK: handles={stats['total_handles']} tickets={stats['total_tickets']}")
    threading.Thread(target=_job_worker, daemon=True).start()


@app.get("/api/handles")
def api_handles(limit: int = Query(default=500, ge=1, le=5000), offset: int = 0):
    items = db.list_handles(db_path(), limit=limit, offset=offset)
    return {"items": sorted(items, key=lambda item: item.get("last_updated_utc") or item.get("finished_utc") or "", reverse=True)}


@app.get("/api/handles/summary")
def api_handles_summary(q: str = "", limit: int = Query(default=200, ge=1, le=5000), offset: int = Query(default=0, ge=0)):
    return db.list_handles_summary(db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    items = db.list_handle_names(db_path(), q=q, limit=limit)
    return {"items": items, "count": len(items)}


@app.post("/api/scrape-batch")
def api_scrape_batch(req: BatchScrapeRequest):
    job_ids: list[str] = []
    for raw_handle in req.handles:
        handle = (raw_handle or "").strip()
        if not handle:
            continue
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)
        db.create_scrape_job(
            db_path(),
            job_id=job_id,
            handle=handle,
            mode=req.mode,
            ticket_limit=req.limit,
            status="queued",
            created_utc=_iso_now(),
        )
        worker = threading.Thread(target=_run_scrape_job, args=(job_id, handle, req.mode, req.limit), daemon=True)
        worker.start()
    return {"status": "queued", "jobIds": job_ids}


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

    _, env_error = _get_required_env()
    if env_error:
        _append_event("error", env_error, handle=req.handle)
        raise HTTPException(status_code=400, detail=env_error)

    if req.mode == "one" and req.handle and not req.refresh_handles and not db.handle_exists(db_path(), req.handle):
        raise HTTPException(status_code=404, detail="handle not found in DB; run with refresh_handles=true first")

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
        JOB_QUEUE.append(
            QueueJob(job_id=job_id, run_id=run_id, mode=req.mode, handle=req.handle, rescrape=req.rescrape, refresh_handles=req.refresh_handles)
        )
    _append_event("info", f"Queued scrape job mode={req.mode} refresh_handles={req.refresh_handles}", handle=req.handle, job_id=job_id)
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
    stats_payload = {**stats_payload, "tickets": int(stats_payload.get("total_tickets", 0))}
    return {
        "status": "ok",
        "version": app.version,
        "db_path": db_path(),
        "db_exists": Path(db_path()).exists(),
        "last_updated_utc": stats_payload.get("last_updated_utc"),
        "total_handles": stats_payload.get("total_handles", 0),
        "total_tickets": stats_payload.get("total_tickets", 0),
        "stats": stats_payload,
    }


@app.get("/health")
def health():
    return api_health()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/scrape")
def api_scrape_legacy(payload: dict[str, Any]):
    mode = payload.get("mode")
    if mode == "handle":
        mode = "one"
    if mode not in {"all", "one"}:
        raise HTTPException(status_code=400, detail="Unsupported mode for legacy endpoint")
    req = StartScrapeRequest(
        mode=mode,
        handle=payload.get("handle"),
        rescrape=bool(payload.get("rescrape")),
        refresh_handles=bool(payload.get("refresh_handles", True)),
    )
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



def run_api(*, host: str = "127.0.0.1", port: int = 8787, reload: bool = False, db_override: str | None = None) -> None:
    if db_override:
        os.environ["TICKETS_DB_PATH"] = str(Path(db_override).resolve())
    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=host, port=port, reload=reload)

def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=db_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    run_api(host=args.host, port=args.port, reload=args.reload, db_override=args.db)


if __name__ == "__main__":
    main()
