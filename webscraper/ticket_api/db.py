from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_indexes(db_path: str) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_handles_last_scrape ON handles(last_scrape_utc);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated ON tickets(handle, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_created ON tickets(handle, created_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_ticket_id ON tickets(ticket_id);
            CREATE INDEX IF NOT EXISTS idx_runs_finished ON runs(finished_utc DESC);
            """
        )


def list_handles(db_path: str, q: str = "", limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    summary_query = """
        WITH ticket_summary AS (
            SELECT
                t.handle,
                COUNT(*) AS tickets_count,
                MAX(COALESCE(t.updated_utc, t.created_utc, t.opened_utc)) AS last_ticket_at
            FROM tickets t
            GROUP BY t.handle
        )
        SELECT
            h.handle,
            COALESCE(ts.tickets_count, 0) AS ticketsCount,
            ts.last_ticket_at AS lastTicketAt,
            h.last_scrape_utc AS lastScrapeAt,
            h.last_status AS status
        FROM handles h
        LEFT JOIN ticket_summary ts ON ts.handle = h.handle
    """
    params: list[Any] = []
    if q:
        summary_query += " WHERE h.handle LIKE ?"
        params.append(f"%{q}%")
    summary_query += " ORDER BY h.handle LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(summary_query, params).fetchall()]


def list_all_handles(db_path: str) -> list[str]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT handle FROM handles ORDER BY handle").fetchall()
    return [row["handle"] for row in rows]


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
) -> dict[str, Any]:
    where = ["handle=?"]
    params: list[Any] = [handle]

    if status:
        where.append("status=?")
        params.append(status)
    if q:
        where.append("(title LIKE ? OR ticket_url LIKE ? OR raw_json LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if from_utc:
        where.append("COALESCE(updated_utc, created_utc, opened_utc) >= ?")
        params.append(from_utc)
    if to_utc:
        where.append("COALESCE(updated_utc, created_utc, opened_utc) <= ?")
        params.append(to_utc)

    where_clause = " AND ".join(where)

    with get_conn(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM tickets WHERE {where_clause}",
            params,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT * FROM tickets
            WHERE {where_clause}
            ORDER BY COALESCE(updated_utc, created_utc, opened_utc) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


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
        total_tickets = conn.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()["count"]
        total_handles = conn.execute("SELECT COUNT(*) AS count FROM handles").fetchone()["count"]
        last_run = conn.execute("SELECT MAX(finished_utc) AS finished_utc FROM runs").fetchone()["finished_utc"]
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
