from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .event_bus import EventBus
from .state_store import StateStore


class TicketPipelineService:
    def __init__(self, state: StateStore, events: EventBus) -> None:
        self.state = state
        self.events = events
        self.failed_jobs: list[dict[str, Any]] = []
        self.recent_tickets: list[dict[str, Any]] = []
        self.recent_handles: list[dict[str, Any]] = [{"handle": "jdoe", "team": "noc", "last_seen": datetime.now(UTC).isoformat()}]

    async def test_handles(self) -> dict[str, Any]:
        await self.events.emit("info", "tickets", "HANDLES_FETCH_STARTED", "Handle fetch started", {})
        self.state.set_pipeline_stage("handles_loaded", "success", "Loaded handles: 1")
        await self.events.emit("info", "tickets", "HANDLES_FETCH_SUCCESS", "Handle fetch succeeded", {"count": len(self.recent_handles)})
        return {"success": True, "count": len(self.recent_handles), "handles": self.recent_handles}

    async def test_ticket_fetch(self) -> dict[str, Any]:
        await self.events.emit("info", "tickets", "TICKETS_FETCH_STARTED", "Ticket fetch started", {})
        self.state.set_pipeline_stage("ticket_fetch_started", "success", "Ticket fetch started")
        if not self.state.auth.get("authenticated"):
            msg = "blocked: auth not validated"
            self.state.set_pipeline_stage("ticket_fetch_succeeded", "failed", msg, "auth_not_valid")
            self.failed_jobs.append({"timestamp": datetime.now(UTC).isoformat(), "reason": msg})
            await self.events.emit("error", "tickets", "TICKETS_FETCH_FAILED", "Ticket fetch failed", {"reason": msg})
            return {"success": False, "reason": msg, "tickets": []}

        ticket = {
            "id": f"T-{int(datetime.now().timestamp())}",
            "subject": "Sample ticket",
            "status": "open",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.recent_tickets = [ticket, *self.recent_tickets][:50]
        self.state.set_pipeline_stage("ticket_fetch_succeeded", "success", "Ticket fetch succeeded")
        self.state.set_pipeline_stage("db_updated", "success", "Mock DB updated")
        self.state.set_pipeline_stage("ui_read_succeeded", "success", "API returned recent tickets")
        await self.events.emit("info", "tickets", "TICKETS_FETCH_SUCCESS", "Ticket fetch succeeded", {"count": 1})
        await self.events.emit("info", "db", "DB_WRITE_SUCCESS", "DB write succeeded", {"inserted": 1})
        await self.events.emit("info", "ui", "UI_READ_SUCCESS", "UI read succeeded", {})
        return {"success": True, "tickets": [ticket]}

    async def run_once(self) -> dict[str, Any]:
        await self.test_handles()
        return await self.test_ticket_fetch()

    def pipeline(self) -> dict[str, Any]:
        return self.state.ticket_pipeline
