from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

WRITE_LOCK = threading.Lock()


def get_conn(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {str(row["name"]) for row in rows}


def build_last_activity_expr(cols: set[str]) -> str:
    priority_columns = ["updated_utc", "created_utc", "opened_utc"]
    qualified = [f"t.{column}" for column in priority_columns if column in cols]
    if not qualified:
        return "MAX(NULL)"
    return f"MAX(COALESCE({', '.join(qualified)}))"


def ensure_indexes(db_path: str) -> None:
    with WRITE_LOCK:
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
                    handle TEXT,
                    mode TEXT NOT NULL,
                    ticket_id TEXT,
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

                CREATE TABLE IF NOT EXISTS scrape_job_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    ts_utc TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT,
                    data_json TEXT
                );
                """
            )

            tickets_columns = table_columns(conn, "tickets")
            for expected_column in [
                "title",
                "subject",
                "status",
                "opened_utc",
                "created_utc",
                "updated_utc",
                "raw_row_json",
            ]:
                if expected_column not in tickets_columns:
                    conn.execute(f"ALTER TABLE tickets ADD COLUMN {expected_column} TEXT")

            scrape_columns = table_columns(conn, "scrape_jobs")
            if "ticket_id" not in scrape_columns:
                conn.execute("ALTER TABLE scrape_jobs ADD COLUMN ticket_id TEXT")

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_handles_last_scrape ON handles(last_scrape_utc);
                CREATE INDEX IF NOT EXISTS idx_handles_status ON handles(last_status);
                CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated ON tickets(handle, updated_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_tickets_handle_status_updated ON tickets(handle, status, updated_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_finished ON runs(finished_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_scrape_jobs_created ON scrape_jobs(created_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_scrape_events_job_id ON scrape_job_events(job_id, id DESC);
                """
            )


def list_handles(db_path: str, q: str = "", limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        tickets_columns = table_columns(conn, "tickets")
        last_ticket_expr = build_last_activity_expr(tickets_columns)
        query = f"""
        WITH all_handles AS (
            SELECT handle FROM handles
            UNION
            SELECT DISTINCT handle FROM tickets
        ), ticket_summary AS (
            SELECT t.handle, COUNT(*) AS tickets_count,
                   SUM(CASE WHEN LOWER(COALESCE(t.status, ''))='open' THEN 1 ELSE 0 END) AS open_count,
                   {last_ticket_expr} AS last_ticket_at
            FROM tickets t GROUP BY t.handle
        )
        SELECT ah.handle, COALESCE(ts.tickets_count,0) AS ticketsCount, COALESCE(ts.open_count,0) AS openCount,
               ts.last_ticket_at AS lastTicketAt, h.last_scrape_utc AS lastScrapeAt, h.last_status AS status, h.last_error AS last_message
        FROM all_handles ah LEFT JOIN handles h ON h.handle=ah.handle LEFT JOIN ticket_summary ts ON ts.handle=ah.handle
        """
        params: list[Any] = []
        if q:
            query += " WHERE ah.handle LIKE ?"
            params.append(f"%{q}%")
        query += " ORDER BY ah.handle LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def list_handle_names(db_path: str, q: str = "", limit: int = 500) -> list[str]:
    query = "SELECT handle FROM (SELECT handle FROM handles UNION SELECT handle FROM tickets) merged"
    params: list[Any] = []
    if q:
        query += " WHERE merged.handle LIKE ?"
        params.append(f"%{q}%")
    query += " ORDER BY merged.handle ASC LIMIT ?"
    params.append(max(1, min(limit, 5000)))
    with get_conn(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [str(r["handle"]) for r in rows]


def list_all_handles(db_path: str) -> list[str]:
    return list_handle_names(db_path, limit=5000)


def handle_exists(db_path: str, handle: str) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT 1 FROM (SELECT handle FROM handles WHERE handle=? UNION SELECT handle FROM tickets WHERE handle=?) LIMIT 1", (handle, handle)).fetchone()
    return bool(row)


def get_handle(db_path: str, handle: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM handles WHERE handle=?", (handle,)).fetchone()
    return dict(row) if row else None


def list_tickets(db_path: str, handle: str | None = None, status: str | None = None, q: str | None = None, from_utc: str | None = None, to_utc: str | None = None, page: int = 1, page_size: int = 50, sort: str = "newest") -> dict[str, Any]:
    where = ["1=1"]
    params: list[Any] = []
    if handle:
        where.append("handle=?")
        params.append(handle)
    if status and status != "any":
        where.append("status=?")
        params.append(status)
    if q:
        like = f"%{q}%"
        where.append("(ticket_id LIKE ? OR title LIKE ? OR subject LIKE ? OR ticket_url LIKE ?)")
        params.extend([like, like, like, like])
    if from_utc:
        where.append("updated_utc >= ?")
        params.append(from_utc)
    if to_utc:
        where.append("updated_utc <= ?")
        params.append(to_utc)
    where_clause = " AND ".join(where)
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size
    order = "updated_utc DESC, ticket_id DESC"
    if sort in {"oldest", "updated_oldest"}:
        order = "updated_utc ASC, ticket_id ASC"
    with get_conn(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM tickets WHERE {where_clause}", params).fetchone()["count"]
        rows = conn.execute(f"SELECT * FROM tickets WHERE {where_clause} ORDER BY {order} LIMIT ? OFFSET ?", [*params, page_size, offset]).fetchall()
    return {"items": [dict(r) for r in rows], "totalCount": total, "page": page, "pageSize": page_size}


def create_scrape_job(db_path: str, job_id: str, handle: str | None, mode: str, ticket_limit: int | None, status: str, created_utc: str, ticket_id: str | None = None) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("INSERT INTO scrape_jobs(job_id, handle, mode, ticket_id, ticket_limit, status, created_utc) VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, handle, mode, ticket_id, ticket_limit, status, created_utc))


def update_scrape_job(db_path: str, job_id: str, *, status: str, progress_completed: int, progress_total: int, started_utc: str | None = None, finished_utc: str | None = None, error_message: str | None = None, result: dict[str, Any] | None = None) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("""
            UPDATE scrape_jobs SET status=?, progress_completed=?, progress_total=?, started_utc=COALESCE(?, started_utc),
            finished_utc=COALESCE(?, finished_utc), error_message=?, result_json=? WHERE job_id=?
            """, (status, progress_completed, progress_total, started_utc, finished_utc, error_message, json.dumps(result, sort_keys=True) if result is not None else None, job_id))


def add_scrape_event(db_path: str, job_id: str, ts_utc: str, level: str, event: str, message: str, data: dict[str, Any] | None = None) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("INSERT INTO scrape_job_events(job_id, ts_utc, level, event, message, data_json) VALUES (?, ?, ?, ?, ?, ?)", (job_id, ts_utc, level, event, message, json.dumps(data, sort_keys=True) if data else None))


def get_scrape_events(db_path: str, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM scrape_job_events WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, limit)).fetchall()
    out=[]
    for row in reversed(rows):
        item = dict(row)
        item["data"] = json.loads(item["data_json"]) if item.get("data_json") else None
        out.append(item)
    return out


def get_latest_scrape_job(db_path: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scrape_jobs ORDER BY created_utc DESC LIMIT 1").fetchone()
    if not row:
        return None
    payload=dict(row)
    payload["result"] = json.loads(payload["result_json"]) if payload.get("result_json") else None
    return payload


def get_scrape_job(db_path: str, job_id: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scrape_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["result"] = json.loads(payload["result_json"]) if payload.get("result_json") else None
    return payload


def get_ticket(db_path: str, ticket_id: str, handle: str | None = None) -> dict[str, Any] | None:
    q = "SELECT * FROM tickets WHERE ticket_id=? ORDER BY updated_utc DESC LIMIT 1"
    params: tuple[Any,...]=(ticket_id,)
    if handle:
        q = "SELECT * FROM tickets WHERE ticket_id=? AND handle=? LIMIT 1"
        params=(ticket_id, handle)
    with get_conn(db_path) as conn:
        row = conn.execute(q, params).fetchone()
    return dict(row) if row else None


def get_artifacts(db_path: str, ticket_id: str, handle: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        try:
            rows=conn.execute("SELECT * FROM ticket_artifacts WHERE ticket_id=? AND handle=? ORDER BY created_utc DESC", (ticket_id, handle)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]


def get_stats(db_path: str) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        total_tickets = conn.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()["count"]
        total_handles = conn.execute("SELECT COUNT(*) AS count FROM handles").fetchone()["count"]
        total_runs = conn.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]
        total_jobs = conn.execute("SELECT COUNT(*) AS count FROM scrape_jobs").fetchone()["count"]
        try:
            total_artifacts = conn.execute("SELECT COUNT(*) AS count FROM ticket_artifacts").fetchone()["count"]
        except sqlite3.OperationalError:
            total_artifacts = 0
        last_updated = conn.execute("SELECT MAX(updated_utc) AS updated_utc FROM tickets").fetchone()["updated_utc"]
    return {"total_tickets": total_tickets, "total_handles": total_handles, "total_runs": total_runs, "total_scrape_jobs": total_jobs, "total_artifacts": total_artifacts, "last_updated_utc": last_updated}


def get_debug_db_payload(db_path: str) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        def cnt(table:str)->int:
            try:
                return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            except sqlite3.OperationalError:
                return 0
        counts = {"handles": cnt("handles"), "tickets": cnt("tickets"), "ticket_artifacts": cnt("ticket_artifacts"), "runs": cnt("runs"), "scrape_jobs": cnt("scrape_jobs")}
        try:
            last_ticket = conn.execute("SELECT MAX(updated_utc) AS v FROM tickets").fetchone()["v"]
        except sqlite3.OperationalError:
            last_ticket = None
        try:
            last_handle = conn.execute("SELECT MAX(last_scrape_utc) AS v FROM handles").fetchone()["v"]
        except sqlite3.OperationalError:
            last_handle = None
    return {"dbPathAbs": str(Path(db_path).resolve()), "tables": tables, "counts": counts, "lastTicketUpdated": last_ticket, "lastHandleRun": last_handle}


def safe_artifact_path(requested_path: str, output_root: str) -> Path | None:
    root = Path(output_root).resolve()
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    return None
