from webscraper.ticket_api import app as appmod


def test_ticket_api_doctor_reports_missing_python_multipart(monkeypatch, capsys):
    monkeypatch.setattr(appmod.importlib.util, "find_spec", lambda name: None if name == "multipart" else object())
    rc = appmod.doctor_command()
    assert rc == 1
    captured = capsys.readouterr()
    assert "Missing dependency python-multipart" in captured.err


def test_ticket_api_pip_check_prints_install_command(monkeypatch, capsys):
    def fake_find_spec(name: str):
        return None if name == "multipart" else object()

    monkeypatch.setattr(appmod.importlib.util, "find_spec", fake_find_spec)
    rc = appmod.pip_check_command()
    assert rc == 1
    out = capsys.readouterr().out
    assert "python-multipart>=0.0.9" in out
    assert "-m pip install" in out
