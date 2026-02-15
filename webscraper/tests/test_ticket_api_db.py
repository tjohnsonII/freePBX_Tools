from webscraper.db import init_db, start_run, upsert_handle, upsert_tickets
from webscraper.ticket_api.db import get_handle, get_stats, get_ticket, list_handles, list_tickets


def test_ticket_api_queries(tmp_path):
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))
    run_id = start_run(str(db_path), {})
    upsert_handle(str(db_path), "ABC", "success")
    upsert_tickets(
        str(db_path),
        run_id,
        "ABC",
        [
            {
                "ticket_id": "777777777777",
                "url": "https://noc-tickets.123.net/ticket/777777777777",
                "title": "Router Down",
                "status": "open",
                "updated_utc": "2024-05-01T00:00:00Z",
            }
        ],
    )

    handles = list_handles(str(db_path), search="AB")
    assert handles[0]["handle"] == "ABC"

    handle = get_handle(str(db_path), "ABC")
    assert handle is not None

    tickets = list_tickets(str(db_path), "ABC", q="Router")
    assert tickets[0]["ticket_id"] == "777777777777"

    ticket = get_ticket(str(db_path), "777777777777", "ABC")
    assert ticket is not None

    stats = get_stats(str(db_path))
    assert stats["total_tickets"] == 1
