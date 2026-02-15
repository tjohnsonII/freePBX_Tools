from webscraper.db import init_db, start_run, upsert_handle, upsert_tickets
from webscraper.ticket_api.db import ensure_indexes, get_handle, get_stats, get_ticket, list_handles, list_tickets


def test_ticket_api_queries(tmp_path):
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))
    ensure_indexes(str(db_path))
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
                "created_utc": "2024-04-01T00:00:00Z",
            },
            {
                "ticket_id": "888888888888",
                "url": "https://noc-tickets.123.net/ticket/888888888888",
                "title": "Router Restored",
                "status": "closed",
                "updated_utc": "2024-05-03T00:00:00Z",
                "created_utc": "2024-05-02T00:00:00Z",
            }
        ],
    )

    handles = list_handles(str(db_path), q="AB")
    assert handles[0]["handle"] == "ABC"
    assert handles[0]["ticketsCount"] == 2
    assert handles[0]["lastScrapeAt"] is not None

    handle = get_handle(str(db_path), "ABC")
    assert handle is not None

    tickets = list_tickets(str(db_path), handle="ABC", q="Router", page=1, page_size=1, sort="newest")
    assert tickets["page"] == 1
    assert tickets["pageSize"] == 1
    assert tickets["totalCount"] == 2
    assert tickets["items"][0]["ticket_id"] == "888888888888"

    older_tickets = list_tickets(str(db_path), handle="ABC", status="open", sort="oldest")
    assert older_tickets["items"][0]["ticket_id"] == "777777777777"

    tickets = list_tickets(str(db_path), handle="ABC", q="Router")
    assert tickets["items"][0]["ticket_id"] == "888888888888"
    assert tickets["totalCount"] == 2

    ticket = get_ticket(str(db_path), "777777777777", "ABC")
    assert ticket is not None

    stats = get_stats(str(db_path))
    assert stats["total_tickets"] == 2
