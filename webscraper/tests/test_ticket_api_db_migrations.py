import sqlite3

from webscraper.ticket_api.db import ensure_indexes, get_stats, list_handles_summary


def test_ticket_api_db_migrates_legacy_tickets_schema(tmp_path):
    db_path = tmp_path / "legacy_tickets.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE tickets(
            ticket_id TEXT,
            handle TEXT,
            ticket_url TEXT,
            created_utc TEXT,
            updated_utc TEXT,
            raw_json TEXT,
            raw_row_json TEXT,
            run_id TEXT,
            PRIMARY KEY(ticket_id, handle),
            UNIQUE(ticket_url, handle)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tickets(ticket_id, handle, ticket_url, created_utc, updated_utc, raw_json, raw_row_json, run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "1001",
            "LEGACY",
            "https://noc-tickets.123.net/ticket/1001",
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "{}",
            "{}",
            "run-1",
        ),
    )
    conn.commit()
    conn.close()

    ensure_indexes(str(db_path))

    stats = get_stats(str(db_path))
    summary = list_handles_summary(str(db_path), q="LEGACY")

    assert "last_updated_utc" in stats
    assert "updated_latest_utc" in summary[0]

    with sqlite3.connect(db_path) as migrated_conn:
        columns = {row[1] for row in migrated_conn.execute("PRAGMA table_info('tickets')").fetchall()}
    assert "opened_utc" in columns
