from pathlib import Path


def test_ticket_ui_auth_help_panel_includes_legend_and_flows() -> None:
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Auth legend" in page
    assert "Flow A — Debug Chrome" in page
    assert "Flow B — Isolated Login" in page
    assert "Flow C — Local Browser Profile Sync" in page
    assert "cdp_debug_chrome = cookies imported from live debug Chrome via CDP on 9222" in page


def test_ticket_ui_auth_help_panel_includes_mixed_source_warnings() -> None:
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Debug Chrome is live on 9222, but Sync from Chrome targets local profile Profile 1." in page
    assert "Paste Cookies is currently active; a successful browser import will replace this state." in page
    assert "Launch Login (isolated) uses a different browser profile than Chrome Profile 1." in page


def test_ticket_ui_auth_help_panel_includes_log_review_commands() -> None:
    page = Path("webscraper/ticket-ui/app/page.tsx").read_text(encoding="utf-8")

    assert "Get-Content E:\\\\DevTools\\\\freepbx-tools\\\\var\\\\web-app-launcher\\\\logs\\\\webscraper_ticket_api.log -Wait -Tail 80" in page
    assert "Get-Content E:\\\\DevTools\\\\freepbx-tools\\\\var\\\\web-app-launcher\\\\logs\\\\webscraper_ticket_ui.log -Wait -Tail 60" in page
    assert "flowA.txt" in page and "flowB.txt" in page and "flowC.txt" in page
