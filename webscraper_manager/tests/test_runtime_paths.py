from pathlib import Path

from webscraper_manager.cli import _load_webscraper_pids, _save_webscraper_pids


def test_save_webscraper_pids_creates_runtime_dir(tmp_path: Path) -> None:
    root = tmp_path
    payload = {"api": {"pid": 1234}}

    _save_webscraper_pids(root, payload)

    pids_path = root / "webscraper" / "var" / "runtime" / "pids.json"
    assert pids_path.is_file()
    assert pids_path.read_text(encoding="utf-8").strip().startswith("{")


def test_load_webscraper_pids_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    root = tmp_path

    loaded = _load_webscraper_pids(root)

    assert loaded == {}
