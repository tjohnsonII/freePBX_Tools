from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import dev_runtime  # type: ignore  # noqa: E402


def test_creationflags_windows_no_console(monkeypatch):
    monkeypatch.setattr(dev_runtime, "is_windows", lambda: True)
    flags = dev_runtime._creationflags()
    assert flags & int(getattr(dev_runtime.subprocess, "CREATE_NO_WINDOW", 0)) == int(
        getattr(dev_runtime.subprocess, "CREATE_NO_WINDOW", 0)
    )
    assert flags & int(getattr(dev_runtime.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) == int(
        getattr(dev_runtime.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def test_runtime_state_update(tmp_path):
    entry = {
        "service": "demo",
        "pid": 123,
        "cmd": ["python", "-m", "demo"],
        "command": "python -m demo",
        "cwd": str(tmp_path),
        "log": str(tmp_path / "demo.log"),
        "started_at": 1,
    }
    dev_runtime.save_service_state(tmp_path, entry)
    dev_runtime.update_service_state(tmp_path, "demo", readiness_status="ready", readiness_reason="ok", degraded=False)
    payload = json.loads((tmp_path / "var" / "web-app-launcher" / "run_state.json").read_text(encoding="utf-8"))
    assert payload["services"]["demo"]["readiness_status"] == "ready"
    assert payload["services"]["demo"]["readiness_reason"] == "ok"


def test_inspection_reports_webscraper_ui_exists():
    payload = dev_runtime.inspect_web_stack(ROOT)
    assert "services" in payload
    assert "webscraper_ui" in payload["services"]
