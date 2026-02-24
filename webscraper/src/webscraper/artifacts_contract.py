from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class HandleArtifacts:
    debug_log: str | None = None
    handle_page_html: str | None = None
    handle_page_png: str | None = None
    company_probe_json: str | None = None
    tickets_json: str | None = None


@dataclass
class HandleResult:
    handle: str
    status: Literal["ok", "failed"]
    error: str | None
    started_utc: str | None
    finished_utc: str | None
    artifacts: dict[str, str | None]
    ticket_count: int = 0


@dataclass
class TicketsAllSummary:
    total_handles: int
    ok: int
    failed: int


@dataclass
class TicketsAllContract:
    run_id: str
    generated_utc: str
    source: str
    handles: dict[str, dict]
    summary: dict[str, int]
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)
