from webscraper.ticket_api import db


def test_upsert_tickets_batch_and_events(tmp_path):
    db_path = str(tmp_path / "tickets.sqlite")
    db.ensure_indexes(db_path)

    inserted = db.upsert_tickets_batch(
        db_path,
        "ABC",
        [
            {"ticket_id": "1", "subject": "First", "status": "open", "created_utc": "2025-01-01T00:00:00Z"},
            {"ticket_id": "2", "subject": "Second", "status": "closed", "created_utc": "2025-01-02T00:00:00Z"},
        ],
    )
    assert inserted == 2

    db.update_handle_progress(db_path, "ABC", status="ok", ticket_count=2, last_updated_utc="2025-01-02T00:00:00Z")
    db.add_event(db_path, "2025-01-02T00:00:00Z", "info", "ABC", "Completed handle ABC", {"inserted": 2})

    handles = db.list_handles(db_path)
    assert handles
    assert handles[0]["handle"] == "ABC"

    events = db.get_latest_events(db_path, limit=10)
    assert events
    assert events[0]["message"] == "Completed handle ABC"
