from webscraper.auth import chrome_cdp


class _Ws:
    pass


def test_open_target_session_reuses_existing_secure_tab(monkeypatch):
    ws = _Ws()
    calls = []

    def fake_cdp_call(_ws, method, params=None, **_kwargs):
        calls.append(method)
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {"targetId": "tab-blank", "type": "page", "url": "about:blank"},
                    {"targetId": "tab-secure", "type": "page", "url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"},
                ]
            }
        if method == "Target.attachToTarget":
            assert params and params.get("targetId") == "tab-secure"
            return {"sessionId": "session-1"}
        if method == "Network.getAllCookies":
            return {"cookies": []}
        raise AssertionError(f"Unexpected CDP method: {method}")

    monkeypatch.setattr(chrome_cdp, "cdp_call", fake_cdp_call)
    chrome_cdp.get_all_cookies(ws)

    assert "Target.createTarget" not in calls
    assert calls[0] == "Target.getTargets"


def test_get_all_cookies_falls_back_to_browser_scope_when_target_empty(monkeypatch):
    ws = _Ws()
    calls = []

    def fake_cdp_call(_ws, method, params=None, session_id=None):
        calls.append((method, bool(session_id)))
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {"targetId": "tab-secure", "type": "page", "url": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"},
                ]
            }
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method == "Network.getAllCookies" and session_id:
            return {"cookies": []}
        if method == "Network.getAllCookies" and not session_id:
            return {"cookies": [{"name": "PHPSESSID", "domain": "secure.123.net"}]}
        raise AssertionError(f"Unexpected CDP method: {method}")

    monkeypatch.setattr(chrome_cdp, "cdp_call", fake_cdp_call)
    cookies = chrome_cdp.get_all_cookies(ws)

    assert cookies == [{"name": "PHPSESSID", "domain": "secure.123.net"}]
    assert ("Network.getAllCookies", True) in calls
    assert ("Network.getAllCookies", False) in calls
