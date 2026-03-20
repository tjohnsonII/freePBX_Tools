from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class StateStore:
    repo_root: Path
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    auth: dict[str, Any] = field(default_factory=dict)
    cookies: dict[str, Any] = field(default_factory=dict)
    ticket_pipeline: dict[str, Any] = field(default_factory=dict)
    worker_paused: bool = False
    manager_running: bool = False

    def __post_init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        self.auth = {
            "authenticated": False,
            "mode": "none",
            "last_check": now,
            "last_success": None,
            "cookie_count": 0,
            "domains": [],
            "source": "none",
            "profile": "Profile 1",
            "browser": "chrome",
            "required_cookie_names_present": [],
            "missing_required_cookie_names": ["sessionid", "csrftoken"],
            "validation": {
                "url": "https://secure.123.net/",
                "http_status": 0,
                "ok": False,
                "reason": "not_validated",
            },
        }
        self.cookies = {
            "source": "none",
            "file_path": None,
            "cookie_count": 0,
            "domains": [],
            "last_loaded": None,
            "secure_count": 0,
            "http_only_count": 0,
            "sample_names": [],
            "missing_required_cookie_names": ["sessionid", "csrftoken"],
        }
        self.ticket_pipeline = {
            stage: {"status": "unknown", "timestamp": None, "message": "not run", "failure_reason": None}
            for stage in [
                "handles_loaded",
                "ticket_fetch_started",
                "ticket_fetch_succeeded",
                "db_updated",
                "ui_read_succeeded",
            ]
        }

    def set_pipeline_stage(self, stage: str, status: str, message: str, failure_reason: str | None = None) -> None:
        self.ticket_pipeline[stage] = {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "message": message,
            "failure_reason": failure_reason,
        }
