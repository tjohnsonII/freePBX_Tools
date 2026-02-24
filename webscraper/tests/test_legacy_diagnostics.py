from webscraper import ultimate_scraper_legacy as legacy


def test_classify_empty_reason_deterministic():
    assert legacy._classify_empty_reason("https://secure.123.net/login", "Sign in", "password") == "auth_required"
    assert legacy._classify_empty_reason("https://10.123.203.1", "Customers", "redirect") == "redirect_gateway"
    assert legacy._classify_empty_reason("https://noc.123.net/customers", "Customers", "plain html without markers") == "selector_mismatch"
    assert legacy._classify_empty_reason("https://noc.123.net/customers", "Customers", "ticket table is empty") == "no_tickets"
