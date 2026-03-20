from pathlib import Path


def test_ticket_ui_kb_search_section_present() -> None:
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Search Tickets" in page
    assert "/api/kb/tickets" in page
    assert "ticketQ" in page or "ticketHandle" in page


def test_ticket_ui_kb_handle_summary_present() -> None:
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Knowledge Base" in page
    assert "handleRows" in page
    assert "last_updated_utc" in page


def test_ticket_ui_no_dead_auth_panel() -> None:
    """Auth help panel and browser-sync code was removed in Phase 3."""
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Auth legend" not in page
    assert "cdp_debug_chrome" not in page
    assert "syncAuthFromBrowser" not in page
