import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


def as_str(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v if x).strip()
    return str(v).strip()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_year_month(extracted_at: Optional[str], fallback_path: Optional[str]) -> str:
    if extracted_at:
        cleaned = extracted_at.rstrip("Z")
        try:
            parsed = datetime.fromisoformat(cleaned)
            return parsed.strftime("%Y-%m")
        except ValueError:
            pass
    if fallback_path and os.path.exists(fallback_path):
        try:
            ts = os.path.getmtime(fallback_path)
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m")
        except OSError:
            pass
    fallback_stamp = _iso_utc_now()
    try:
        return datetime.fromisoformat(fallback_stamp.rstrip("Z")).strftime("%Y-%m")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_existing_kb_keys(kb_jsonl: str) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    if not os.path.exists(kb_jsonl):
        return seen
    with open(kb_jsonl, "r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ticket_id = as_str(data.get("ticket_id"))
            handle = as_str(data.get("handle"))
            if ticket_id and handle:
                seen.add((handle, ticket_id))
    return seen


def _init_kb_sqlite(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets(
            handle TEXT,
            ticket_id TEXT,
            url TEXT,
            extracted_at TEXT,
            page_title TEXT,
            text TEXT,
            hash TEXT,
            word_count INTEGER,
            year_month TEXT,
            html_path TEXT,
            screenshot_path TEXT,
            PRIMARY KEY(handle, ticket_id)
        )
        """
    )
    conn.commit()
    return conn


def _upsert_kb_record(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO tickets (
            handle, ticket_id, url, extracted_at, page_title, text, hash, word_count,
            year_month, html_path, screenshot_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("handle"),
            record.get("ticket_id"),
            record.get("url"),
            record.get("extracted_at"),
            record.get("page_title"),
            record.get("text"),
            record.get("hash"),
            record.get("word_count"),
            record.get("year_month"),
            record.get("html_path"),
            record.get("screenshot_path"),
        ),
    )
    conn.commit()


def build_kb_index(out_dir: str, resume: bool, kb_jsonl: str, kb_sqlite: Optional[str]) -> dict:
    tickets_root = os.path.join(out_dir, "tickets")
    if not os.path.isdir(tickets_root):
        print(f"[KB] Tickets folder not found at {tickets_root}")
        return {"processed": 0, "skipped": 0, "failed": 0, "total": 0}

    os.makedirs(os.path.dirname(kb_jsonl), exist_ok=True)
    seen_keys = _load_existing_kb_keys(kb_jsonl) if resume else set()
    mode = "a" if resume else "w"
    conn = _init_kb_sqlite(kb_sqlite) if kb_sqlite else None
    processed = skipped = failed = total = 0

    with open(kb_jsonl, mode, encoding="utf-8") as out_f:
        for handle in sorted(os.listdir(tickets_root)):
            handle_dir = os.path.join(tickets_root, handle)
            if not os.path.isdir(handle_dir):
                continue
            for ticket_id in sorted(os.listdir(handle_dir)):
                ticket_dir = os.path.join(handle_dir, ticket_id)
                if not os.path.isdir(ticket_dir):
                    continue
                total += 1
                key = (handle, ticket_id)
                if key in seen_keys:
                    skipped += 1
                    continue
                ticket_json_path = os.path.join(ticket_dir, "ticket.json")
                if not os.path.exists(ticket_json_path):
                    failed += 1
                    continue
                try:
                    with open(ticket_json_path, "r", encoding="utf-8") as fh:
                        ticket_data = json.load(fh)
                except Exception:
                    failed += 1
                    continue
                text = as_str(ticket_data.get("text"))[:20000]
                extracted_at = as_str(ticket_data.get("extracted_at")) or None
                html_path = ticket_data.get("html_path") or (os.path.join(ticket_dir, "page.html") if os.path.exists(os.path.join(ticket_dir, "page.html")) else None)
                screenshot_path = ticket_data.get("screenshot_path") or (os.path.join(ticket_dir, "page.png") if os.path.exists(os.path.join(ticket_dir, "page.png")) else None)
                record = {
                    "ticket_id": ticket_data.get("ticket_id") or ticket_id,
                    "handle": ticket_data.get("handle") or handle,
                    "url": ticket_data.get("url"),
                    "extracted_at": extracted_at,
                    "page_title": as_str(ticket_data.get("page_title")) or None,
                    "text": text,
                    "html_path": html_path,
                    "screenshot_path": screenshot_path,
                    "source": ticket_data.get("source"),
                    "tags": [],
                    "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "word_count": len(text.split()) if text else 0,
                    "year_month": _parse_year_month(extracted_at, ticket_json_path),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                if conn:
                    _upsert_kb_record(conn, record)
                seen_keys.add(key)
                processed += 1
    if conn:
        conn.close()
    print(f"[KB] Summary: processed={processed} skipped={skipped} failed={failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed, "total": total}
