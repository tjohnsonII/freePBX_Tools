import sqlite3

from webscraper.db import get_handle_state, init_db, mark_handle_attempt, mark_handle_error, mark_handle_success


def test_handle_scrape_state_lifecycle(tmp_path):
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))

    mark_handle_attempt(str(db_path), "KPM")
    mark_handle_error(str(db_path), "KPM", "boom")
    state = get_handle_state(str(db_path), "KPM")
    assert state is not None
    assert state["last_error"] == "boom"

    mark_handle_success(
        str(db_path),
        "KPM",
        run_id="run-1",
        max_updated_utc="2026-01-01T00:00:00Z",
        seen_count=10,
        upserted_count=3,
    )
    state = get_handle_state(str(db_path), "KPM")
    assert state is not None
    assert state["last_error"] is None
    assert state["last_max_updated_utc"] == "2026-01-01T00:00:00Z"
    assert state["total_tickets_seen"] == 10
    assert state["total_tickets_upserted"] == 3

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM handle_scrape_state WHERE handle='KPM'").fetchone()[0]
    assert count == 1
