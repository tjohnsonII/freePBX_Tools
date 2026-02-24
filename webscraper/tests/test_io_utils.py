from __future__ import annotations

import json
from pathlib import Path

from webscraper.utils.io_utils import make_run_id, safe_write_json


def test_make_run_id_unique_across_multiple_calls() -> None:
    ids = {make_run_id() for _ in range(10)}
    assert len(ids) == 10


def test_safe_write_json_write_and_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "tickets_all.json"

    first_payload = {"schema_version": 1, "run_id": "run-1", "handles": {}}
    safe_write_json(target, first_payload)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == first_payload
    assert not target.with_suffix(target.suffix + ".tmp").exists()

    second_payload = {
        "schema_version": 1,
        "run_id": "run-2",
        "generated_utc": "2026-02-24T02:15:30Z",
        "handles": {"ABC": {"status": "ok"}},
        "summary": {"total_handles": 1, "ok": 1, "failed": 0},
    }
    safe_write_json(target, second_payload)

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == second_payload
    assert not target.with_suffix(target.suffix + ".tmp").exists()
