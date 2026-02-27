from webscraper.ticket_api.app import map_batch_mode
from webscraper.ticket_api.auth import (
    filter_cookies_for_domains,
    parse_cookies,
    parse_cookies_from_cookie_header,
    parse_cookies_from_json,
    parse_cookies_from_netscape,
)


def test_mode_mapping_latest_to_incremental():
    assert map_batch_mode("latest") == "incremental"
    assert map_batch_mode("full") == "full"


def test_parse_json_cookie_array():
    cookies = parse_cookies_from_json('[{"name":"sid","value":"x","domain":"secure.123.net"}]')
    assert len(cookies) == 1
    assert cookies[0].domain == "secure.123.net"


def test_parse_json_wrapper_and_playwright():
    wrapper = parse_cookies_from_json('{"cookies":[{"name":"a","value":"1","domain":"123.net"}]}')
    assert len(wrapper) == 1
    playwright = parse_cookies_from_json('{"cookies":[{"name":"sid","value":"x","domain":"secure.123.net"}],"origins":[]}')
    assert len(playwright) == 1


def test_parse_netscape_cookie_text():
    payload = """# Netscape HTTP Cookie File
.secure.123.net\tTRUE\t/\tTRUE\t1730000000\tsid\tabc
"""
    cookies = parse_cookies_from_netscape(payload)
    assert len(cookies) == 1
    assert cookies[0].domain == "secure.123.net"


def test_parse_cookie_header_with_default_domain():
    cookies = parse_cookies_from_cookie_header("Cookie: sid=abc; csrftoken=xyz", "secure.123.net")
    assert len(cookies) == 2
    assert {c.domain for c in cookies} == {"secure.123.net"}


def test_domain_filtering_subdomain_matching():
    parsed, _ = parse_cookies(
        '[{"name":"sid","value":"x","domain":"sub.secure.123.net"},{"name":"x","value":"2","domain":"other.com"}]',
        "cookies.json",
        None,
    )
    kept = filter_cookies_for_domains(parsed, ["secure.123.net"])
    assert len(kept) == 1
    assert kept[0].name == "sid"
