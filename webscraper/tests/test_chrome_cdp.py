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
