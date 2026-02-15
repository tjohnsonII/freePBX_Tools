import importlib.util
import json
import sqlite3
from pathlib import Path

from webscraper.db import create_run, init_db


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"


def load_module():
    spec = importlib.util.spec_from_file_location("scrape_all_handles", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_process_batch_output_imports_tickets_all_into_db(tmp_path):
    module = load_module()
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))
    run_id = create_run(str(db_path), "run-test", args_dict={"test": True}, out_dir=str(tmp_path))

    batch_out = tmp_path / "batch_001"
    batch_out.mkdir(parents=True)
    payload = {
        "KPM": [
            {
                "ticket_id": "123456789012",
                "url": "https://noc-tickets.123.net/ticket/123456789012",
                "title": "Imported from tickets_all",
                "status": "open",
            }
        ]
    }
    (batch_out / "tickets_all.json").write_text(json.dumps(payload), encoding="utf-8")

    success, failed = module.process_batch_output(str(db_path), run_id, batch_out, ["KPM"])

    conn = sqlite3.connect(db_path)
    tickets_count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    title = conn.execute("SELECT title FROM tickets WHERE handle='KPM' AND ticket_id='123456789012'").fetchone()[0]

    assert success == {"KPM"}
    assert failed == set()
    assert tickets_count > 0
    assert title == "Imported from tickets_all"


def test_process_batch_output_records_artifacts_when_no_tickets(tmp_path):
    module = load_module()
    db_path = tmp_path / "tickets.sqlite"
    init_db(str(db_path))
    run_id = create_run(str(db_path), "run-test-2", args_dict={"test": True}, out_dir=str(tmp_path))

    batch_out = tmp_path / "batch_002"
    debug_dir = batch_out / "debug"
    debug_dir.mkdir(parents=True)
    (debug_dir / "handle_page_WS7.html").write_text("<html>debug</html>", encoding="utf-8")

    success, failed = module.process_batch_output(str(db_path), run_id, batch_out, ["WS7"])

    conn = sqlite3.connect(db_path)
    status = conn.execute("SELECT last_status FROM handles WHERE handle='WS7'").fetchone()[0]
    artifact_count = conn.execute("SELECT COUNT(*) FROM ticket_artifacts WHERE run_id=?", (run_id,)).fetchone()[0]

    assert success == set()
    assert failed == {"WS7"}
    assert status == "failed"
    assert artifact_count > 0
