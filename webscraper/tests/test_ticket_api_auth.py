from webscraper.ticket_api.app import map_batch_mode
from webscraper.ticket_api.auth import normalize_cookie_input


def test_mode_mapping_latest_to_incremental():
    assert map_batch_mode("latest") == "incremental"
    assert map_batch_mode("full") == "full"


def test_parse_netscape_cookie_text():
    payload = """# Netscape HTTP Cookie File
.secure.123.net\tTRUE\t/\tTRUE\t1730000000\tsid\tabc
"""
    cookies = normalize_cookie_input(payload, ["secure.123.net"])
    assert len(cookies) == 1
    assert cookies[0]["domain"] == "secure.123.net"


def test_parse_cookie_header_for_selected_domains():
    cookies = normalize_cookie_input("Cookie: sid=abc; csrftoken=xyz", ["secure.123.net", "noc-tickets.123.net"])
    assert len(cookies) == 4
    assert {c["domain"] for c in cookies} == {"secure.123.net", "noc-tickets.123.net"}


def test_parse_json_cookie_array_filtered_domains():
    cookies = normalize_cookie_input(
        [{"name": "sid", "value": "1", "domain": "sub.secure.123.net"}, {"name": "x", "value": "2", "domain": "other.com"}],
        ["secure.123.net"],
    )
    assert len(cookies) == 1
    assert cookies[0]["name"] == "sid"
