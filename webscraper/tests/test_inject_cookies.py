from webscraper.auth.inject_cookies import inject_imported_cookies


class FakeDriver:
    def __init__(self):
        self.current_url = ""
        self.cookies = []
        self.refreshes = 0

    def get(self, url: str):
        self.current_url = url

    def add_cookie(self, cookie):
        self.cookies.append(cookie)

    def refresh(self):
        self.refreshes += 1


def test_inject_imported_cookies_domain_and_secure_filter(monkeypatch):
    monkeypatch.setattr(
        "webscraper.auth.inject_cookies.load_imported_cookies",
        lambda: [
            {"name": "a", "value": "1", "domain": ".secure.123.net", "secure": True},
            {"name": "b", "value": "2", "domain": "noc-tickets.123.net", "secure": True},
            {"name": "c", "value": "3", "domain": "10.123.203.1", "secure": True},
            {"name": "d", "value": "4", "domain": "10.123.203.1", "secure": False},
        ],
    )
    driver = FakeDriver()

    meta = inject_imported_cookies(
        driver,
        ["https://secure.123.net/", "https://noc-tickets.123.net/", "http://10.123.203.1/"],
    )

    assert meta["applied"] == 3
    assert meta["skipped"] >= 1
    assert "secure.123.net" in meta["hosts"]
    assert "noc-tickets.123.net" in meta["hosts"]
    assert "10.123.203.1" in meta["hosts"]
    assert any(cookie["name"] == "d" for cookie in driver.cookies)
    assert all(cookie["name"] != "c" for cookie in driver.cookies)
    assert all(not cookie["domain"].startswith(".") for cookie in driver.cookies)
