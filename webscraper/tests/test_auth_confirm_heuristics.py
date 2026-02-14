from pathlib import Path

from webscraper.auth.healthcheck import auth_confirmed_from_page


def _fixture_text(name: str) -> str:
    fixture_path = Path(__file__).parent / "fixtures" / "auth_pages" / name
    return fixture_path.read_text(encoding="utf-8")


def test_logged_in_fixture_returns_true() -> None:
    html = _fixture_text("customers_logged_in.html")
    ok, _reason = auth_confirmed_from_page(
        current_url="https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
        page_source=html,
        has_password_input=False,
        has_expected_logged_in_elements=True,
        has_session_cookie=False,
        has_enough_dom_content=True,
    )
    assert ok is True


def test_logged_out_fixture_returns_false() -> None:
    html = _fixture_text("customers_logged_out.html")
    ok, _reason = auth_confirmed_from_page(
        current_url="https://secure.123.net/login",
        page_source=html,
        has_password_input=True,
        has_expected_logged_in_elements=False,
        has_session_cookie=False,
        has_enough_dom_content=False,
    )
    assert ok is False
