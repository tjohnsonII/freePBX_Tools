import os
import sqlite3
from typing import Dict, List, Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  host TEXT NOT NULL,
  ticket_id TEXT,
  subject TEXT,
  status TEXT,
  opened TEXT,
  customer TEXT,
  link TEXT,
  raw_json TEXT
);
"""

def open_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA_SQL)
    return conn

def normalize_row(row: Dict, header_synonyms: Dict[str, List[str]]) -> Dict:
    # Map common fields from various header names
    def pick(keys: List[str]) -> Optional[str]:
        for k in keys:
            for rk in row.keys():
                if rk and rk.lower() == k:
                    return row.get(rk)
        return None

    ticket_id = pick([x.lower() for x in header_synonyms.get("ticket_id", ["id", "ticket id"])])
    subject = pick([x.lower() for x in header_synonyms.get("subject", ["subject", "title"])])
    status = pick([x.lower() for x in header_synonyms.get("status", ["status", "state"])])
    opened = pick([x.lower() for x in header_synonyms.get("opened", ["opened", "created", "date"])])
    customer = pick([x.lower() for x in header_synonyms.get("customer", ["customer", "account"])])

    return {
        "ticket_id": ticket_id,
        "subject": subject,
        "status": status,
        "opened": opened,
        "customer": customer,
    }

def store_rows(conn, host: str, rows: List[Dict], header_synonyms: Dict[str, List[str]], page_link: Optional[str] = None):
    import json
    cur = conn.cursor()
    for r in rows:
        norm = normalize_row(r, header_synonyms)
        cur.execute(
            "INSERT INTO tickets (host, ticket_id, subject, status, opened, customer, link, raw_json) VALUES (?,?,?,?,?,?,?,?)",
            (
                host,
                norm.get("ticket_id"),
                norm.get("subject"),
                norm.get("status"),
                norm.get("opened"),
                norm.get("customer"),
                page_link,
                json.dumps(r, ensure_ascii=False),
            ),
        )
    conn.commit()
