from __future__ import annotations

from pathlib import Path

from webscraper_manager.config import load_or_create_config, save_config


def test_load_or_create_config(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "webscraper").mkdir()
    cfg = load_or_create_config(tmp_path)
    assert cfg.config_file.exists()
    assert cfg.manager_home.exists()


def test_save_config_roundtrip(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "webscraper").mkdir()
    cfg = load_or_create_config(tmp_path)
    cfg.base_url = "http://127.0.0.1:9999"
    save_config(cfg)
    loaded = load_or_create_config(tmp_path)
    assert loaded.base_url == "http://127.0.0.1:9999"
