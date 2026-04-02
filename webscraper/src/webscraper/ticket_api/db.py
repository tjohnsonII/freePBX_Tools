from __future__ import annotations

import json
import sqlite3
from typing import Any

from webscraper.ticket_api.db_core import WRITE_LOCK, build_last_activity_expr, get_conn, table_columns


def ensure_indexes(db_path: str) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS handles(
                    handle TEXT PRIMARY KEY,
                    name TEXT,
                    account_status TEXT,
                    ip TEXT,
                    last_seen_utc TEXT,
                    first_seen_utc TEXT,
                    last_scrape_utc TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    last_started_utc TEXT,
                    last_finished_utc TEXT,
                    last_run_id TEXT
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
                    pk TEXT,
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
                    handles_json TEXT,
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

                CREATE TABLE IF NOT EXISTS auth_cookies(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    path TEXT NOT NULL DEFAULT '/',
                    expires INTEGER,
                    secure INTEGER NOT NULL DEFAULT 0,
                    http_only INTEGER NOT NULL DEFAULT 0,
                    expires_utc TEXT,
                    same_site TEXT,
                    created_utc TEXT NOT NULL,
                    updated_at TEXT,
                    source TEXT,
                    UNIQUE(domain, name, path)
                );

                CREATE TABLE IF NOT EXISTS auth_cookie_state(
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_loaded TEXT,
                    source TEXT
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
            if "handles_json" not in scrape_columns:
                conn.execute("ALTER TABLE scrape_jobs ADD COLUMN handles_json TEXT")

            handle_columns = table_columns(conn, "handles")
            for handle_column in ["last_started_utc", "last_finished_utc", "last_run_id"]:
                if handle_column not in handle_columns:
                    conn.execute(f"ALTER TABLE handles ADD COLUMN {handle_column} TEXT")

            for handle_column in ["name", "account_status", "ip", "last_seen_utc"]:
                if handle_column not in handle_columns:
                    conn.execute(f"ALTER TABLE handles ADD COLUMN {handle_column} TEXT")

            # Compatibility columns used by the Ticket History API UI.
            handle_columns = table_columns(conn, "handles")
            compat_handle_columns = {
                "status": "TEXT",
                "error": "TEXT",
                "last_updated_utc": "TEXT",
                "ticket_count": "INTEGER DEFAULT 0",
            }
            for col, ddl in compat_handle_columns.items():
                if col not in handle_columns:
                    conn.execute(f"ALTER TABLE handles ADD COLUMN {col} {ddl}")

            ticket_columns = table_columns(conn, "tickets")
            if "id" not in ticket_columns:
                conn.execute("ALTER TABLE tickets ADD COLUMN id TEXT")
            if "pk" not in ticket_columns:
                conn.execute("ALTER TABLE tickets ADD COLUMN pk TEXT")

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_utc TEXT NOT NULL,
                    level TEXT NOT NULL,
                    handle TEXT,
                    message TEXT NOT NULL,
                    meta_json TEXT
                )
                ;

                CREATE TABLE IF NOT EXISTS companies(
                    handle TEXT PRIMARY KEY,
                    name TEXT,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    last_ingest_job_id TEXT
                );

                CREATE TABLE IF NOT EXISTS ticket_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    ticket_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    event_utc TEXT,
                    summary TEXT NOT NULL,
                    raw_source_text TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS narratives(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    narrative_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ticket_id TEXT,
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_path TEXT,
                    metadata_json TEXT,
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS company_timeline(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    event_utc TEXT,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT,
                    ticket_id TEXT,
                    source_event_id INTEGER,
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS resolution_patterns(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    last_seen_utc TEXT,
                    created_utc TEXT NOT NULL
                );
                """
            )

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_handles_last_scrape ON handles(last_scrape_utc);
                CREATE INDEX IF NOT EXISTS idx_handles_status ON handles(last_status);
                CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated ON tickets(handle, updated_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_tickets_handle_status_updated ON tickets(handle, status, updated_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_finished ON runs(finished_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_scrape_jobs_created ON scrape_jobs(created_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_scrape_events_job_id ON scrape_job_events(job_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_auth_cookies_domain_name ON auth_cookies(domain, name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_cookies_domain_name_path ON auth_cookies(domain, name, path);
                CREATE INDEX IF NOT EXISTS idx_ticket_events_handle_time ON ticket_events(handle, event_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_timeline_handle_time ON company_timeline(handle, event_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_resolution_patterns_handle ON resolution_patterns(handle);
                """
            )

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS noc_queue_tickets (
                    ticket_id TEXT NOT NULL,
                    view TEXT NOT NULL,
                    subject TEXT,
                    status TEXT,
                    opened TEXT,
                    customer TEXT,
                    priority TEXT,
                    assigned_to TEXT,
                    ticket_type TEXT,
                    ticket_id_url TEXT,
                    raw_json TEXT,
                    last_seen_utc TEXT,
                    PRIMARY KEY (ticket_id, view)
                );
                CREATE INDEX IF NOT EXISTS idx_noc_queue_view ON noc_queue_tickets(view);
                CREATE INDEX IF NOT EXISTS idx_noc_queue_status ON noc_queue_tickets(status);
                """
            )

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vpbx_device_configs (
                    device_id TEXT NOT NULL,
                    vpbx_id   TEXT NOT NULL,
                    handle    TEXT,
                    directory_name TEXT,
                    extension TEXT,
                    mac       TEXT,
                    make      TEXT,
                    model     TEXT,
                    site_code TEXT,
                    bulk_config TEXT,
                    last_seen_utc TEXT,
                    PRIMARY KEY (device_id, vpbx_id)
                );
                CREATE INDEX IF NOT EXISTS idx_vpbx_device_handle ON vpbx_device_configs(handle);
                """
            )

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vpbx_records (
                    handle TEXT PRIMARY KEY,
                    name TEXT,
                    account_status TEXT,
                    ip TEXT,
                    web_order TEXT,
                    deployment_id TEXT,
                    switch TEXT,
                    devices TEXT,
                    last_seen_utc TEXT
                );
                """
            )

            auth_cookie_columns = table_columns(conn, "auth_cookies")
            if "expires" not in auth_cookie_columns:
                conn.execute("ALTER TABLE auth_cookies ADD COLUMN expires INTEGER")
            if "updated_at" not in auth_cookie_columns:
                conn.execute("ALTER TABLE auth_cookies ADD COLUMN updated_at TEXT")
            if "source" not in auth_cookie_columns:
                conn.execute("ALTER TABLE auth_cookies ADD COLUMN source TEXT")


def ensure_handle_row(db_path: str, handle: str) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO handles(handle) VALUES (?)", (handle,))


def upsert_discovered_handles(db_path: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            for row in rows:
                handle = str(row.get("handle") or "").strip()
                if not handle:
                    continue
                conn.execute(
                    """
                    INSERT INTO handles(handle, name, account_status, ip, last_seen_utc)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(handle) DO UPDATE SET
                        name=COALESCE(excluded.name, handles.name),
                        account_status=COALESCE(excluded.account_status, handles.account_status),
                        ip=COALESCE(excluded.ip, handles.ip),
                        last_seen_utc=COALESCE(excluded.last_seen_utc, handles.last_seen_utc)
                    """,
                    (
                        handle,
                        row.get("name"),
                        row.get("account_status"),
                        row.get("ip"),
                        row.get("last_seen_utc"),
                    ),
                )
    return len(rows)


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
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO handles(handle) VALUES (?)", (handle,))
            conn.execute(
                """
                UPDATE handles
                SET last_status=?, status=?,
                    last_error=?, error=?,
                    last_scrape_utc=COALESCE(?, last_scrape_utc),
                    last_updated_utc=COALESCE(?, last_updated_utc),
                    ticket_count=COALESCE(?, ticket_count),
                    last_run_id=COALESCE(?, last_run_id)
                WHERE handle=?
                """,
                (status, status, error, error, last_updated_utc, last_updated_utc, ticket_count, last_run_id, handle),
            )


def upsert_tickets_batch(db_path: str, handle: str, rows: list[dict[str, Any]], batch_size: int = 100) -> int:
    if not rows:
        return 0
    inserted = 0
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            for idx in range(0, len(rows), batch_size):
                batch = rows[idx : idx + batch_size]
                conn.execute("BEGIN")
                for row in batch:
                    ticket_id = str(row.get("ticket_id") or row.get("id") or "").strip()
                    if not ticket_id:
                        continue
                    raw_json = row.get("raw_json")
                    if raw_json is None:
                        raw_json = json.dumps(row, sort_keys=True)
                    stable_id = f"{handle}:{ticket_id}"
                    conn.execute(
                        """
                        INSERT INTO tickets(pk, id, ticket_id, handle, created_utc, updated_utc, subject, status, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticket_id, handle) DO UPDATE SET
                            pk=excluded.pk,
                            id=excluded.id,
                            created_utc=COALESCE(excluded.created_utc, tickets.created_utc),
                            updated_utc=COALESCE(excluded.updated_utc, tickets.updated_utc),
                            subject=COALESCE(excluded.subject, tickets.subject),
                            status=COALESCE(excluded.status, tickets.status),
                            raw_json=excluded.raw_json
                        """,
                        (
                            stable_id,
                            stable_id,
                            ticket_id,
                            handle,
                            row.get("created_utc") or row.get("created_on") or row.get("opened_utc"),
                            row.get("updated_utc") or row.get("created_utc") or row.get("created_on"),
                            row.get("subject") or row.get("title"),
                            row.get("status"),
                            raw_json,
                        ),
                    )
                    inserted += 1
                conn.commit()
    return inserted


def add_event(db_path: str, created_utc: str, level: str, handle: str | None, message: str, meta: dict[str, Any] | None = None) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO events(created_utc, level, handle, message, meta_json) VALUES (?, ?, ?, ?, ?)",
                (created_utc, level, handle, message, json.dumps(meta, sort_keys=True) if meta else None),
            )


def get_latest_events(db_path: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, created_utc, level, handle, message, meta_json FROM events ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["meta"] = json.loads(item["meta_json"]) if item.get("meta_json") else None
        out.append(item)
    return out


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
               COALESCE(h.ticket_count, ts.tickets_count, 0) AS ticket_count,
               h.name AS name, h.account_status AS account_status, h.ip AS ip,
               ts.last_ticket_at AS lastTicketAt, h.last_scrape_utc AS lastScrapeAt, h.last_status AS status, h.last_error AS last_message,
               h.last_error AS error_message, h.last_error AS error, h.last_started_utc AS started_utc, h.last_finished_utc AS finished_utc,
               h.last_updated_utc AS last_updated_utc, h.last_seen_utc AS last_seen_utc,
               h.last_run_id AS last_run_id,
               CASE
                 WHEN h.last_run_id IS NULL THEN NULL
                 ELSE 'var/runs/' || h.last_run_id || '/'
               END AS artifacts_hint
        FROM all_handles ah LEFT JOIN handles h ON h.handle=ah.handle LEFT JOIN ticket_summary ts ON ts.handle=ah.handle
        """
        params: list[Any] = []
        if q:
            query += " WHERE ah.handle LIKE ?"
            params.append(f"%{q}%")
        query += " ORDER BY ah.handle LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def list_handles_summary(db_path: str, q: str = "", limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    """Backwards-compatible summary shape used by legacy tests/UI."""
    rows = list_handles(db_path=db_path, q=q, limit=limit, offset=offset)
    return [
        {
            "handle": row.get("handle"),
            "last_scrape_utc": row.get("lastScrapeAt"),
            "ticket_count": row.get("ticket_count", row.get("ticketsCount", 0)),
            "open_count": row.get("openCount", 0),
            "updated_latest_utc": row.get("lastTicketAt") or row.get("last_updated_utc"),
        }
        for row in rows
    ]


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


def get_handle_latest(db_path: str, handle: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT handle, last_status AS status, last_error AS error_message, last_started_utc AS started_utc,
                   last_finished_utc AS finished_utc, last_run_id,
                   CASE
                     WHEN last_run_id IS NULL THEN NULL
                     ELSE 'var/runs/' || last_run_id || '/'
                   END AS artifacts_hint
            FROM handles WHERE handle=?
            """,
            (handle,),
        ).fetchone()
    return dict(row) if row else None


def list_runs(db_path: str, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT run_id, failure_reason, started_utc, finished_utc FROM runs ORDER BY started_utc DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [dict(r) for r in rows]


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
        where.append("(ticket_id LIKE ? OR title LIKE ? OR subject LIKE ? OR ticket_url LIKE ? OR raw_json LIKE ?)")
        params.extend([like, like, like, like, like])
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


def create_scrape_job(
    db_path: str,
    job_id: str,
    handle: str | None,
    mode: str,
    ticket_limit: int | None,
    status: str,
    created_utc: str,
    ticket_id: str | None = None,
    handles: list[str] | None = None,
) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO scrape_jobs(job_id, handle, handles_json, mode, ticket_id, ticket_limit, status, created_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, handle, json.dumps(handles, sort_keys=True) if handles is not None else None, mode, ticket_id, ticket_limit, status, created_utc),
            )


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


def list_scrape_jobs(db_path: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM scrape_jobs ORDER BY created_utc DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        payload = dict(row)
        payload["result"] = json.loads(payload["result_json"]) if payload.get("result_json") else None
        payload["handles"] = json.loads(payload["handles_json"]) if payload.get("handles_json") else None
        result.append(payload)
    return result


def get_latest_scrape_job(db_path: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scrape_jobs ORDER BY created_utc DESC LIMIT 1").fetchone()
    if not row:
        return None
    payload=dict(row)
    payload["result"] = json.loads(payload["result_json"]) if payload.get("result_json") else None
    payload["handles"] = json.loads(payload["handles_json"]) if payload.get("handles_json") else None
    return payload


def get_scrape_job(db_path: str, job_id: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scrape_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["result"] = json.loads(payload["result_json"]) if payload.get("result_json") else None
    payload["handles"] = json.loads(payload["handles_json"]) if payload.get("handles_json") else None
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


def replace_auth_cookies(db_path: str, cookies: list[dict[str, Any]], created_utc: str, source: str = "none") -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("DELETE FROM auth_cookies")
            for cookie in cookies:
                conn.execute(
                    """
                    INSERT INTO auth_cookies(domain, name, value, path, expires, secure, http_only, expires_utc, same_site, created_utc, updated_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(domain, name, path) DO UPDATE SET
                        value=excluded.value,
                        expires=excluded.expires,
                        secure=excluded.secure,
                        http_only=excluded.http_only,
                        expires_utc=excluded.expires_utc,
                        same_site=excluded.same_site,
                        created_utc=excluded.created_utc,
                        updated_at=excluded.updated_at,
                        source=excluded.source
                    """,
                    (
                        cookie.get("domain"),
                        cookie.get("name"),
                        cookie.get("value"),
                        cookie.get("path") or "/",
                        cookie.get("expires"),
                        1 if cookie.get("secure") else 0,
                        1 if cookie.get("httpOnly") else 0,
                        cookie.get("expires_utc"),
                        cookie.get("sameSite"),
                        created_utc,
                        created_utc,
                        source,
                    ),
                )
            conn.execute(
                """
                INSERT INTO auth_cookie_state(id, last_loaded, source)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_loaded=excluded.last_loaded,
                    source=excluded.source
                """,
                (created_utc, source),
            )


def clear_auth_cookies(db_path: str) -> None:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("DELETE FROM auth_cookies")
            conn.execute("UPDATE auth_cookie_state SET last_loaded=NULL, source='none' WHERE id=1")


def get_auth_cookies(db_path: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT domain, name, value, path, expires, secure, http_only, expires_utc, same_site, created_utc, updated_at, source FROM auth_cookies ORDER BY id ASC"
        ).fetchall()
    return [
        {
            "domain": str(row["domain"]),
            "name": str(row["name"]),
            "value": str(row["value"]),
            "path": str(row["path"] or "/"),
            "expires": row["expires"],
            "secure": bool(row["secure"]),
            "httpOnly": bool(row["http_only"]),
            "expires_utc": row["expires_utc"],
            "sameSite": row["same_site"],
            "created_utc": row["created_utc"],
            "updated_at": row["updated_at"],
            "source": row["source"],
        }
        for row in rows
    ]


def get_auth_cookie_status(db_path: str) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count, MAX(created_utc) AS created_utc FROM auth_cookies"
        ).fetchone()
        domains = conn.execute(
            "SELECT domain, COUNT(*) AS count FROM auth_cookies GROUP BY domain ORDER BY domain ASC"
        ).fetchall()
        state = conn.execute("SELECT last_loaded, source FROM auth_cookie_state WHERE id=1").fetchone()
    return {
        "count": int(row["count"] if row else 0),
        "domains": [{"domain": str(item["domain"]), "count": int(item["count"])} for item in domains],
        "created_utc": row["created_utc"] if row else None,
        "last_loaded": state["last_loaded"] if state else row["created_utc"] if row else None,
        "source": (state["source"] if state and state["source"] else "none"),
    }


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
        last_updated = conn.execute(
            "SELECT MAX(COALESCE(last_updated_utc, last_scrape_utc)) AS updated_utc FROM handles"
        ).fetchone()["updated_utc"]
    return {
        "total_tickets": total_tickets,
        "total_handles": total_handles,
        "total_runs": total_runs,
        "total_scrape_jobs": total_jobs,
        "total_artifacts": total_artifacts,
        "last_updated_utc": last_updated,
    }


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


def explain_list_tickets_plan(db_path: str, handle: str | None = None, status: str | None = None) -> list[str]:
    where = ["1=1"]
    params: list[Any] = []
    if handle:
        where.append("handle=?")
        params.append(handle)
    if status and status != "any":
        where.append("status=?")
        params.append(status)
    sql = f"EXPLAIN QUERY PLAN SELECT * FROM tickets WHERE {' AND '.join(where)} ORDER BY updated_utc DESC LIMIT 50"
    with get_conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [" ".join(str(x) for x in row) for row in rows]


def safe_artifact_path(requested_path: str, output_root: str) -> Path | None:
    root = Path(output_root).resolve()
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    return None


def upsert_company(db_path: str, handle: str, name: str | None = None, last_ingest_job_id: str | None = None, now_utc: str | None = None) -> None:
    now = now_utc or ""
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute(
                """
                INSERT INTO companies(handle, name, created_utc, updated_utc, last_ingest_job_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(handle) DO UPDATE SET
                    name=COALESCE(excluded.name, companies.name),
                    updated_utc=excluded.updated_utc,
                    last_ingest_job_id=COALESCE(excluded.last_ingest_job_id, companies.last_ingest_job_id)
                """,
                (handle, name, now, now, last_ingest_job_id),
            )


def replace_ticket_events(db_path: str, handle: str, events: list[dict[str, Any]], now_utc: str) -> int:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("DELETE FROM ticket_events WHERE handle=?", (handle,))
            for event in events:
                conn.execute(
                    """
                    INSERT INTO ticket_events(handle, ticket_id, category, event_utc, summary, raw_source_text, confidence, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.get("handle") or handle,
                        event.get("ticket_id"),
                        event.get("category"),
                        event.get("event_utc"),
                        event.get("summary"),
                        event.get("raw_source_text"),
                        float(event.get("confidence") or 0.5),
                        now_utc,
                    ),
                )
    return len(events)


def replace_company_timeline(db_path: str, handle: str, timeline_rows: list[dict[str, Any]], now_utc: str) -> int:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("DELETE FROM company_timeline WHERE handle=?", (handle,))
            for row in timeline_rows:
                conn.execute(
                    """
                    INSERT INTO company_timeline(handle, event_utc, category, title, details, ticket_id, source_event_id, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        handle,
                        row.get("event_utc"),
                        row.get("category"),
                        row.get("title"),
                        row.get("details"),
                        row.get("ticket_id"),
                        row.get("source_event_id"),
                        now_utc,
                    ),
                )
    return len(timeline_rows)


def replace_resolution_patterns(db_path: str, handle: str, patterns: list[dict[str, Any]], now_utc: str) -> int:
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            conn.execute("DELETE FROM resolution_patterns WHERE handle=?", (handle,))
            for pattern in patterns:
                conn.execute(
                    """
                    INSERT INTO resolution_patterns(handle, pattern, count, last_seen_utc, created_utc)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        handle,
                        str(pattern.get("pattern") or ""),
                        int(pattern.get("count") or 0),
                        pattern.get("last_seen_utc"),
                        now_utc,
                    ),
                )
    return len(patterns)


def get_company(db_path: str, handle: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM companies WHERE handle=?", (handle,)).fetchone()
    return dict(row) if row else None


def get_company_timeline(db_path: str, handle: str, limit: int = 500) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_timeline WHERE handle=? ORDER BY COALESCE(event_utc, created_utc) DESC, id DESC LIMIT ?",
            (handle, max(1, min(limit, 5000))),
        ).fetchall()
    return [dict(row) for row in rows]


def list_noc_queue_tickets(db_path: str, view: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM noc_queue_tickets"
    params: list[Any] = []
    if view:
        q += " WHERE view=?"
        params.append(view)
    q += " ORDER BY view ASC, last_seen_utc DESC"
    with get_conn(db_path) as conn:
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def upsert_noc_queue_tickets(db_path: str, records: list[dict[str, Any]], now_utc: str) -> int:
    if not records:
        return 0
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            for rec in records:
                ticket_id = (rec.get("ticket_id") or "").strip()
                view = (rec.get("view") or "all").strip()
                if not ticket_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO noc_queue_tickets(ticket_id, view, subject, status, opened, customer,
                        priority, assigned_to, ticket_type, ticket_id_url, raw_json, last_seen_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticket_id, view) DO UPDATE SET
                        subject=excluded.subject,
                        status=excluded.status,
                        opened=excluded.opened,
                        customer=excluded.customer,
                        priority=excluded.priority,
                        assigned_to=excluded.assigned_to,
                        ticket_type=excluded.ticket_type,
                        ticket_id_url=excluded.ticket_id_url,
                        raw_json=excluded.raw_json,
                        last_seen_utc=excluded.last_seen_utc
                    """,
                    (
                        ticket_id, view,
                        rec.get("subject") or "",
                        rec.get("status") or "",
                        rec.get("opened") or "",
                        rec.get("customer") or "",
                        rec.get("priority") or "",
                        rec.get("assigned_to") or "",
                        rec.get("ticket_type") or "",
                        rec.get("ticket_id_url") or "",
                        rec.get("raw_json") or "{}",
                        rec.get("last_seen_utc") or now_utc,
                    ),
                )
    return len(records)


def list_vpbx_records(db_path: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT handle, name, account_status, ip, web_order, deployment_id, switch, devices, last_seen_utc"
            " FROM vpbx_records ORDER BY handle ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_handle(db_path: str, handle: str) -> bool:
    """Remove a handle row. Returns True if a row was deleted."""
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            cur = conn.execute("DELETE FROM handles WHERE handle=?", (handle,))
    return cur.rowcount > 0


def upsert_vpbx_records(db_path: str, records: list[dict[str, Any]], now_utc: str) -> int:
    if not records:
        return 0
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            for rec in records:
                handle = (rec.get("handle") or "").strip()
                if not handle:
                    continue
                conn.execute(
                    """
                    INSERT INTO vpbx_records(handle, name, account_status, ip, web_order, deployment_id, switch, devices, last_seen_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(handle) DO UPDATE SET
                        name=excluded.name,
                        account_status=excluded.account_status,
                        ip=excluded.ip,
                        web_order=excluded.web_order,
                        deployment_id=excluded.deployment_id,
                        switch=excluded.switch,
                        devices=excluded.devices,
                        last_seen_utc=excluded.last_seen_utc
                    """,
                    (
                        handle,
                        rec.get("name") or "",
                        rec.get("account_status") or "",
                        rec.get("ip") or "",
                        rec.get("web_order") or "",
                        rec.get("deployment_id") or "",
                        rec.get("switch") or "",
                        rec.get("devices") or "",
                        rec.get("last_seen_utc") or now_utc,
                    ),
                )
    return len(records)


def list_vpbx_device_configs(db_path: str, handle: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM vpbx_device_configs"
    params: list[Any] = []
    if handle:
        q += " WHERE handle=?"
        params.append(handle.upper())
    q += " ORDER BY handle ASC, directory_name ASC"
    with get_conn(db_path) as conn:
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def upsert_vpbx_device_configs(db_path: str, records: list[dict[str, Any]], now_utc: str) -> int:
    if not records:
        return 0
    with WRITE_LOCK:
        with get_conn(db_path) as conn:
            for rec in records:
                device_id = (rec.get("device_id") or "").strip()
                vpbx_id = (rec.get("vpbx_id") or "").strip()
                if not device_id or not vpbx_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO vpbx_device_configs
                        (device_id, vpbx_id, handle, directory_name, extension, mac,
                         make, model, site_code, bulk_config, last_seen_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, vpbx_id) DO UPDATE SET
                        handle=excluded.handle,
                        directory_name=excluded.directory_name,
                        extension=excluded.extension,
                        mac=excluded.mac,
                        make=excluded.make,
                        model=excluded.model,
                        site_code=excluded.site_code,
                        bulk_config=excluded.bulk_config,
                        last_seen_utc=excluded.last_seen_utc
                    """,
                    (
                        device_id, vpbx_id,
                        (rec.get("handle") or "").upper(),
                        rec.get("directory_name") or "",
                        rec.get("extension") or "",
                        rec.get("mac") or "",
                        rec.get("make") or "",
                        rec.get("model") or "",
                        rec.get("site_code") or "",
                        rec.get("bulk_config") or "",
                        rec.get("last_seen_utc") or now_utc,
                    ),
                )
    return len(records)
