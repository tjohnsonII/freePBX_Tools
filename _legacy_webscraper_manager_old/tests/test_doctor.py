from __future__ import annotations

from pathlib import Path

from webscraper_manager.config import load_or_create_config
from webscraper_manager.doctor import run_doctor


def test_doctor_reports_expected_checks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    ws = tmp_path / "webscraper"
    (ws / "src" / "webscraper").mkdir(parents=True)
    (ws / "ticket-ui").mkdir(parents=True)
    (ws / "requirements.txt").write_text("selenium\n", encoding="utf-8")
    (ws / "ticket-ui" / "package.json").write_text("{}", encoding="utf-8")

    cfg = load_or_create_config(tmp_path)
    findings = run_doctor(cfg)
    keys = {item.key for item in findings}

    assert "python_version" in keys
    assert "dep_selenium" in keys
    assert "port_8787" in keys
