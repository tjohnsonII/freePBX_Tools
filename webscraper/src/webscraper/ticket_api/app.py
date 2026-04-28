from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from webscraper.handles_loader import load_handles
from webscraper.lib.db_path import get_tickets_db_path
from webscraper.logging_config import LOG_DIR, setup_logging
from webscraper.paths import kb_dir

# CLIENT_MODE=1 → send all writes to a remote server via HTTP (no local SQLite).
# Leave unset (or 0) for normal local operation.
if os.getenv("CLIENT_MODE", "").strip() == "1":
    from webscraper.ticket_api import db_client as db  # type: ignore[no-redef]
else:
    from webscraper.ticket_api import db  # type: ignore[assignment]

# ── Constants ────────────────────────────────────────────────────────────────


HANDLE_RE = re.compile(r"^[A-Za-z0-9]+$")
LOCALHOST_ONLY = {"127.0.0.1", "::1"}
OUTPUT_ROOT = str((Path(__file__).resolve().parents[4] / "webscraper" / "var").resolve())

TIMELINE_CATEGORIES: tuple[str, ...] = (
    "ticket_opened",
    "follow_up",
    "phone_replacement",
    "provisioning_change",
    "queue_change",
    "voicemail_issue",
    "training_provided",
    "awaiting_customer",
    "resolved",
)

LOGGER = setup_logging("ticket_api")

# ── DB / time helpers ────────────────────────────────────────────────────────


def db_path() -> str:
    return get_tickets_db_path()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_event(
    level: str,
    message: str,
    *,
    handle: str | None = None,
    job_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    ts = _iso_now()
    db.add_event(db_path(), ts, level, handle, message, {"job_id": job_id, **(meta or {})})
    if job_id:
        db.add_scrape_event(db_path(), job_id, ts, level, "scrape.progress", message, {"handle": handle, **(meta or {})})
    LOGGER.info("[%s] %s", ts, message)


def _normalize_handle(handle: str) -> str:
    normalized = (handle or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="handle is required")
    if not HANDLE_RE.match(normalized):
        raise HTTPException(status_code=400, detail="handle must be alphanumeric")
    return normalized


def _is_localhost_request(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in LOCALHOST_ONLY


# ── Multipart dependency check ───────────────────────────────────────────────


def _has_python_multipart() -> bool:
    return importlib.util.find_spec("multipart") is not None


def _missing_python_multipart_message() -> str:
    return f"Missing dependency python-multipart. Install: {sys.executable} -m pip install python-multipart"


# ── Timeline helpers ──────────────────────────────────────────────────────────


def _extract_event_category(raw_text: str) -> tuple[str, float]:
    text = raw_text.lower()
    rules: list[tuple[str, tuple[str, ...], float]] = [
        ("phone_replacement", ("replace phone", "phone replacement", "rma", "replaced handset"), 0.9),
        ("provisioning_change", ("provision", "template change", "configuration update", "reprovision"), 0.8),
        ("queue_change", ("queue", "ring group", "call routing", "acd"), 0.75),
        ("voicemail_issue", ("voicemail", "vm issue", "mailbox"), 0.85),
        ("training_provided", ("training", "walked through", "explained to customer"), 0.75),
        ("awaiting_customer", ("awaiting customer", "waiting on customer", "pending customer"), 0.8),
        ("resolved", ("resolved", "closed", "fixed", "completed"), 0.9),
        ("follow_up", ("follow up", "follow-up", "called customer", "emailed customer"), 0.7),
    ]
    for category, needles, confidence in rules:
        if any(needle in text for needle in needles):
            return category, confidence
    if any(needle in text for needle in ("opened", "new ticket", "created")):
        return "ticket_opened", 0.7
    return "follow_up", 0.5


def _build_handle_timeline(
    handle: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tickets_payload = db.list_tickets(db_path(), handle=handle, page=1, page_size=1000, sort="oldest")
    ticket_rows = (tickets_payload.get("items") if isinstance(tickets_payload, dict) else None) or []
    events: list[dict[str, Any]] = []
    for row in ticket_rows:
        ticket_id = str(row.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        parts = [
            str(row.get("title") or ""), str(row.get("subject") or ""),
            str(row.get("status") or ""), str(row.get("raw_json") or ""),
        ]
        raw_text = " | ".join(part for part in parts if part).strip()
        category, confidence = _extract_event_category(raw_text)
        event_time = row.get("updated_utc") or row.get("created_utc") or row.get("opened_utc") or _iso_now()
        summary = str(row.get("title") or row.get("subject") or f"Ticket {ticket_id}")
        events.append({
            "handle": handle, "ticket_id": ticket_id, "category": category,
            "event_utc": event_time, "summary": summary,
            "raw_source_text": raw_text, "confidence": confidence,
        })
        if category != "ticket_opened":
            events.append({
                "handle": handle, "ticket_id": ticket_id, "category": "ticket_opened",
                "event_utc": row.get("created_utc") or event_time,
                "summary": f"Ticket opened: {summary}",
                "raw_source_text": raw_text, "confidence": 0.6,
            })

    timeline_rows = [
        {
            "event_utc": event.get("event_utc"),
            "category": event.get("category"),
            "title": str(event.get("summary") or ""),
            "details": event.get("raw_source_text"),
            "ticket_id": event.get("ticket_id"),
            "source_event_id": None,
        }
        for event in sorted(events, key=lambda item: str(item.get("event_utc") or ""))
    ]
    pattern_counts: dict[str, dict[str, Any]] = {}
    for event in events:
        category = str(event.get("category") or "follow_up")
        bucket = pattern_counts.setdefault(
            category, {"pattern": category, "count": 0, "last_seen_utc": None}
        )
        bucket["count"] += 1
        bucket["last_seen_utc"] = event.get("event_utc")
    patterns = sorted(
        pattern_counts.values(), key=lambda item: int(item.get("count") or 0), reverse=True
    )
    return events, timeline_rows, patterns


# ── Log API helpers ───────────────────────────────────────────────────────────


def _log_api_enabled() -> bool:
    raw = os.getenv("WEBSCRAPER_LOGS_ENABLED")
    if raw is None:
        raw = os.getenv("SCRAPER_ENABLE_LOG_API")
    if raw is not None:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    env_name = (
        os.getenv("ENV") or os.getenv("APP_ENV") or os.getenv("PYTHON_ENV") or "dev"
    ).strip().lower()
    return env_name in {"dev", "development", "local", "test"}


def _ensure_log_api_enabled(request: Request) -> None:
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    if not _log_api_enabled():
        raise HTTPException(
            status_code=403,
            detail={"error": "logs_disabled", "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"},
        )


def _resolve_log_file(name: str) -> Path:
    candidate = (LOG_DIR / name).resolve()
    if candidate.parent != LOG_DIR or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    return candidate


def _tail_file(path: Path, lines: int) -> list[str]:
    if lines <= 0:
        return []
    chunk_size = 8192
    data = bytearray()
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        file_size = fh.tell()
        while file_size > 0 and data.count(b"\n") <= lines:
            read_size = min(chunk_size, file_size)
            file_size -= read_size
            fh.seek(file_size)
            data = fh.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-lines:]


# ── Startup ───────────────────────────────────────────────────────────────────


def _startup_bootstrap() -> None:
    _client_mode = os.getenv("CLIENT_MODE", "").strip() == "1"
    if _client_mode:
        server = os.getenv("INGEST_SERVER_URL", "http://127.0.0.1:8788")
        LOGGER.info("startup CLIENT_MODE=1 ingest_server=%s", server)
    else:
        db.ensure_indexes(db_path())
        handles = load_handles()
        if handles:
            for handle in handles:
                db.ensure_handle_row(db_path(), handle)
        # Reap jobs left in running/queued state from a previous crashed session
        try:
            import sqlite3 as _sqlite3
            con = _sqlite3.connect(db_path())
            cur = con.execute(
                "UPDATE scrape_jobs SET status='failed', finished_utc=datetime('now')"
                " WHERE status IN ('running','queued')"
            )
            if cur.rowcount:
                LOGGER.warning("startup: reaped %d stale running/queued jobs", cur.rowcount)
            con.commit()
            con.close()
        except Exception as exc:
            LOGGER.warning("startup: could not reap stale jobs: %s", exc)
        stats = db.get_stats(db_path())
        LOGGER.info("startup db_path=%s handles=%s tickets=%s",
                    db_path(), stats.get("total_handles"), stats.get("total_tickets"))
    if not _has_python_multipart():
        LOGGER.warning(_missing_python_multipart_message())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup_bootstrap()
    yield


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Ticket History API", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register ingest routes so remote clients can POST scraped data to this server.
# Protected by X-Ingest-Key header (INGEST_API_KEY env var); localhost-only fallback.
from webscraper.ticket_api import ingest_routes as _ingest_routes  # noqa: E402
_ingest_routes.register(app, db, db_path)


@app.middleware("http")
async def request_context(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        LOGGER.info("request method=%s path=%s status=%s ms=%s",
                    request.method, request.url.path, response.status_code, duration_ms)
        return response
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        LOGGER.exception("request_failed method=%s path=%s ms=%s",
                         request.method, request.url.path, duration_ms)
        raise


# ── Pydantic models ───────────────────────────────────────────────────────────


class ScrapeStartRequest(BaseModel):
    resume_from_handle: str | None = None


# ── Job conversion helper ─────────────────────────────────────────────────────


def _job_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Map a scrape_jobs DB row to the API Job shape expected by the dashboard."""
    result = row.get("result") or {}
    return {
        "job_id": row.get("job_id", ""),
        "created_at": row.get("created_utc", ""),
        "started_at": row.get("started_utc"),
        "completed_at": row.get("finished_utc"),
        "current_state": row.get("status", "unknown"),
        "current_step": result.get("status_message", row.get("status", "unknown")),
        "records_found": int(row.get("progress_total") or 0),
        "records_written": int(row.get("progress_completed") or 0),
        "error_message": row.get("error_message"),
    }



@app.get("/api/scrape/check-auth")
def api_check_auth():
    """Auth check runs on the client, not the server."""
    raise HTTPException(status_code=501, detail="Auth check runs on the client. Use the client branch.")


# ── Scrape control endpoints ──────────────────────────────────────────────────


@app.post("/api/scrape/start")
def api_scrape_start_selenium(payload: ScrapeStartRequest | None = None):
    """Scraping runs on the client. This server only receives data via /api/ingest/*."""
    raise HTTPException(status_code=501, detail="Scraping is handled by the client. Use the client branch.")


@app.post("/api/scrape/selenium_fallback")
def api_scrape_selenium_fallback():
    """Alias kept for compatibility — scraping is handled by the client."""
    raise HTTPException(status_code=501, detail="Scraping is handled by the client. Use the client branch.")


@app.get("/api/scrape/state")
def api_scrape_state():
    """Return the last completed handle and timestamp from var/kb/scrape_state.json."""
    state_path = kb_dir() / "scrape_state.json"
    if not state_path.exists():
        return {"last_completed_handle": None, "updated_utc": None}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read scrape state: {exc}") from exc


# ── Job status endpoints ──────────────────────────────────────────────────────


@app.get("/api/jobs")
def api_jobs():
    rows = db.list_scrape_jobs(db_path(), limit=20)
    return {"items": [_job_row_to_api(r) for r in rows]}


@app.get("/api/jobs/{job_id}/events")
def api_scrape_job_events(job_id: str, limit: int = Query(default=50, ge=1, le=500)):
    """Return the last *limit* events for a scrape job as JSON (non-streaming)."""
    rows = db.get_scrape_events(db_path(), job_id, limit=limit)
    return {"job_id": job_id, "events": rows}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    row = db.get_scrape_job(db_path(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_row_to_api(row)


@app.get("/jobs/{job_id}")
def job_status_alias(job_id: str):
    """Alias used by the Next.js proxy route /api/jobs/status/[jobId]."""
    row = db.get_scrape_job(db_path(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_row_to_api(row)


# ── System / health ───────────────────────────────────────────────────────────


@app.get("/api/system/status")
def api_system_status():
    from datetime import datetime, timezone as _tz
    stats = db.get_stats(db_path())

    # ── Active job ────────────────────────────────────────────────────────────
    current_job: dict[str, Any] | None = None
    state = "idle"
    last_error: str | None = None
    try:
        latest_job = db.get_latest_scrape_job(db_path())
        if latest_job and latest_job.get("status") in ("running", "queued"):
            current_job = _job_row_to_api(latest_job)
            state = latest_job["status"]
            last_error = latest_job.get("error_message")
        elif latest_job and latest_job.get("status") == "failed":
            last_error = latest_job.get("error_message")
    except Exception:
        pass

    # ── Client heartbeat ──────────────────────────────────────────────────────
    clients: list[dict[str, Any]] = []
    try:
        now_utc = datetime.now(_tz.utc)
        for hb in db.get_client_heartbeats(db_path()):
            seen_str = hb.get("server_seen_utc", "")
            try:
                seen_dt = datetime.fromisoformat(seen_str.replace("Z", "+00:00"))
                age_s = int((now_utc - seen_dt).total_seconds())
            except Exception:
                age_s = 9999
            connectivity = "connected" if age_s < 120 else ("recent" if age_s < 600 else "offline")
            clients.append({
                "client_id":      hb.get("client_id"),
                "connectivity":   connectivity,
                "last_seen_ago_s": age_s,
                "last_seen_utc":  seen_str,
                "status":         hb.get("status"),
                "job_id":         hb.get("job_id"),
                "current_handle": hb.get("current_handle"),
                "handles_done":   hb.get("handles_done", 0),
                "handles_total":  hb.get("handles_total", 0),
                "client_version": hb.get("client_version"),
                "vpn_connected":  bool(hb.get("vpn_connected")) if hb.get("vpn_connected") is not None else None,
                "vpn_ip":         hb.get("vpn_ip"),
            })
    except Exception:
        pass

    return {
        "backend_health": "ok",
        "state": state,
        "db_counts": {
            "tickets": int(stats.get("total_tickets", 0)),
            "handles": int(stats.get("total_handles", 0)),
        },
        "last_error": last_error,
        "current_job": current_job,
        "clients": clients,
    }


@app.get("/api/db/status")
def api_db_status():
    stats = db.get_stats(db_path())
    return {
        "tickets": int(stats.get("total_tickets", 0)),
        "handles": int(stats.get("total_handles", 0)),
    }


@app.get("/api/health")
@app.get("/health")
def api_health():
    stats = db.get_stats(db_path())
    return {
        "ok": True,
        "status": "ok",
        "version": app.version,
        "db_path": db_path(),
        "db_exists": Path(db_path()).exists(),
        "total_handles": int(stats.get("total_handles", 0)),
        "total_tickets": int(stats.get("total_tickets", 0)),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ── Handle / ticket data endpoints ────────────────────────────────────────────


@app.get("/api/handles")
@app.get("/handles")
def api_handles(
    q: str = "",
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = 0,
):
    items = db.list_handles(db_path(), q=q, limit=limit, offset=offset)
    return {"items": sorted(
        items,
        key=lambda item: item.get("last_updated_utc") or item.get("finished_utc") or "",
        reverse=True,
    )}


@app.get("/api/handles/summary")
def api_handles_summary(
    q: str = "",
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return db.list_handles_summary(db_path(), q=q, limit=limit, offset=offset)


@app.get("/api/handles/all")
def api_handles_all(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    items = db.list_handle_names(db_path(), q=q, limit=limit)
    return {"items": items, "count": len(items)}


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
def api_tickets(
    handle: str | None = None,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    pageSize: int = 50,
):
    return db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=pageSize)


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row["artifacts"] = db.get_artifacts(db_path(), row["ticket_id"], row["handle"])
    return row


@app.get("/api/kb/tickets")
def api_kb_tickets(
    q: str | None = None,
    handle: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    """Search KB tickets. Full-text search includes ticket notes stored in raw_json."""
    result = db.list_tickets(db_path(), handle=handle, q=q, status=status, page=page, page_size=page_size)
    items = []
    for ticket in result["items"]:
        notes_preview: str | None = None
        raw = ticket.get("raw_json")
        if raw:
            try:
                parsed = json.loads(raw)
                notes = parsed.get("detail", {}).get("notes") or parsed.get("notes")
                if notes:
                    notes_preview = str(notes)[:300]
            except Exception:
                pass
        items.append({**ticket, "notes_preview": notes_preview})
    return {**result, "items": items}


@app.get("/api/kb/tickets/{ticket_id}")
def api_kb_ticket(ticket_id: str, handle: str | None = None):
    """Return a single KB ticket with full detail and parsed notes."""
    row = db.get_ticket(db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    detail: dict[str, Any] = {}
    raw = row.get("raw_json")
    if raw:
        try:
            parsed = json.loads(raw)
            detail = parsed.get("detail") or {}
        except Exception:
            pass
    return {**row, "detail": detail, "notes": detail.get("notes"), "fields": detail.get("fields", {})}


@app.get("/api/kb/handles")
def api_kb_handles(q: str = "", limit: int = Query(default=500, ge=1, le=5000)):
    """Return KB handle summary sorted by last scraped date."""
    rows = db.list_handles_summary(db_path(), q=q, limit=limit)
    return {"items": sorted(rows, key=lambda r: r.get("updated_latest_utc") or r.get("last_scrape_utc") or "", reverse=True)}


@app.get("/api/kb/export")
def api_kb_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    handle: str | None = None,
    q: str | None = None,
    status: str | None = None,
):
    """Bulk export of KB tickets as JSON or CSV."""
    result = db.list_tickets(db_path(), handle=handle, q=q, status=status, page=1, page_size=10000)
    items = result["items"]
    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        fields = ["ticket_id", "handle", "subject", "status", "created_utc", "updated_utc", "ticket_url"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow({k: item.get(k, "") for k in fields})
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=kb_tickets.csv"},
        )
    return {"items": items, "total": result["totalCount"]}


@app.get("/api/artifacts")
def api_artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


@app.get("/api/events/latest")
def api_events_latest(
    limit: int = Query(default=50, ge=1, le=500),
    job_id: str | None = None,
):
    items = db.get_latest_events(db_path(), limit=limit)
    if job_id:
        items = [item for item in items if (item.get("meta") or {}).get("job_id") == job_id]
        items = items[:limit]
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


@app.get("/companies/{handle}")
def company_detail(handle: str):
    normalized = _normalize_handle(handle)
    company = db.get_company(db_path(), normalized) or {"handle": normalized}
    latest = db.get_handle_latest(db_path(), normalized) or {}
    return {"company": company, "latest": latest}


@app.get("/companies/{handle}/tickets")
def company_tickets(handle: str, limit: int = Query(default=200, ge=1, le=1000)):
    normalized = _normalize_handle(handle)
    return db.list_tickets(db_path(), handle=normalized, page=1, page_size=limit)


@app.get("/companies/{handle}/timeline")
def company_timeline(handle: str, limit: int = Query(default=500, ge=1, le=5000)):
    normalized = _normalize_handle(handle)
    rows = db.get_company_timeline(db_path(), normalized, limit=limit)
    return {"handle": normalized, "items": rows}


@app.post("/jobs/build-timeline")
def jobs_build_timeline(payload: dict[str, Any]):
    handle = _normalize_handle(str(payload.get("handle") or ""))
    now = _iso_now()
    events, timeline_rows, patterns = _build_handle_timeline(handle)
    db.upsert_company(db_path(), handle=handle, now_utc=now)
    event_count = db.replace_ticket_events(db_path(), handle, events, now)
    timeline_count = db.replace_company_timeline(db_path(), handle, timeline_rows, now)
    pattern_count = db.replace_resolution_patterns(db_path(), handle, patterns, now)
    return {
        "ok": True,
        "handle": handle,
        "ticket_events_written": event_count,
        "timeline_rows_written": timeline_count,
        "resolution_patterns_written": pattern_count,
        "categories": list(TIMELINE_CATEGORIES),
    }


@app.get("/api/companies/{handle}")
def api_company_detail(handle: str):
    return company_detail(handle)


@app.get("/api/companies/{handle}/tickets")
def api_company_tickets(handle: str, limit: int = Query(default=200, ge=1, le=1000)):
    return company_tickets(handle, limit=limit)


@app.get("/api/companies/{handle}/timeline")
def api_company_timeline(handle: str, limit: int = Query(default=200, ge=1, le=5000)):
    return company_timeline(handle, limit=limit)


@app.post("/api/jobs/build-timeline")
def api_jobs_build_timeline(payload: dict[str, Any]):
    return jobs_build_timeline(payload)


# ── Log API endpoints ─────────────────────────────────────────────────────────


@app.get("/api/logs/enabled")
def api_logs_enabled(request: Request):
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Logs API is localhost-only")
    return {"enabled": _log_api_enabled(), "how_to_enable": "set WEBSCRAPER_LOGS_ENABLED=1"}


@app.get("/api/logs/list")
def api_logs_list(request: Request):
    _ensure_log_api_enabled(request)
    items: list[dict[str, Any]] = []
    for path in sorted(LOG_DIR.glob("*.log*")):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append({
            "name": path.name,
            "size": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return {"items": items}


@app.get("/api/logs/tail")
def api_logs_tail(
    request: Request,
    name: str = Query(...),
    lines: int = Query(2000, ge=1, le=5000),
):
    _ensure_log_api_enabled(request)
    log_file = _resolve_log_file(name)
    rows = _tail_file(log_file, lines)
    return {"name": log_file.name, "lines": rows}


# ── Handle management endpoints ──────────────────────────────────────────────


class HandleAddRequest(BaseModel):
    handle: str


@app.post("/api/handles")
def api_handle_add(payload: HandleAddRequest, request: Request):
    """Add a new handle to the knowledge base."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Handle management is localhost-only")
    handle = _normalize_handle(payload.handle)
    db.ensure_handle_row(db_path(), handle)
    _append_event("info", f"handle_added handle={handle}")
    return {"handle": handle, "status": "added"}


@app.delete("/api/handles/{handle}")
def api_handle_delete(handle: str, request: Request):
    """Remove a handle and all its tickets from the knowledge base."""
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Handle management is localhost-only")
    handle = _normalize_handle(handle)
    deleted = db.delete_handle(db_path(), handle)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Handle {handle!r} not found")
    _append_event("info", f"handle_deleted handle={handle}")
    return {"handle": handle, "status": "deleted"}


# ── NOC Queue endpoints ───────────────────────────────────────────────────────


@app.get("/api/noc-queue/records")
def api_noc_queue_records(view: str | None = Query(None)):
    """Return cached NOC queue tickets. Optionally filter by view: hosted|noc|all|local."""
    db.ensure_indexes(db_path())
    return {"items": db.list_noc_queue_tickets(db_path(), view=view)}


class _NocQueueRefreshBody(BaseModel):
    view: str | None = None  # hosted | noc | all | local — omit to scrape all


@app.post("/api/noc-queue/refresh")
def api_noc_queue_refresh(body: _NocQueueRefreshBody, request: Request):
    """NOC queue scraping runs on the client. Data arrives via /api/ingest/noc-queue."""
    raise HTTPException(status_code=501, detail="NOC queue scraping is handled by the client. Use the client branch.")


# ── VPBX endpoints ───────────────────────────────────────────────────────────


@app.get("/api/vpbx/records")
def api_vpbx_records():
    """Return cached VPBX records from the database (no live scrape)."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_records(db_path())}


@app.post("/api/vpbx/refresh")
def api_vpbx_refresh(request: Request):
    """VPBX scraping runs on the client. Data arrives via /api/ingest/vpbx/records."""
    raise HTTPException(status_code=501, detail="VPBX scraping is handled by the client. Use the client branch.")


class _VpbxDeviceConfigsRefreshBody(BaseModel):
    handles: list[str] | None = None  # limit to specific handles; omit for all
    force: bool = False               # True → ignore existing data, re-scrape everything
    incomplete_only: bool = False     # True → re-scrape devices with blank/single-line view_config


@app.get("/api/vpbx/device-configs")
def api_vpbx_device_configs(handle: str | None = Query(None)):
    """Return cached VPBX device configs. Filter by handle= to narrow results."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_device_configs(db_path(), handle=handle)}


class _SidecarSaveBody(BaseModel):
    vpbx_id: str
    sidecar_config: str  # full sidecar config text; pass "" to clear


@app.put("/api/vpbx/device-configs/{device_id}/sidecar")
def api_vpbx_save_sidecar(device_id: str, body: _SidecarSaveBody, request: Request):
    """Save or update the sidecar_config for a specific device.

    Only touches the sidecar_config column — never overwrites scraped data.
    Returns 404 if the device_id + vpbx_id combination doesn't exist yet.
    """
    if not _is_localhost_request(request):
        raise HTTPException(status_code=403, detail="Sidecar save is localhost-only")
    db.ensure_indexes(db_path())
    updated = db.save_sidecar_config(db_path(), device_id, body.vpbx_id, body.sidecar_config)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device {device_id}/{body.vpbx_id} not found")
    return {"status": "saved", "device_id": device_id, "vpbx_id": body.vpbx_id,
            "sidecar_length": len(body.sidecar_config)}


@app.post("/api/vpbx/device-configs/refresh")
def api_vpbx_device_configs_refresh(body: _VpbxDeviceConfigsRefreshBody, request: Request):
    """VPBX device config scraping runs on the client. Data arrives via /api/ingest/vpbx/device-configs."""
    raise HTTPException(status_code=501, detail="VPBX device config scraping is handled by the client. Use the client branch.")


# ── Orders endpoints ──────────────────────────────────────────────────────────


@app.get("/api/orders")
def api_orders(pm: str | None = Query(None)):
    """Return scraped orders from 123.net orders admin. Filter by pm= username."""
    db.ensure_indexes(db_path())
    return {"items": db.list_orders(db_path(), pm=pm)}


# ── VPBX site-config endpoints ────────────────────────────────────────────────


class _VpbxSiteConfigsRefreshBody(BaseModel):
    handles: list[str] | None = None  # limit to specific handles; omit for all


@app.get("/api/vpbx/site-configs")
def api_vpbx_site_configs(handle: str | None = Query(None)):
    """Return cached VPBX site configs. Filter by handle= to narrow results."""
    db.ensure_indexes(db_path())
    return {"items": db.list_vpbx_site_configs(db_path(), handle=handle)}


@app.get("/api/vpbx/site-configs/{handle}")
def api_vpbx_site_config_by_handle(handle: str):
    """Return site config for a single handle. 404 if not yet scraped."""
    db.ensure_indexes(db_path())
    h = _normalize_handle(handle)
    items = db.list_vpbx_site_configs(db_path(), handle=h)
    if not items:
        raise HTTPException(status_code=404, detail=f"No site config found for handle {h}")
    return items[0]


@app.post("/api/vpbx/site-configs/refresh")
def api_vpbx_site_configs_refresh(body: _VpbxSiteConfigsRefreshBody, request: Request):
    """VPBX site config scraping runs on the client. Data arrives via /api/ingest/vpbx/site-configs."""
    raise HTTPException(status_code=501, detail="VPBX site config scraping is handled by the client. Use the client branch.")


@app.get("/api/clients")
def api_clients():
    """Return all known scraper clients and their latest heartbeat state."""
    rows = db.get_client_heartbeats(db_path())
    return {"items": rows}


@app.get("/api/orders")
def api_orders(
    assigned_to: str | None = Query(None),
    order_type: str | None = Query(None),
    from_date: str | None = Query(None),
):
    """Return scraped orders from the orders table. Filter by assigned_to, order_type, or from_date."""
    db.ensure_indexes(db_path())
    orders = db.list_orders(
        db_path(),
        assigned_to=assigned_to or None,
        order_type=order_type or None,
        from_date=from_date or None,
    )
    return {"orders": orders, "count": len(orders)}


# ── CLI entry points ──────────────────────────────────────────────────────────


def run_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    reload: bool = False,
    db_override: str | None = None,
) -> None:
    if db_override:
        os.environ["TICKETS_DB_PATH"] = str(Path(db_override).resolve())
    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=host, port=port, reload=reload,
                proxy_headers=False)


def _pip_check_required_deps() -> list[tuple[str, str, bool]]:
    checks = [
        ("fastapi", "fastapi>=0.115.0"),
        ("uvicorn", "uvicorn[standard]>=0.30.0"),
        ("multipart", "python-multipart>=0.0.9"),
    ]
    return [
        (module, requirement, importlib.util.find_spec(module) is not None)
        for module, requirement in checks
    ]


def pip_check_command() -> int:
    missing = [(m, r) for m, r, ok in _pip_check_required_deps() if not ok]
    if not missing:
        print("[OK] All ticket API dependencies are installed.")
        return 0
    print("[FAIL] Missing required dependencies:")
    for module, requirement in missing:
        print(f"  - {module}: {requirement}")
    requirements = " ".join(r for _, r in missing)
    print(f"Install: {sys.executable} -m pip install {requirements}")
    return 1


def doctor_command() -> int:
    multipart_ok = _has_python_multipart()
    db_file = Path(db_path())
    db_ok = db_file.exists()
    table_ok = False
    table_error: str | None = None

    if db_ok:
        try:
            db.ensure_indexes(db_path())
            with sqlite3.connect(db_file) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='scrape_jobs'"
                ).fetchone()
                table_ok = bool(row and row[0] > 0)
        except Exception as exc:
            table_error = str(exc)

    if multipart_ok:
        print("[OK] python-multipart is installed.")
    else:
        print(f"[FAIL] {_missing_python_multipart_message()}", file=sys.stderr)

    if db_ok:
        print(f"[OK] Ticket DB path exists: {db_file}")
    else:
        print(f"[FAIL] Ticket DB path missing: {db_file}", file=sys.stderr)

    if table_ok:
        print("[OK] scrape_jobs table is ready.")
    else:
        msg = "scrape_jobs table check failed" if table_error else "scrape_jobs table missing"
        detail = f": {table_error}" if table_error else ""
        print(f"[FAIL] {msg}{detail}", file=sys.stderr)

    return 0 if multipart_ok and db_ok and table_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=db_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--doctor", action="store_true",
                        help="Validate API runtime dependencies and exit")
    parser.add_argument("--pip-check", action="store_true",
                        help="Print missing dependencies and pip install command")
    args = parser.parse_args()
    if args.pip_check:
        raise SystemExit(pip_check_command())
    if args.doctor:
        raise SystemExit(doctor_command())
    run_api(host=args.host, port=args.port, reload=args.reload, db_override=args.db)


if __name__ == "__main__":
    main()
