from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_handles(db_path: str, search: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    query = "SELECT * FROM handles"
    params: list[Any] = []
    if search:
        query += " WHERE handle LIKE ?"
        params.append(f"%{search}%")
    query += " ORDER BY handle LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_handle(db_path: str, handle: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM handles WHERE handle=?", (handle,)).fetchone()
        return dict(row) if row else None


def list_tickets(
    db_path: str,
    handle: str,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM tickets WHERE handle=?"
    params: list[Any] = [handle]
    if status:
        query += " AND status=?"
        params.append(status)
    if q:
        query += " AND (title LIKE ? OR ticket_url LIKE ? OR raw_json LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if from_utc:
        query += " AND COALESCE(updated_utc, created_utc) >= ?"
        params.append(from_utc)
    if to_utc:
        query += " AND COALESCE(updated_utc, created_utc) <= ?"
        params.append(to_utc)
    query += " ORDER BY COALESCE(updated_utc, created_utc) DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_ticket(db_path: str, ticket_id: str, handle: str | None = None) -> dict[str, Any] | None:
    if handle:
        query = "SELECT * FROM tickets WHERE ticket_id=? AND handle=? LIMIT 1"
        params: tuple[Any, ...] = (ticket_id, handle)
    else:
        query = "SELECT * FROM tickets WHERE ticket_id=? ORDER BY updated_utc DESC LIMIT 1"
        params = (ticket_id,)
    with get_conn(db_path) as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def get_artifacts(db_path: str, ticket_id: str, handle: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM ticket_artifacts WHERE ticket_id=? AND handle=? ORDER BY created_utc DESC",
            (ticket_id, handle),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats(db_path: str) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        statuses = {
            row["status"] or "unknown": row["count"]
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM tickets GROUP BY status")
        }
        total_tickets = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        total_handles = conn.execute("SELECT COUNT(*) FROM handles").fetchone()[0]
        last_run = conn.execute("SELECT MAX(finished_utc) FROM runs").fetchone()[0]
    return {
        "total_tickets": total_tickets,
        "total_handles": total_handles,
        "last_run_finished_utc": last_run,
        "counts_by_status": statuses,
    }


def safe_artifact_path(requested_path: str, output_root: str) -> Path | None:
    root = Path(output_root).resolve()
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    return None
