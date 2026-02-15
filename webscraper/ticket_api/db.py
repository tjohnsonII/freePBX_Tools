from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def get_conn(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_indexes(db_path: str) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS handles(
                handle TEXT PRIMARY KEY,
                first_seen_utc TEXT,
                last_scrape_utc TEXT,
                last_status TEXT,
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS runs(
                run_id TEXT PRIMARY KEY,
                started_utc TEXT,
                finished_utc TEXT,
                args_json TEXT,
                out_dir TEXT,
                failure_reason TEXT,
                git_sha TEXT,
                host TEXT
            );

            CREATE TABLE IF NOT EXISTS tickets(
                ticket_id TEXT,
                handle TEXT,
                ticket_url TEXT,
                ticket_num TEXT,
                title TEXT,
                subject TEXT,
                status TEXT,
                opened_utc TEXT,
                created_utc TEXT,
                updated_utc TEXT,
                raw_json TEXT,
                raw_row_json TEXT,
                run_id TEXT,
                PRIMARY KEY(ticket_id, handle),
                UNIQUE(ticket_url, handle)
            );

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
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated ON tickets(handle, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_status_updated ON tickets(handle, status, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_status_updated ON tickets(status, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_created ON tickets(handle, created_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_ticket_id ON tickets(ticket_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_ticket_id ON tickets(handle, ticket_id);
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
                SUM(CASE WHEN LOWER(COALESCE(t.status, '')) = 'open' THEN 1 ELSE 0 END) AS open_count,
                MAX(COALESCE(t.updated_utc, t.created_utc, t.opened_utc)) AS last_ticket_at
            FROM tickets t
            GROUP BY t.handle
        )
        SELECT
            ah.handle,
            COALESCE(ts.tickets_count, 0) AS ticketsCount,
            COALESCE(ts.open_count, 0) AS openCount,
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


def list_handle_names(db_path: str, q: str = "", limit: int = 500) -> list[str]:
    query = """
        SELECT handle FROM (
            SELECT handle FROM handles
            UNION
            SELECT handle FROM tickets
        ) merged
    """
    params: list[Any] = []
    if q:
        query += " WHERE merged.handle LIKE ?"
        params.append(f"%{q}%")
    query += " ORDER BY merged.handle ASC LIMIT ?"
    params.append(max(1, min(limit, 5000)))
    with get_conn(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [str(row["handle"]) for row in rows]


def list_handles_summary(db_path: str, q: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = """
        WITH all_handles AS (
            SELECT handle FROM handles
            UNION
            SELECT DISTINCT handle FROM tickets
        ),
        ticket_summary AS (
            SELECT
                t.handle,
                COUNT(*) AS ticket_count,
                SUM(CASE WHEN LOWER(COALESCE(t.status, '')) = 'open' THEN 1 ELSE 0 END) AS open_count,
                MAX(COALESCE(t.updated_utc, t.created_utc, t.opened_utc)) AS updated_latest_utc
            FROM tickets t
            GROUP BY t.handle
        )
        SELECT
            ah.handle AS handle,
            h.last_scrape_utc AS last_scrape_utc,
            COALESCE(ts.ticket_count, 0) AS ticket_count,
            COALESCE(ts.open_count, 0) AS open_count,
            ts.updated_latest_utc AS updated_latest_utc
        FROM all_handles ah
        LEFT JOIN handles h ON h.handle = ah.handle
        LEFT JOIN ticket_summary ts ON ts.handle = ah.handle
    """
    params: list[Any] = []
    if q:
        query += " WHERE ah.handle LIKE ?"
        params.append(f"%{q}%")
    query += " ORDER BY ah.handle LIMIT ? OFFSET ?"
    params.extend([max(1, min(limit, 500)), max(offset, 0)])
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


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


def handle_exists(db_path: str, handle: str) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM (
                SELECT handle FROM handles WHERE handle = ?
                UNION
                SELECT handle FROM tickets WHERE handle = ?
            ) LIMIT 1
            """,
            (handle, handle),
        ).fetchone()
    return bool(row)


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
    where_clause, params, order_by = _build_list_tickets_query(
        db_path=db_path,
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        sort=sort,
    )

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


def _build_list_tickets_query(
    db_path: str,
    *,
    handle: str | None,
    status: str | None,
    q: str | None,
    from_utc: str | None,
    to_utc: str | None,
    sort: str,
) -> tuple[str, list[Any], str]:
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
        if sort in {"created_newest", "created_oldest"}:
            where.append("created_utc >= ?")
        else:
            where.append("updated_utc >= ?")
        params.append(from_utc)
    if to_utc:
        if sort in {"created_newest", "created_oldest"}:
            where.append("created_utc <= ?")
        else:
            where.append("updated_utc <= ?")
        params.append(to_utc)

    where_clause = " AND ".join(where)

    sort_col = "updated_utc"
    if sort in {"created_newest", "created_oldest"}:
        sort_col = "created_utc"

    order_by = f"{sort_col} DESC, ticket_id DESC, handle DESC"
    if sort == "oldest":
        order_by = f"{sort_col} ASC, ticket_id ASC, handle ASC"
    if sort == "created_oldest":
        order_by = "created_utc ASC, ticket_id ASC, handle ASC"

    return where_clause, params, order_by


def explain_list_tickets_plan(
    db_path: str,
    handle: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    sort: str = "newest",
) -> list[str]:
    where_clause, params, order_clause = _build_list_tickets_query(
        db_path=db_path,
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        sort=sort,
    )
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"EXPLAIN QUERY PLAN SELECT * FROM tickets WHERE {where_clause} ORDER BY {order_clause} LIMIT 10",
            params,
        ).fetchall()
    return [" | ".join(str(col) for col in row) for row in rows]


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
        total_runs = conn.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]
        total_jobs = conn.execute("SELECT COUNT(*) AS count FROM scrape_jobs").fetchone()["count"]
        last_run = conn.execute("SELECT MAX(finished_utc) AS finished_utc FROM runs").fetchone()["finished_utc"]
        try:
            total_artifacts = conn.execute("SELECT COUNT(*) AS count FROM ticket_artifacts").fetchone()["count"]
        except sqlite3.OperationalError:
            total_artifacts = 0
        last_updated = conn.execute(
            "SELECT MAX(COALESCE(updated_utc, created_utc, opened_utc)) AS updated_utc FROM tickets"
        ).fetchone()["updated_utc"]
    return {
        "total_tickets": total_tickets,
        "total_handles": total_handles,
        "total_runs": total_runs,
        "total_scrape_jobs": total_jobs,
        "total_artifacts": total_artifacts,
        "last_run_finished_utc": last_run,
        "last_updated_utc": last_updated,
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
