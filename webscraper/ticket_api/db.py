from __future__ import annotations

import json
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
            CREATE TABLE IF NOT EXISTS scrape_jobs(
                job_id TEXT PRIMARY KEY,
                handle TEXT NOT NULL,
                mode TEXT NOT NULL,
                ticket_limit INTEGER,
                status TEXT NOT NULL,
                progress_completed INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 1,
                started_utc TEXT,
                finished_utc TEXT,
                error_message TEXT,
                result_json TEXT,
                created_utc TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_handles_last_scrape ON handles(last_scrape_utc);
            CREATE INDEX IF NOT EXISTS idx_handles_status ON handles(last_status);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle ON tickets(handle);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated ON tickets(handle, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_created ON tickets(handle, created_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets(updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_ticket_id ON tickets(ticket_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_runs_finished ON runs(finished_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_scrape_jobs_created ON scrape_jobs(created_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_scrape_jobs_handle_created ON scrape_jobs(handle, created_utc DESC);
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS tickets_fts
                USING fts5(ticket_id, handle, title, subject, ticket_url, raw_json, content='tickets', content_rowid='rowid')
                """
            )
            conn.execute("INSERT INTO tickets_fts(tickets_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            # FTS is optional; fallback LIKE search remains available.
            pass


def list_handles(db_path: str, q: str = "", limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    summary_query = """
        WITH all_handles AS (
            SELECT handle FROM handles
            UNION
            SELECT DISTINCT handle FROM tickets
        ),
        ticket_summary AS (
            SELECT
                t.handle,
                COUNT(*) AS tickets_count,
                MAX(COALESCE(t.updated_utc, t.created_utc, t.opened_utc)) AS last_ticket_at
            FROM tickets t
            GROUP BY t.handle
        )
        SELECT
            ah.handle,
            COALESCE(ts.tickets_count, 0) AS ticketsCount,
            ts.last_ticket_at AS lastTicketAt,
            h.last_scrape_utc AS lastScrapeAt,
            h.last_status AS status
        FROM all_handles ah
        LEFT JOIN handles h ON h.handle = ah.handle
        LEFT JOIN ticket_summary ts ON ts.handle = ah.handle
    """
    params: list[Any] = []
    if q:
        summary_query += " WHERE ah.handle LIKE ?"
        params.append(f"%{q}%")
    summary_query += " ORDER BY ah.handle LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(summary_query, params).fetchall()]


def list_all_handles(db_path: str) -> list[str]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT handle FROM (
                SELECT handle FROM handles
                UNION
                SELECT DISTINCT handle FROM tickets
            )
            ORDER BY handle
            """
        ).fetchall()
    return [row["handle"] for row in rows]


def get_handle(db_path: str, handle: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM handles WHERE handle=?", (handle,)).fetchone()
        return dict(row) if row else None


def list_tickets(
    db_path: str,
    handle: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "newest",
) -> dict[str, Any]:
    where = ["1=1"]
    params: list[Any] = []

    if handle:
        where.append("handle=?")
        params.append(handle)

    if status:
        where.append("status=?")
        params.append(status)
    with get_conn(db_path) as conn:
        use_fts = bool(
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tickets_fts' LIMIT 1").fetchone()
        )

    if q:
        if use_fts:
            where.append(
                "(rowid IN (SELECT rowid FROM tickets_fts WHERE tickets_fts MATCH ?) OR title LIKE ? OR subject LIKE ? OR ticket_url LIKE ? OR raw_json LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([q, like, like, like, like])
        else:
            where.append("(title LIKE ? OR subject LIKE ? OR ticket_url LIKE ? OR raw_json LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
    if from_utc:
        where.append("COALESCE(updated_utc, created_utc, opened_utc) >= ?")
        params.append(from_utc)
    if to_utc:
        where.append("COALESCE(updated_utc, created_utc, opened_utc) <= ?")
        params.append(to_utc)

    where_clause = " AND ".join(where)

    order_by = "COALESCE(updated_utc, created_utc, opened_utc) DESC"
    if sort == "oldest":
        order_by = "COALESCE(updated_utc, created_utc, opened_utc) ASC"

    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size

    with get_conn(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM tickets WHERE {where_clause}",
            params,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT * FROM tickets
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "totalCount": total,
        "page": page,
        "pageSize": page_size,
    }


def create_scrape_job(
    db_path: str,
    job_id: str,
    handle: str,
    mode: str,
    ticket_limit: int | None,
    status: str,
    created_utc: str,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scrape_jobs(job_id, handle, mode, ticket_limit, status, created_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, handle, mode, ticket_limit, status, created_utc),
        )


def update_scrape_job(
    db_path: str,
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
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE scrape_jobs
            SET status=?, progress_completed=?, progress_total=?, started_utc=COALESCE(?, started_utc),
                finished_utc=COALESCE(?, finished_utc), error_message=?, result_json=?
            WHERE job_id=?
            """,
            (
                status,
                progress_completed,
                progress_total,
                started_utc,
                finished_utc,
                error_message,
                json.dumps(result, sort_keys=True) if result is not None else None,
                job_id,
            ),
        )


def get_scrape_job(db_path: str, job_id: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scrape_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    result_json = payload.get("result_json")
    payload["result"] = json.loads(result_json) if result_json else None
    return payload


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
