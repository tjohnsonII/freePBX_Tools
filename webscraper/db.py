"""SQLite persistence helpers for webscraper ticket history."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
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
                git_sha TEXT,
                host TEXT
            );

            CREATE TABLE IF NOT EXISTS tickets(
                ticket_id TEXT,
                handle TEXT,
                ticket_url TEXT,
                title TEXT,
                status TEXT,
                created_utc TEXT,
                updated_utc TEXT,
                raw_json TEXT,
                run_id TEXT,
                PRIMARY KEY(ticket_id, handle),
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
            CREATE INDEX IF NOT EXISTS idx_artifacts_ticket ON ticket_artifacts(ticket_id, handle);
            """
        )
        _ensure_column(conn, "runs", "out_dir", "TEXT")
        _ensure_column(conn, "ticket_artifacts", "notes", "TEXT")


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
    with _connect(db_path) as conn:
        conn.execute("UPDATE runs SET finished_utc=? WHERE run_id=?", (utc_now(), run_id))


def upsert_handle(db_path: str, handle: str, status: str, error: str | None = None) -> None:
    now = utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO handles(handle, first_seen_utc, last_scrape_utc, last_status, last_error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                last_scrape_utc=excluded.last_scrape_utc,
                last_status=excluded.last_status,
                last_error=excluded.last_error
            """,
            (handle, now, now, status, error),
        )


def _ticket_from_row(handle: str, row: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    ticket_url = row.get("ticket_url") or row.get("url")
    ticket_id = row.get("ticket_id")
    title = row.get("title") or row.get("subject") or row.get("page_title")
    status = row.get("status") or row.get("kind")
    created_utc = row.get("created_utc") or row.get("extracted_at")
    updated_utc = row.get("updated_utc") or row.get("extracted_at")
    if ticket_id is None and isinstance(ticket_url, str):
        maybe = ticket_url.rstrip("/").split("/")[-1]
        ticket_id = maybe if maybe.isdigit() else None
    return ticket_id, ticket_url, title, status, created_utc, updated_utc


def upsert_tickets(db_path: str, run_id: str, handle: str, tickets_list: Iterable[dict[str, Any]]) -> int:
    inserted = 0
    with _connect(db_path) as conn:
        for row in tickets_list:
            ticket_id, ticket_url, title, status, created_utc, updated_utc = _ticket_from_row(handle, row)
            if not ticket_id:
                continue
            conn.execute(
                """
                INSERT INTO tickets(ticket_id, handle, ticket_url, title, status, created_utc, updated_utc, raw_json, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_id, handle) DO UPDATE SET
                    ticket_url=excluded.ticket_url,
                    title=COALESCE(excluded.title, tickets.title),
                    status=COALESCE(excluded.status, tickets.status),
                    created_utc=COALESCE(excluded.created_utc, tickets.created_utc),
                    updated_utc=COALESCE(excluded.updated_utc, tickets.updated_utc),
                    raw_json=excluded.raw_json,
                    run_id=excluded.run_id
                """,
                (
                    str(ticket_id),
                    handle,
                    ticket_url,
                    title,
                    status,
                    created_utc,
                    updated_utc,
                    json.dumps(row, sort_keys=True),
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
