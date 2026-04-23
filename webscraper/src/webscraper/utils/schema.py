from __future__ import annotations

TICKETS_ALL_SCHEMA_VERSION = 1


def validate_tickets_all(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("tickets_all payload must be an object")
    if data.get("schema_version") != TICKETS_ALL_SCHEMA_VERSION:
        raise ValueError(f"tickets_all.schema_version must be {TICKETS_ALL_SCHEMA_VERSION}")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("tickets_all.run_id must be a non-empty string")

    has_handles = isinstance(data.get("handles"), dict)
    has_legacy_records = isinstance(data.get("items"), list) or isinstance(data.get("handles_map"), dict)
    if not (has_handles or has_legacy_records):
        raise ValueError("tickets_all must include a handles object (or legacy handle records)")
