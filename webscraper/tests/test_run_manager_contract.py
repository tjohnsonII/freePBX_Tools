from __future__ import annotations

import json

from webscraper.run_manager import RunManager


def test_tickets_all_written_for_handles(tmp_path, monkeypatch):
    from webscraper import paths
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    rm = RunManager(source="test", handles=["ABC", "XYZ"])
    rm.initialize()
    rm.mark_started("ABC")
    rm.update_handle("ABC", "ok", None, {"tickets_json": "handles/ABC/tickets.json"}, 3)

    payload = json.loads((rm.run_dir / "tickets_all.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["run_id"]
    assert payload["summary"]["total_handles"] == 2
    assert payload["handles"]["ABC"]["status"] == "ok"
    assert payload["handles"]["XYZ"]["error"] == "not started"


def test_latest_run_pointer_created(tmp_path, monkeypatch):
    from webscraper import paths
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    rm = RunManager(source="test", handles=[])
    rm.initialize()
    ptr = tmp_path / "var" / "runs" / "LATEST_RUN.txt"
    assert ptr.exists()
    assert ptr.read_text(encoding="utf-8").strip() == rm.run_id
