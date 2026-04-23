from pathlib import Path

import pytest

from webscraper import handles_loader as loader
from webscraper.handles_loader import load_handles, load_handles_from_csv


def test_load_handles_from_csv_normalizes_and_dedupes(tmp_path: Path):
    csv_path = tmp_path / "handles.csv"
    rows = ["Handle", " abc ", "ABC", "", "def"]
    csv_path.write_text("\n".join(rows), encoding="utf-8")

    handles = load_handles_from_csv(str(csv_path))
    assert handles == ["ABC", "DEF"]


def test_load_handles_from_csv_requires_handle_column(tmp_path: Path):
    csv_path = tmp_path / "handles.csv"
    csv_path.write_text("Account\nABC\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_handles_from_csv(str(csv_path))


def test_load_handles_prefers_csv_over_handles_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    csv_path = tmp_path / "123NET Admin.csv"
    txt_path = tmp_path / "var" / "handles.txt"
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("Handle\nA\nB\n", encoding="utf-8")
    txt_path.write_text("C\n", encoding="utf-8")

    monkeypatch.setattr(loader, "CSV_PATH", csv_path)
    monkeypatch.setattr(loader, "HANDLES_TXT", txt_path)

    assert load_handles() == ["A", "B"]


def test_load_handles_falls_back_to_handles_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    txt_path = tmp_path / "var" / "handles.txt"
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("A\n# comment\nB\n", encoding="utf-8")

    monkeypatch.setattr(loader, "CSV_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(loader, "HANDLES_TXT", txt_path)

    assert load_handles() == ["A", "B"]
