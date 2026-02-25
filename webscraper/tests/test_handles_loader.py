from pathlib import Path

import pytest

from webscraper.handles_loader import load_handles_from_csv


def test_load_handles_from_csv_normalizes_and_dedupes(tmp_path: Path):
    csv_path = tmp_path / "handles.csv"
    rows = ["Handle", " abc ", "ABC", "", "def"]
    csv_path.write_text("\n".join(rows), encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_handles_from_csv(str(csv_path))


def test_load_handles_from_csv_requires_handle_column(tmp_path: Path):
    csv_path = tmp_path / "handles.csv"
    csv_path.write_text("NotHandle\nABC\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_handles_from_csv(str(csv_path))
