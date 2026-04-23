from __future__ import annotations

import json
from pathlib import Path

from webscraper.utils.io import make_run_id, safe_write_json


def test_make_run_id_deterministic() -> None:
    rid1 = make_run_id(
        handle="KPM",
        mode="one_handle",
        browser="edge",
        base_url="https://noc-tickets.123.net",
        started_utc="2026-02-24T02:54:12Z",
    )
    rid2 = make_run_id(
        handle="KPM",
        mode="one_handle",
        browser="edge",
        base_url="https://noc-tickets.123.net",
        started_utc="2026-02-24T02:54:12Z",
    )
    assert rid1 == rid2


def test_make_run_id_changes_with_browser() -> None:
    edge_id = make_run_id(
        handle="KPM",
        mode="one_handle",
        browser="edge",
        base_url="https://noc-tickets.123.net",
        started_utc="2026-02-24T02:54:12Z",
    )
    chrome_id = make_run_id(
        handle="KPM",
        mode="one_handle",
        browser="chrome",
        base_url="https://noc-tickets.123.net",
        started_utc="2026-02-24T02:54:12Z",
    )
    assert edge_id != chrome_id


def test_safe_write_json_atomic(tmp_path: Path) -> None:
    target = tmp_path / "tickets_all.json"
    payload = {"schema_version": 1, "run_id": "rid-1", "handles": {}}
    safe_write_json(target, payload)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob("tickets_all.json.tmp.*")) == []
