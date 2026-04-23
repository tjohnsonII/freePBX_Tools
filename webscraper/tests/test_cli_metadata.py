import json
from pathlib import Path

import pytest

from webscraper.cli.main import main


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Selenium ticket scraper" in out


def test_cli_dry_run_writes_run_metadata(tmp_path: Path) -> None:
    rc = main(["--dry-run", "--out", str(tmp_path)])
    assert rc == 0

    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert run_dirs, "expected run directory to be created"

    metadata_path = run_dirs[0] / "run_metadata.json"
    assert metadata_path.exists()

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    for key in ("timestamp_utc", "run_id", "out_dir", "mode"):
        assert key in data
    assert data["mode"] == "cli_dry_run"
