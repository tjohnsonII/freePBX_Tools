from __future__ import annotations

from pydantic import BaseModel


class HandleModel(BaseModel):
    handle: str
    first_seen_utc: str | None = None
    last_scrape_utc: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class TicketModel(BaseModel):
    ticket_id: str
    handle: str
    ticket_url: str | None = None
    title: str | None = None
    status: str | None = None
    created_utc: str | None = None
    updated_utc: str | None = None
    raw_json: str | None = None
    run_id: str | None = None


class ArtifactModel(BaseModel):
    ticket_id: str
    handle: str
    artifact_type: str
    path: str
    sha256: str | None = None
    created_utc: str | None = None
    run_id: str | None = None
