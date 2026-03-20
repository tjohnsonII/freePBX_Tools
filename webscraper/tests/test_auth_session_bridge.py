from webscraper.auth.session import selenium_driver_to_requests_session, summarize_driver_cookies


class _FakeDriver:
    def __init__(self, cookies):
        self._cookies = cookies

    def get_cookies(self):
        return self._cookies


def test_summarize_driver_cookies_collects_domains_and_session_names():
    driver = _FakeDriver([
        {"name": "PHPSESSID", "value": "abc", "domain": ".123.net", "path": "/"},
        {"name": "csrftoken", "value": "xyz", "domain": "secure.123.net", "path": "/"},
    ])

    summary = summarize_driver_cookies(driver)
    assert summary["count"] == 2
    assert "123.net" in summary["domains"]
    assert "PHPSESSID" in summary["session_like_names"]


def test_summarize_driver_cookies_domains_filter_includes_matching():
    driver = _FakeDriver([
        {"name": "PHPSESSID", "value": "abc", "domain": ".123.net", "path": "/"},
        {"name": "csrftoken", "value": "xyz", "domain": "secure.123.net", "path": "/"},
        {"name": "unrelated", "value": "q", "domain": "example.com", "path": "/"},
    ])

    summary = summarize_driver_cookies(driver, domains=["secure.123.net", ".123.net"])
    assert summary["count"] == 2, "only cookies matching 123.net domain should be counted"
    assert "example.com" not in summary["domains"]
    assert "PHPSESSID" in summary["names"]
    assert "unrelated" not in summary["names"]


def test_summarize_driver_cookies_domains_none_includes_all():
    driver = _FakeDriver([
        {"name": "a", "value": "1", "domain": "foo.com", "path": "/"},
        {"name": "b", "value": "2", "domain": "bar.com", "path": "/"},
    ])

    summary = summarize_driver_cookies(driver, domains=None)
    assert summary["count"] == 2


def test_summarize_driver_cookies_no_kwarg_backward_compat():
    """Calling without domains kwarg must still work exactly as before."""
    driver = _FakeDriver([
        {"name": "PHPSESSID", "value": "abc", "domain": ".123.net", "path": "/"},
    ])
    summary = summarize_driver_cookies(driver)
    assert summary["count"] == 1


def test_selenium_driver_to_requests_session_seeds_cookie_jar():
    driver = _FakeDriver([
        {"name": "sid", "value": "token", "domain": ".123.net", "path": "/"},
    ])

    session = selenium_driver_to_requests_session(driver, "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
    cookie_domains = [cookie.domain for cookie in session.cookies]
    assert "123.net" in cookie_domains
    assert session.headers["Referer"].startswith("https://secure.123.net/")
