"""SQLite persistence helpers for webscraper ticket history."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
import subprocess
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


WRITE_LOCK = threading.Lock()

@contextmanager
def _connect(db_path: str):
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=5.0, check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with WRITE_LOCK:
        with _connect(db_path) as conn:
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
                url TEXT,
                ticket_num TEXT,
                title TEXT,
                subject TEXT,
                status TEXT,
                opened_utc TEXT,
                created_utc TEXT,
                updated_utc TEXT,
                raw_json TEXT,
                raw_row_json TEXT,
                scraped_utc TEXT,
                run_id TEXT,
                PRIMARY KEY(ticket_id, handle),
                UNIQUE(ticket_id),
                UNIQUE(ticket_url, handle),
                FOREIGN KEY(handle) REFERENCES handles(handle),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS ticket_artifacts(
                ticket_id TEXT,
                handle TEXT,
                artifact_type TEXT,
                path TEXT,
                sha256 TEXT,
                created_utc TEXT,
                run_id TEXT,
                notes TEXT,
                PRIMARY KEY(ticket_id, handle, artifact_type, path)
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_handle ON tickets(handle);
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets(updated_utc);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_updated_desc ON tickets(handle, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_handle_status_updated_desc ON tickets(handle, status, updated_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_tickets_ticket_id_handle ON tickets(ticket_id, handle);
            CREATE INDEX IF NOT EXISTS idx_artifacts_ticket ON ticket_artifacts(ticket_id, handle);

            CREATE TABLE IF NOT EXISTS handle_scrape_state(
                handle TEXT PRIMARY KEY,
                last_success_utc TEXT,
                last_max_updated_utc TEXT,
                last_run_id TEXT,
                last_error TEXT,
                last_attempt_utc TEXT,
                total_tickets_seen INTEGER DEFAULT 0,
                total_tickets_upserted INTEGER DEFAULT 0
            );
            """
        )
            _ensure_column(conn, "runs", "out_dir", "TEXT")
            _ensure_column(conn, "runs", "failure_reason", "TEXT")
            _ensure_column(conn, "handles", "last_started_utc", "TEXT")
            _ensure_column(conn, "handles", "last_finished_utc", "TEXT")
            _ensure_column(conn, "handles", "last_run_id", "TEXT")
            _ensure_column(conn, "tickets", "ticket_num", "TEXT")
            _ensure_column(conn, "tickets", "subject", "TEXT")
            _ensure_column(conn, "tickets", "opened_utc", "TEXT")
            _ensure_column(conn, "tickets", "raw_row_json", "TEXT")
            _ensure_column(conn, "tickets", "url", "TEXT")
            _ensure_column(conn, "tickets", "scraped_utc", "TEXT")
            _ensure_column(conn, "ticket_artifacts", "notes", "TEXT")


def get_handle_state(db_path: str, handle: str) -> dict[str, Any] | None:
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT handle, last_success_utc, last_max_updated_utc, last_run_id, last_error,
                       last_attempt_utc, total_tickets_seen, total_tickets_upserted
                FROM handle_scrape_state
                WHERE handle=?
                """,
                (handle,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {
        "handle": row[0],
        "last_success_utc": row[1],
        "last_max_updated_utc": row[2],
        "last_run_id": row[3],
        "last_error": row[4],
        "last_attempt_utc": row[5],
        "total_tickets_seen": int(row[6] or 0),
        "total_tickets_upserted": int(row[7] or 0),
    }


def mark_handle_attempt(db_path: str, handle: str) -> str:
    attempt = utc_now()
    for _ in range(2):
        try:
            with WRITE_LOCK:
                with _connect(db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO handle_scrape_state(handle, last_attempt_utc)
                        VALUES (?, ?)
                        ON CONFLICT(handle) DO UPDATE SET
                            last_attempt_utc=excluded.last_attempt_utc
                        """,
                        (handle, attempt),
                    )
            return attempt
        except sqlite3.OperationalError:
            init_db(db_path)
    return attempt


def mark_handle_success(
    db_path: str,
    handle: str,
    *,
    run_id: str,
    max_updated_utc: str | None,
    seen_count: int,
    upserted_count: int,
) -> None:
    success_utc = utc_now()
    for _ in range(2):
        try:
            with WRITE_LOCK:
                with _connect(db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO handle_scrape_state(
                            handle, last_success_utc, last_max_updated_utc, last_run_id, last_error, last_attempt_utc,
                            total_tickets_seen, total_tickets_upserted
                        )
                        VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                        ON CONFLICT(handle) DO UPDATE SET
                            last_success_utc=excluded.last_success_utc,
                            last_max_updated_utc=COALESCE(excluded.last_max_updated_utc, handle_scrape_state.last_max_updated_utc),
                            last_run_id=excluded.last_run_id,
                            last_error=NULL,
                            last_attempt_utc=excluded.last_attempt_utc,
                            total_tickets_seen=handle_scrape_state.total_tickets_seen + excluded.total_tickets_seen,
                            total_tickets_upserted=handle_scrape_state.total_tickets_upserted + excluded.total_tickets_upserted
                        """,
                        (handle, success_utc, max_updated_utc, run_id, success_utc, seen_count, upserted_count),
                    )
            return
        except sqlite3.OperationalError:
            init_db(db_path)


def mark_handle_error(db_path: str, handle: str, error: str) -> None:
    for _ in range(2):
        try:
            with WRITE_LOCK:
                with _connect(db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO handle_scrape_state(handle, last_error, last_attempt_utc)
                        VALUES (?, ?, ?)
                        ON CONFLICT(handle) DO UPDATE SET
                            last_error=excluded.last_error,
                            last_attempt_utc=excluded.last_attempt_utc
                        """,
                        (handle, error, utc_now()),
                    )
            return
        except sqlite3.OperationalError:
            init_db(db_path)


def export_tickets_by_handle(db_path: str) -> dict[str, list[dict[str, Any]]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT handle, ticket_id, COALESCE(subject, title), status, created_utc, updated_utc,
                   COALESCE(url, ticket_url), raw_json, scraped_utc
            FROM tickets
            ORDER BY handle ASC, updated_utc DESC
            """
        ).fetchall()

    result: dict[str, list[dict[str, Any]]] = {}
    for handle, ticket_id, subject, status, created_utc, updated_utc, url, raw_json, scraped_utc in rows:
        payload = None
        if raw_json:
            try:
                payload = json.loads(raw_json)
            except Exception:
                payload = raw_json
        result.setdefault(handle, []).append(
            {
                "handle": handle,
                "ticket_id": ticket_id,
                "subject": subject,
                "status": status,
                "created_utc": created_utc,
                "updated_utc": updated_utc,
                "url": url,
                "raw_json": payload,
                "scraped_utc": scraped_utc,
            }
        )
    return result


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        return out or None
    except Exception:
        return None


def start_run(db_path: str, args_dict: dict[str, Any]) -> str:
    run_id = str(uuid.uuid4())
    create_run(db_path, run_id, args_dict=args_dict)
    return run_id


def create_run(
    db_path: str,
    run_id: str,
    started_at: str | None = None,
    args_dict: dict[str, Any] | None = None,
    out_dir: str | None = None,
) -> str:
    with WRITE_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
            """
            INSERT INTO runs(run_id, started_utc, args_json, out_dir, git_sha, host)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                started_at or utc_now(),
                json.dumps(args_dict or {}, sort_keys=True),
                out_dir,
                _git_sha(),
                socket.gethostname(),
            ),
        )
    return run_id


def finish_run(db_path: str, run_id: str) -> None:
    with WRITE_LOCK:
        with _connect(db_path) as conn:
            conn.execute("UPDATE runs SET finished_utc=? WHERE run_id=?", (utc_now(), run_id))


def set_run_failure_reason(db_path: str, run_id: str, failure_reason: str) -> None:
    with WRITE_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
            "UPDATE runs SET failure_reason=COALESCE(failure_reason, ?) WHERE run_id=?",
            (failure_reason, run_id),
        )


def upsert_handle(
    db_path: str,
    handle: str,
    status: str,
    error: str | None = None,
    *,
    started_utc: str | None = None,
    finished_utc: str | None = None,
    run_id: str | None = None,
) -> None:
    now = utc_now()
    started_value = started_utc or now
    finished_value = finished_utc or now
    with WRITE_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
            """
            INSERT INTO handles(handle, first_seen_utc, last_scrape_utc, last_status, last_error, last_started_utc, last_finished_utc, last_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                last_scrape_utc=excluded.last_scrape_utc,
                last_status=excluded.last_status,
                last_error=excluded.last_error,
                last_started_utc=excluded.last_started_utc,
                last_finished_utc=excluded.last_finished_utc,
                last_run_id=COALESCE(excluded.last_run_id, handles.last_run_id)
            """,
            (handle, now, finished_value, status, error, started_value, finished_value, run_id),
        )


def _ticket_from_row(handle: str, row: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None, str | None, str | None, str | None]:
    ticket_url = row.get("ticket_url") or row.get("url")
    ticket_id = row.get("ticket_id") or row.get("ticket_num")
    ticket_num = row.get("ticket_num") or row.get("ticket_id")
    title = row.get("title") or row.get("subject") or row.get("page_title")
    subject = row.get("subject") or row.get("title")
    status = row.get("status") or row.get("kind")
    opened_utc = row.get("opened_utc") or row.get("opened") or row.get("created_utc")
    created_utc = row.get("created_utc") or row.get("extracted_at")
    updated_utc = row.get("updated_utc") or row.get("updated") or row.get("last_updated") or row.get("extracted_at")
    if ticket_id is None and isinstance(ticket_url, str):
        maybe = ticket_url.rstrip("/").split("/")[-1]
        ticket_id = maybe if maybe.isdigit() else None
    if ticket_id is None and isinstance(ticket_url, str) and ticket_url.strip():
        ticket_id = f"url:{sha256(ticket_url.encode('utf-8')).hexdigest()[:16]}"
    return ticket_id, ticket_url, ticket_num, title, subject, status, opened_utc, created_utc, updated_utc


def upsert_tickets(db_path: str, run_id: str, handle: str, tickets_list: Iterable[dict[str, Any]]) -> int:
    inserted = 0
    with WRITE_LOCK:
        with _connect(db_path) as conn:
            for row in tickets_list:
                ticket_id, ticket_url, ticket_num, title, subject, status, opened_utc, created_utc, updated_utc = _ticket_from_row(handle, row)
                if not ticket_id:
                    continue
                now = utc_now()
                conn.execute(
                """
                INSERT INTO tickets(ticket_id, handle, ticket_url, url, ticket_num, title, subject, status, opened_utc, created_utc, updated_utc, raw_json, raw_row_json, scraped_utc, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    handle=excluded.handle,
                    ticket_url=excluded.ticket_url,
                    url=COALESCE(excluded.url, tickets.url),
                    ticket_num=COALESCE(excluded.ticket_num, tickets.ticket_num),
                    title=COALESCE(excluded.title, tickets.title),
                    subject=COALESCE(excluded.subject, tickets.subject),
                    status=COALESCE(excluded.status, tickets.status),
                    opened_utc=COALESCE(excluded.opened_utc, tickets.opened_utc),
                    created_utc=COALESCE(excluded.created_utc, tickets.created_utc),
                    updated_utc=COALESCE(excluded.updated_utc, tickets.updated_utc),
                    raw_json=excluded.raw_json,
                    raw_row_json=excluded.raw_row_json,
                    scraped_utc=excluded.scraped_utc,
                    run_id=excluded.run_id
                """,
                (
                    str(ticket_id),
                    handle,
                    ticket_url,
                    ticket_url,
                    ticket_num,
                    title,
                    subject,
                    status,
                    opened_utc,
                    created_utc,
                    updated_utc,
                    json.dumps(row, sort_keys=True),
                    json.dumps(row, sort_keys=True),
                    now,
                    run_id,
                ),
            )
                inserted += 1
    return inserted


def upsert_ticket(db_path: str, run_id: str, handle: str, ticket: dict[str, Any]) -> bool:
    return upsert_tickets(db_path, run_id, handle, [ticket]) > 0


def record_artifact(
    db_path: str,
    run_id: str,
    handle: str,
    ticket_id: str,
    artifact_type: str,
    path: str,
    notes: str | None = None,
) -> None:
    digest = None
    try:
        digest = sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        digest = None

    with WRITE_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
            """
            INSERT INTO ticket_artifacts(ticket_id, handle, artifact_type, path, sha256, created_utc, run_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id, handle, artifact_type, path) DO UPDATE SET
                sha256=excluded.sha256,
                created_utc=excluded.created_utc,
                run_id=excluded.run_id,
                notes=excluded.notes
            """,
            (ticket_id, handle, artifact_type, path, digest, utc_now(), run_id, notes),
        )
