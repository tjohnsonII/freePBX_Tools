from webscraper.auth.seeded_session import is_authenticated_html


def test_is_authenticated_html_detects_authenticated_nav() -> None:
    html = "<html><body><nav>Administration</nav><div>Account Search</div></body></html>"
    assert is_authenticated_html(html) is True


def test_is_authenticated_html_detects_login_page() -> None:
    html = "<html><body><h1>Login</h1><input type='password' name='password'></body></html>"
    assert is_authenticated_html(html) is False
