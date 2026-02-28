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


def test_selenium_driver_to_requests_session_seeds_cookie_jar():
    driver = _FakeDriver([
        {"name": "sid", "value": "token", "domain": ".123.net", "path": "/"},
    ])

    session = selenium_driver_to_requests_session(driver, "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
    cookie_domains = [cookie.domain for cookie in session.cookies]
    assert "123.net" in cookie_domains
    assert session.headers["Referer"].startswith("https://secure.123.net/")
