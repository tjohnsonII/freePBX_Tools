from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field


class SystemState(str, Enum):
    idle = "idle"
    detecting_browser = "detecting_browser"
    seeding_auth = "seeding_auth"
    validating_auth = "validating_auth"
    scraping = "scraping"
    persisting = "persisting"
    exposing_results = "exposing_results"
    error = "error"


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class OrchestrationJob(BaseModel):
    job_id: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    current_state: JobState = JobState.queued
    current_step: SystemState = SystemState.idle
    records_found: int = 0
    records_written: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepResponse(BaseModel):
    ok: bool
    state: SystemState
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class SystemStatus(BaseModel):
    backend_health: str = "ok"
    browser_status: str = "unknown"
    auth_status: str = "unknown"
    secure_tab_status: str = "unknown"
    session_status: str = "unknown"
    cookies_status: str = "unknown"
    validation_status: str = "unknown"
    current_job: OrchestrationJob | None = None
    last_successful_scrape: str | None = None
    db_counts: dict[str, int] = Field(default_factory=lambda: {"tickets": 0, "handles": 0})
    last_error: str | None = None
    state: SystemState = SystemState.idle


@dataclass
class OrchestratorDeps:
    detect_browser: Callable[[], dict[str, Any]]
    seed_auth: Callable[[], dict[str, Any]]
    validate_auth: Callable[[], dict[str, Any]]
    run_scrape: Callable[[str], dict[str, Any]]
    persist_records: Callable[[str, dict[str, Any]], dict[str, Any]]
    db_status: Callable[[], dict[str, int]]


class WebScraperOrchestrator:
    def __init__(self, deps: OrchestratorDeps, logger: logging.Logger) -> None:
        self._deps = deps
        self._logger = logger
        self._lock = threading.Lock()
        self._jobs: list[OrchestrationJob] = []
        self._browser_attached = False
        self._status = SystemStatus()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _log_transition(self, event: str, **payload: Any) -> None:
        data = {"event": event, "ts": self._now(), **payload}
        self._logger.info("orchestration_event=%s", data)

    def _update_state(self, state: SystemState, *, error: str | None = None) -> None:
        self._status.state = state
        if error:
            self._status.last_error = error
        self._log_transition("state_change", state=state.value, error=error)

    def _new_job(self) -> OrchestrationJob:
        job = OrchestrationJob(job_id=str(uuid.uuid4()), created_at=self._now())
        self._jobs.insert(0, job)
        return job

    def system_status(self) -> SystemStatus:
        with self._lock:
            self._status.db_counts = self._deps.db_status()
            return self._status.model_copy(deep=True)

    def list_jobs(self) -> list[OrchestrationJob]:
        with self._lock:
            return [job.model_copy(deep=True) for job in self._jobs]

    def get_job(self, job_id: str) -> OrchestrationJob | None:
        with self._lock:
            for job in self._jobs:
                if job.job_id == job_id:
                    return job.model_copy(deep=True)
        return None

    def _build_browser_step(self, result: dict[str, Any]) -> StepResponse:
        self._browser_attached = bool(result.get("available", False))
        self._status.browser_status = str(result.get("status") or ("available" if self._browser_attached else "unavailable"))
        self._status.secure_tab_status = "detected" if bool(result.get("secure_tab_open")) else "not_found"
        self._status.session_status = "detected" if bool(result.get("authenticated_session")) else "not_detected"
        detail = str(result.get("message") or ("Browser detected" if self._browser_attached else "No browser available"))
        self._update_state(SystemState.idle)
        return StepResponse(ok=self._browser_attached, state=SystemState.detecting_browser, detail=detail, data=result)

    def record_browser_detection(self, result: dict[str, Any]) -> StepResponse:
        with self._lock:
            self._update_state(SystemState.detecting_browser)
            return self._build_browser_step(result)

    def detect_browser(self) -> StepResponse:
        with self._lock:
            self._update_state(SystemState.detecting_browser)
            if self._browser_attached:
                return StepResponse(ok=True, state=SystemState.detecting_browser, detail="Browser already attached", data={"idempotent": True})
            try:
                result = self._deps.detect_browser()
                return self._build_browser_step(result)
            except Exception as exc:  # pragma: no cover - defensive
                message = f"Browser detection failed: {exc}"
                self._status.browser_status = "browser_detection_failure"
                self._update_state(SystemState.error, error=message)
                return StepResponse(ok=False, state=SystemState.detecting_browser, detail=message)

    def seed_auth(self) -> StepResponse:
        with self._lock:
            self._update_state(SystemState.seeding_auth)
            result = self._deps.seed_auth()
            seeded = bool(result.get("seeded", False))
            self._status.auth_status = "seeded" if seeded else "not_seeded"
            self._status.cookies_status = "seeded" if seeded else "not_seeded"
            detail = "Auth seeded" if seeded else "Auth seeding returned no credentials"
            self._update_state(SystemState.idle)
            return StepResponse(ok=seeded, state=SystemState.seeding_auth, detail=detail, data=result)

    def validate_auth(self) -> StepResponse:
        with self._lock:
            self._update_state(SystemState.validating_auth)
            result = self._deps.validate_auth()
            authenticated = bool(result.get("authenticated", False))
            self._status.auth_status = "valid" if authenticated else "invalid"
            self._status.validation_status = "passed" if authenticated else "failed"
            self._status.session_status = "validated" if authenticated else "not_validated"
            detail = "Auth is valid" if authenticated else "Auth is invalid"
            self._update_state(SystemState.idle)
            return StepResponse(ok=authenticated, state=SystemState.validating_auth, detail=detail, data=result)

    def run_scrape(self) -> OrchestrationJob:
        with self._lock:
            job = self._new_job()
            job.current_state = JobState.running
            job.started_at = self._now()
            job.current_step = SystemState.scraping
            self._status.current_job = job
            self._update_state(SystemState.scraping)
            self._log_transition("job_created", job_id=job.job_id)

            try:
                scrape_result = self._deps.run_scrape(job.job_id)
                records = int(scrape_result.get("records_found", 0))
                job.records_found = records
                job.current_step = SystemState.persisting
                self._update_state(SystemState.persisting)
                persist_result = self._deps.persist_records(job.job_id, scrape_result)
                job.records_written = int(persist_result.get("records_written", 0))
                job.current_step = SystemState.exposing_results
                self._update_state(SystemState.exposing_results)
                job.current_state = JobState.completed
                job.completed_at = self._now()
                self._status.last_successful_scrape = job.completed_at
                self._status.last_error = None
                self._status.db_counts = self._deps.db_status()
                self._update_state(SystemState.idle)
            except Exception as exc:
                job.current_state = JobState.failed
                job.completed_at = self._now()
                job.error_message = str(exc)
                self._status.last_error = str(exc)
                self._update_state(SystemState.error, error=str(exc))

            self._status.current_job = job
            return job.model_copy(deep=True)

    def run_end_to_end(self) -> dict[str, Any]:
        step_results: list[StepResponse] = []
        detect = self.detect_browser()
        step_results.append(detect)
        if not detect.ok:
            job = self._new_job()
            job.current_state = JobState.failed
            job.current_step = SystemState.detecting_browser
            job.error_message = detect.detail
            job.completed_at = self._now()
            self._status.current_job = job
            return {"ok": False, "steps": [step.model_dump() for step in step_results], "job": job.model_dump()}

        seed = self.seed_auth()
        step_results.append(seed)
        validate = self.validate_auth()
        step_results.append(validate)
        if not validate.ok:
            job = self._new_job()
            job.current_state = JobState.failed
            job.current_step = SystemState.validating_auth
            job.error_message = validate.detail
            job.completed_at = self._now()
            self._status.current_job = job
            return {"ok": False, "steps": [step.model_dump() for step in step_results], "job": job.model_dump()}

        job = self.run_scrape()
        return {
            "ok": job.current_state == JobState.completed,
            "steps": [step.model_dump() for step in step_results],
            "job": job.model_dump(),
        }
