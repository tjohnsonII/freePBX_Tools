from __future__ import annotations

from dataclasses import asdict

from webscraper.artifacts_contract import HandleArtifacts, HandleResult, TicketsAllContract, utc_now
from webscraper.paths import latest_run_pointer_path, runs_dir
from webscraper.utils.io import make_run_id, safe_write_json, utc_now_iso
from webscraper.utils.schema import validate_tickets_all


class RunManager:
    def __init__(
        self,
        source: str,
        handles: list[str],
        requested_by: str = "cli",
        *,
        mode: str | None = None,
        browser: str = "edge",
        base_url: str = "",
    ) -> None:
        self.started_utc = utc_now_iso()
        self.handles = handles
        self.source = source
        self.requested_by = requested_by
        self.mode = mode or ("all_handles" if len(handles) != 1 else "one_handle")
        self.browser = browser
        self.base_url = base_url
        self.run_id = make_run_id(
            handle=handles[0] if len(handles) == 1 else None,
            mode=self.mode,
            browser=self.browser,
            base_url=self.base_url,
            started_utc=self.started_utc,
            extra={"source": source, "requested_by": requested_by},
        )
        self.run_dir = runs_dir() / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "handles").mkdir(parents=True, exist_ok=True)
        self.state: dict[str, dict] = {}

    def initialize(self) -> None:
        metadata = {
            "run_id": self.run_id,
            "source": self.source,
            "requested_by": self.requested_by,
            "started_utc": self.started_utc,
            "browser": self.browser,
            "base_url": self.base_url,
            "mode": self.mode,
            "total_handles": len(self.handles),
        }
        safe_write_json(self.run_dir / "run_metadata.json", metadata)
        (self.run_dir / "handles.json").write_text("\n".join(self.handles) + "\n", encoding="utf-8")
        for handle in self.handles:
            self.state[handle] = asdict(
                HandleResult(
                    handle=handle,
                    status="failed",
                    error="not started",
                    started_utc=None,
                    finished_utc=None,
                    artifacts=asdict(HandleArtifacts()),
                    ticket_count=0,
                )
            )
        self.write_tickets_all()
        latest_run_pointer_path().write_text(self.run_id + "\n", encoding="utf-8")

    def mark_started(self, handle: str) -> None:
        row = self.state[handle]
        row["started_utc"] = utc_now()
        row["error"] = None
        self.write_tickets_all()

    def update_handle(self, handle: str, status: str, error: str | None, artifacts: dict[str, str | None], ticket_count: int) -> None:
        row = self.state[handle]
        row["status"] = status
        row["error"] = error
        row["artifacts"] = artifacts
        row["ticket_count"] = ticket_count
        row["finished_utc"] = utc_now()
        if row.get("started_utc") is None:
            row["started_utc"] = row["finished_utc"]
        self.write_tickets_all()

    def write_tickets_all(self) -> None:
        ok = sum(1 for v in self.state.values() if v.get("status") == "ok")
        failed = len(self.state) - ok
        payload = TicketsAllContract(
            run_id=self.run_id,
            generated_utc=utc_now(),
            source=self.source,
            handles=self.state,
            summary={"total_handles": len(self.state), "ok": ok, "failed": failed},
        ).to_dict()
        payload.update(
            {
                "schema_version": 1,
                "started_utc": self.started_utc,
                "finished_utc": utc_now_iso(),
                "browser": self.browser,
                "base_url": self.base_url,
                "mode": self.mode,
            }
        )
        validate_tickets_all(payload)
        safe_write_json(self.run_dir / "tickets_all.json", payload)
