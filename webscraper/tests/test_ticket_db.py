import sqlite3

from webscraper.db import finish_run, init_db, start_run, upsert_handle, upsert_tickets


def test_db_init_and_upsert(tmp_path):
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))
    run_id = start_run(str(db_path), {"a": 1})

    upsert_handle(str(db_path), "KPM", "success")
    upsert_tickets(
        str(db_path),
        run_id,
        "KPM",
        [
            {
                "ticket_id": "123456789012",
                "url": "https://noc-tickets.123.net/ticket/123456789012",
                "title": "Sample",
                "status": "open",
                "created_utc": "2024-01-01T00:00:00Z",
            }
        ],
    )
    finish_run(str(db_path), run_id)

    conn = sqlite3.connect(db_path)
    handle = conn.execute("SELECT last_status FROM handles WHERE handle='KPM'").fetchone()[0]
    ticket = conn.execute("SELECT title FROM tickets WHERE ticket_id='123456789012'").fetchone()[0]
    finished = conn.execute("SELECT finished_utc FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]

    assert handle == "success"
    assert ticket == "Sample"
    assert finished is not None
