"""Drop-in replacement for ticket_api.db that sends writes to a remote server.

Configure with env vars:
  INGEST_SERVER_URL  — base URL of the server running ticket_api (e.g. http://10.0.0.5:8788)
  INGEST_API_KEY     — must match the server's INGEST_API_KEY

All write operations POST to /api/ingest/* on the server.
Read operations proxy to the server's existing GET endpoints.
The db_path argument accepted by every function is ignored (no local SQLite).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import requests as _requests

_LOG = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────


def _server_url() -> str:
    return os.getenv("INGEST_SERVER_URL", "http://127.0.0.1:8788").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.getenv("INGEST_API_KEY", "")
    h: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        h["X-Ingest-Key"] = key
    return h


def _post(path: str, body: dict[str, Any], *, timeout: int = 6) -> dict[str, Any]:
    url = f"{_server_url()}{path}"
    try:
        resp = _requests.post(url, json=body, headers=_headers(), timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        _LOG.error("ingest POST %s failed: %s", path, exc)
        raise


def _post_queued(path: str, body: dict[str, Any], *, timeout: int = 6) -> dict[str, Any]:
    """POST to server; on failure queue payload locally and return {} without raising."""
    try:
        return _post(path, body, timeout=timeout)
    except Exception:
        _queue_locally(path, body)
        return {}


def _get(path: str, *, timeout: int = 6, **params: Any) -> Any:
    url = f"{_server_url()}{path}"
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        resp = _requests.get(url, params=clean, headers=_headers(), timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        _LOG.error("ingest GET %s failed: %s", path, exc)
        raise


# ── Offline write-ahead queue ─────────────────────────────────────────────────

_QUEUE_DB: Path = (
    Path(os.getenv("CLIENT_QUEUE_DB") or "")
    if os.getenv("CLIENT_QUEUE_DB")
    else Path(__file__).resolve().parents[3] / "var" / "client_queue.db"
)
_queue_lock = threading.Lock()


def _queue_locally(endpoint: str, body: dict[str, Any]) -> None:
    """Buffer a failed POST to local SQLite so it can be retried when the server returns."""
    try:
        _QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
        with _queue_lock:
            con = sqlite3.connect(str(_QUEUE_DB))
            con.execute(
                "CREATE TABLE IF NOT EXISTS queue "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT, payload TEXT, created_utc TEXT)"
            )
            con.execute(
                "INSERT INTO queue (endpoint, payload, created_utc) VALUES (?,?,datetime('now'))",
                (endpoint, json.dumps(body)),
            )
            con.commit()
            con.close()
    except Exception as exc:
        _LOG.error("queue_locally failed endpoint=%s error=%s", endpoint, exc)


def _drain_queue() -> None:
    """Flush queued payloads to the server; stops at the first failure."""
    if not _QUEUE_DB.exists():
        return
    with _queue_lock:
        con = sqlite3.connect(str(_QUEUE_DB))
        rows = con.execute(
            "SELECT id, endpoint, payload FROM queue ORDER BY id LIMIT 50"
        ).fetchall()
        for row_id, endpoint, payload_str in rows:
            try:
                body = json.loads(payload_str)
                url = f"{_server_url()}{endpoint}"
                resp = _requests.post(url, json=body, headers=_headers(), timeout=30)
                resp.raise_for_status()
                con.execute("DELETE FROM queue WHERE id=?", (row_id,))
                con.commit()
            except Exception:
                break  # Server still unreachable; retry next cycle
        con.close()


def _start_retry_thread() -> None:
    def _loop() -> None:
        while True:
            time.sleep(60)
            try:
                _drain_queue()
            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True, name="db-client-retry").start()


_start_retry_thread()

# ── Schema / init (no-ops — server owns its schema) ──────────────────────────


def ensure_indexes(db_path: str) -> None:  # noqa: ARG001
    pass


def ensure_handle_row(db_path: str, handle: str) -> None:  # noqa: ARG001
    upsert_discovered_handles(db_path, [{"handle": handle}])


# ── Handle writes ─────────────────────────────────────────────────────────────


def upsert_discovered_handles(db_path: str, rows: list[dict[str, Any]]) -> int:  # noqa: ARG001
    if not rows:
        return 0
    r = _post_queued("/api/ingest/handles", {"rows": rows})
    return int(r.get("inserted", 0))


def update_handle_progress(
    db_path: str,
    handle: str,
    *,
    status: str,
    error: str | None = None,
    last_updated_utc: str | None = None,
    ticket_count: int | None = None,
    last_run_id: str | None = None,
) -> None:
    _post_queued(
        "/api/ingest/handle-progress",
        {
            "handle": handle,
            "status": status,
            "error": error,
            "last_updated_utc": last_updated_utc,
            "ticket_count": ticket_count,
            "last_run_id": last_run_id,
        },
    )


# ── Ticket writes ─────────────────────────────────────────────────────────────


def upsert_tickets_batch(
    db_path: str,  # noqa: ARG001
    handle: str,
    rows: list[dict[str, Any]],
    batch_size: int = 100,  # noqa: ARG001 — server batches internally
) -> int:
    if not rows:
        return 0
    r = _post_queued("/api/ingest/tickets", {"handle": handle, "tickets": rows})
    return int(r.get("inserted", 0))


# ── Event / log writes ────────────────────────────────────────────────────────


def add_event(
    db_path: str,  # noqa: ARG001
    created_utc: str,
    level: str,
    handle: str | None,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    _post_queued(
        "/api/ingest/event",
        {"created_utc": created_utc, "level": level, "handle": handle, "message": message, "meta": meta},
    )


# ── Scrape job writes ─────────────────────────────────────────────────────────


def create_scrape_job(
    db_path: str,  # noqa: ARG001
    job_id: str,
    handle: str | None,
    mode: str,
    ticket_limit: int | None,
    status: str,
    created_utc: str,
    ticket_id: str | None = None,
    handles: list[str] | None = None,
) -> None:
    _post_queued(
        "/api/ingest/job/create",
        {
            "job_id": job_id,
            "handle": handle,
            "mode": mode,
            "ticket_limit": ticket_limit,
            "status": status,
            "created_utc": created_utc,
            "ticket_id": ticket_id,
            "handles": handles,
        },
    )


def update_scrape_job(
    db_path: str,  # noqa: ARG001
    job_id: str,
    *,
    status: str,
    progress_completed: int,
    progress_total: int,
    started_utc: str | None = None,
    finished_utc: str | None = None,
    error_message: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    _post_queued(
        "/api/ingest/job/update",
        {
            "job_id": job_id,
            "status": status,
            "progress_completed": progress_completed,
            "progress_total": progress_total,
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "error_message": error_message,
            "result": result,
        },
    )


def add_scrape_event(
    db_path: str,  # noqa: ARG001
    job_id: str,
    ts_utc: str,
    level: str,
    event: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    _post_queued(
        "/api/ingest/job/event",
        {"job_id": job_id, "ts_utc": ts_utc, "level": level, "event": event, "message": message, "data": data},
    )


# ── NOC / VPBX writes ─────────────────────────────────────────────────────────


def upsert_noc_queue_tickets(
    db_path: str,  # noqa: ARG001
    records: list[dict[str, Any]],
    now_utc: str,
) -> int:
    if not records:
        return 0
    r = _post_queued("/api/ingest/noc-queue", {"records": records, "now_utc": now_utc})
    return int(r.get("inserted", 0))


def upsert_vpbx_records(
    db_path: str,  # noqa: ARG001
    records: list[dict[str, Any]],
    now_utc: str,
) -> int:
    if not records:
        return 0
    r = _post_queued("/api/ingest/vpbx/records", {"records": records, "now_utc": now_utc})
    return int(r.get("inserted", 0))


def upsert_vpbx_device_configs(
    db_path: str,  # noqa: ARG001
    records: list[dict[str, Any]],
    now_utc: str,
) -> int:
    if not records:
        return 0
    r = _post_queued("/api/ingest/vpbx/device-configs", {"records": records, "now_utc": now_utc})
    return int(r.get("inserted", 0))


def upsert_vpbx_site_configs(
    db_path: str,  # noqa: ARG001
    records: list[dict[str, Any]],
    now_utc: str,
) -> int:
    if not records:
        return 0
    r = _post_queued("/api/ingest/vpbx/site-configs", {"records": records, "now_utc": now_utc})
    return int(r.get("inserted", 0))


def upsert_orders(
    db_path: str,  # noqa: ARG001
    records: list[dict[str, Any]],
    now_utc: str,
) -> int:
    if not records:
        return 0
    r = _post_queued("/api/ingest/orders", {"records": records, "now_utc": now_utc})
    return int(r.get("inserted", 0))


def list_orders(
    db_path: str,  # noqa: ARG001
    assigned_to: str | None = None,
    order_type: str | None = None,
    from_date: str | None = None,
) -> list[dict[str, Any]]:
    try:
        r = _get("/api/orders", assigned_to=assigned_to, order_type=order_type, from_date=from_date)
        return r.get("orders", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


# ── Auth cookies (stay local — used for scraping, not stored on server) ───────


def replace_auth_cookies(
    db_path: str,  # noqa: ARG001
    cookies: list[dict[str, Any]],
    created_utc: str,
    source: str = "none",
) -> None:
    pass  # Cookies are auth material; they live on the client only.


def clear_auth_cookies(db_path: str) -> None:  # noqa: ARG001
    pass


def get_auth_cookies(db_path: str) -> list[dict[str, Any]]:  # noqa: ARG001
    return []


def get_auth_cookie_status(db_path: str) -> dict[str, Any]:  # noqa: ARG001
    return {"count": 0, "domains": [], "created_utc": None, "last_loaded": None, "source": "client"}


# ── Read proxies (hit server GET endpoints) ───────────────────────────────────


_stats_cache: dict[str, Any] = {}
_stats_cache_ts: float = 0.0


def get_stats(db_path: str) -> dict[str, Any]:  # noqa: ARG001
    global _stats_cache, _stats_cache_ts
    now = time.monotonic()
    if now - _stats_cache_ts < 30:
        return _stats_cache
    try:
        result = _get("/api/system/status")
        _stats_cache = result
        _stats_cache_ts = now
        return result
    except Exception:
        _stats_cache_ts = now  # Don't hammer on repeated failures
        return _stats_cache


def get_debug_db_payload(db_path: str) -> dict[str, Any]:  # noqa: ARG001
    try:
        return _get("/api/db/status")
    except Exception:
        return {}


def list_handles(
    db_path: str,  # noqa: ARG001
    q: str = "",
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    r = _get("/api/handles", q=q, limit=limit, offset=offset)
    return r.get("items", r) if isinstance(r, dict) else (r or [])


def list_handles_summary(
    db_path: str,  # noqa: ARG001
    q: str = "",
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    r = _get("/api/handles/summary", q=q, limit=limit, offset=offset)
    return r.get("items", r) if isinstance(r, dict) else (r or [])


def list_handle_names(db_path: str, q: str = "", limit: int = 500) -> list[str]:
    rows = list_handles(db_path, q=q, limit=limit)
    return [str(row["handle"]) for row in rows if row.get("handle")]


def list_all_handles(db_path: str) -> list[str]:
    return list_handle_names(db_path, limit=5000)


def handle_exists(db_path: str, handle: str) -> bool:
    rows = list_handles(db_path, q=handle, limit=10)
    return any(row.get("handle") == handle for row in rows)


def get_handle(db_path: str, handle: str) -> dict[str, Any] | None:
    rows = list_handles(db_path, q=handle, limit=10)
    for row in rows:
        if row.get("handle") == handle:
            return row
    return None


def get_handle_latest(db_path: str, handle: str) -> dict[str, Any] | None:
    try:
        return _get(f"/api/handles/{handle}/latest")
    except Exception:
        return None


def list_runs(db_path: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ARG001
    return []


def list_tickets(
    db_path: str,  # noqa: ARG001
    handle: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "newest",
) -> dict[str, Any]:
    r = _get(
        "/api/tickets",
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return r if isinstance(r, dict) else {"items": [], "totalCount": 0, "page": page, "pageSize": page_size}


def get_ticket(db_path: str, ticket_id: str, handle: str | None = None) -> dict[str, Any] | None:
    try:
        return _get(f"/api/tickets/{ticket_id}", handle=handle)
    except Exception:
        return None


def get_artifacts(db_path: str, ticket_id: str, handle: str) -> list[dict[str, Any]]:
    return []


def list_scrape_jobs(db_path: str, limit: int = 20) -> list[dict[str, Any]]:  # noqa: ARG001
    try:
        r = _get("/api/jobs", limit=limit)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


def get_latest_scrape_job(db_path: str) -> dict[str, Any] | None:
    jobs = list_scrape_jobs(db_path, limit=1)
    return jobs[0] if jobs else None


def get_scrape_job(db_path: str, job_id: str) -> dict[str, Any] | None:
    try:
        return _get(f"/api/jobs/{job_id}")
    except Exception:
        return None


def get_scrape_events(db_path: str, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
    try:
        r = _get(f"/api/jobs/{job_id}/events", limit=limit)
        if isinstance(r, dict):
            return r.get("events", r.get("items", []))
        return r or []
    except Exception:
        return []


def get_latest_events(db_path: str, limit: int = 50) -> list[dict[str, Any]]:
    try:
        r = _get("/api/events", limit=limit)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


def get_company(db_path: str, handle: str) -> dict[str, Any] | None:
    try:
        return _get(f"/api/companies/{handle}")
    except Exception:
        return None


def get_company_timeline(db_path: str, handle: str, limit: int = 500) -> list[dict[str, Any]]:
    try:
        r = _get(f"/api/companies/{handle}/timeline", limit=limit)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


# ── VPBX reads (used by the scraper to compare against existing data) ─────────


def list_vpbx_records(db_path: str) -> list[dict[str, Any]]:  # noqa: ARG001
    try:
        r = _get("/api/vpbx/records")
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


def list_vpbx_device_configs(
    db_path: str,  # noqa: ARG001
    handle: str | None = None,
) -> list[dict[str, Any]]:
    try:
        r = _get("/api/vpbx/device-configs", handle=handle)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


def list_vpbx_site_configs(
    db_path: str,  # noqa: ARG001
    handle: str | None = None,
) -> list[dict[str, Any]]:
    try:
        r = _get("/api/vpbx/site-configs", handle=handle)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


def list_noc_queue_tickets(
    db_path: str,  # noqa: ARG001
    view: str | None = None,
) -> list[dict[str, Any]]:
    try:
        r = _get("/api/noc-queue/records", view=view)
        return r.get("items", r) if isinstance(r, dict) else (r or [])
    except Exception:
        return []


# ── Stubs for less-common functions (no-ops or safe defaults on client) ───────


def upsert_company(
    db_path: str,  # noqa: ARG001
    handle: str,
    name: str | None = None,
    last_ingest_job_id: str | None = None,
    now_utc: str | None = None,
) -> None:
    pass


def replace_ticket_events(
    db_path: str,  # noqa: ARG001
    handle: str,
    events: list[dict[str, Any]],
    now_utc: str,
) -> int:
    return 0


def replace_company_timeline(
    db_path: str,  # noqa: ARG001
    handle: str,
    timeline_rows: list[dict[str, Any]],
    now_utc: str,
) -> int:
    return 0


def replace_resolution_patterns(
    db_path: str,  # noqa: ARG001
    handle: str,
    patterns: list[dict[str, Any]],
    now_utc: str,
) -> int:
    return 0


def delete_handle(db_path: str, handle: str) -> bool:  # noqa: ARG001
    return False


def save_sidecar_config(db_path: str, device_id: str, vpbx_id: str, sidecar_config: str) -> bool:  # noqa: ARG001
    return False


def explain_list_tickets_plan(
    db_path: str,  # noqa: ARG001
    handle: str | None = None,
    status: str | None = None,
) -> list[str]:
    return []


def safe_artifact_path(requested_path: str, output_root: str):
    from pathlib import Path

    root = Path(output_root).resolve()
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    return None


# ── Client heartbeat ──────────────────────────────────────────────────────────


def upsert_client_heartbeat(
    db_path: str,  # noqa: ARG001
    client_id: str,
    status: str,
    vpn_connected: bool,
    vpn_ip: str | None,
    job_id: str | None,
    current_handle: str | None,
    handles_done: int | None,
    handles_total: int | None,
    ts_utc: str,
) -> None:
    _post_queued(
        "/api/ingest/heartbeat",
        {
            "client_id":      client_id,
            "status":         status,
            "vpn_connected":  vpn_connected,
            "vpn_ip":         vpn_ip,
            "job_id":         job_id,
            "current_handle": current_handle,
            "handles_done":   handles_done if handles_done is not None else 0,
            "handles_total":  handles_total if handles_total is not None else 0,
            "ts_utc":         ts_utc,
        },
    )


def list_client_heartbeats(db_path: str) -> list[dict[str, Any]]:  # noqa: ARG001
    try:
        data = _get("/api/clients")
        return data.get("items", []) if isinstance(data, dict) else data
    except Exception:
        return []
