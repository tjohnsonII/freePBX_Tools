from webscraper.auth import imported_cookies


def test_save_and_meta_roundtrip(tmp_path, monkeypatch):
    store_path = tmp_path / "auth" / "imported_cookies.json"
    monkeypatch.setattr(imported_cookies, "_IMPORTED_COOKIES_PATH", store_path)

    meta = imported_cookies.save_imported_cookies(
        {
            "cookies": [
                {"name": "a", "value": "1", "domain": ".secure.123.net", "expirationDate": 1730000000},
                {"name": "b", "value": "2", "domain": "secure.123.net", "path": "/foo", "expires": 1730001000},
            ]
        }
    )

    assert meta["hasImportedCookies"] is True
    assert meta["count"] == 2
    assert "secure.123.net" in meta["domains"]

    loaded = imported_cookies.load_imported_cookies()
    assert len(loaded) == 2
    assert loaded[0]["path"] == "/"
    assert loaded[0]["expiry"] == 1730000000
    assert loaded[1]["path"] == "/foo"

    status = imported_cookies.get_imported_cookie_meta()
    assert status["count"] == 2
    assert status["stored_utc"]


def test_invalid_cookie_payload_rejected(tmp_path, monkeypatch):
    store_path = tmp_path / "auth" / "imported_cookies.json"
    monkeypatch.setattr(imported_cookies, "_IMPORTED_COOKIES_PATH", store_path)

    try:
        imported_cookies.save_imported_cookies({"cookies": [{"name": "a", "domain": "secure.123.net"}]})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "required fields" in str(exc)


def test_clear_cookies(tmp_path, monkeypatch):
    store_path = tmp_path / "auth" / "imported_cookies.json"
    monkeypatch.setattr(imported_cookies, "_IMPORTED_COOKIES_PATH", store_path)
    imported_cookies.save_imported_cookies([{"name": "a", "value": "1", "domain": "secure.123.net"}])
    assert store_path.exists()

    imported_cookies.clear_imported_cookies()
    assert not store_path.exists()
    assert imported_cookies.get_imported_cookie_meta()["hasImportedCookies"] is False


def test_domain_inferred_from_host_only(tmp_path, monkeypatch):
    store_path = tmp_path / "auth" / "imported_cookies.json"
    monkeypatch.setattr(imported_cookies, "_IMPORTED_COOKIES_PATH", store_path)
    imported_cookies.save_imported_cookies(
        {
            "cookies": [
                {"name": "a", "value": "1", "hostOnly": "secure.123.net", "extra": "drop-me"},
            ]
        }
    )
    loaded = imported_cookies.load_imported_cookies()
    assert loaded[0]["domain"] == "secure.123.net"
    assert "extra" not in loaded[0]
