from __future__ import annotations

import logging

from webscraper.ticket_api.orchestration import OrchestratorDeps, WebScraperOrchestrator, JobState


def _build_orchestrator(*, browser_ok=True, auth_valid=True, scrape_error: str | None = None, persist_error: str | None = None):
    def detect_browser():
        return {"available": browser_ok}

    def seed_auth():
        return {"seeded": browser_ok}

    def validate_auth():
        return {"authenticated": auth_valid}

    def run_scrape(_job_id: str):
        if scrape_error:
            raise RuntimeError(scrape_error)
        return {"records_found": 4}

    def persist_records(_job_id: str, _payload: dict):
        if persist_error:
            raise RuntimeError(persist_error)
        return {"records_written": 4}

    def db_status():
        return {"tickets": 100, "handles": 10}

    deps = OrchestratorDeps(
        detect_browser=detect_browser,
        seed_auth=seed_auth,
        validate_auth=validate_auth,
        run_scrape=run_scrape,
        persist_records=persist_records,
        db_status=db_status,
    )
    return WebScraperOrchestrator(deps=deps, logger=logging.getLogger("test.orchestrator"))


def test_no_browser_available_path():
    orchestrator = _build_orchestrator(browser_ok=False)
    result = orchestrator.run_end_to_end()
    assert result["ok"] is False
    assert result["job"]["current_state"] == JobState.failed
    assert "No browser available" in (result["job"]["error_message"] or "")


def test_browser_available_but_not_logged_in_path():
    orchestrator = _build_orchestrator(browser_ok=True, auth_valid=False)
    result = orchestrator.run_end_to_end()
    assert result["ok"] is False
    assert result["job"]["current_state"] == JobState.failed
    assert result["job"]["current_step"] == "validating_auth"


def test_auth_valid_but_scrape_fails_path():
    orchestrator = _build_orchestrator(scrape_error="scrape failed")
    job = orchestrator.run_scrape()
    assert job.current_state == JobState.failed
    assert job.error_message == "scrape failed"


def test_scrape_succeeds_but_db_write_fails_path():
    orchestrator = _build_orchestrator(persist_error="db write failed")
    job = orchestrator.run_scrape()
    assert job.current_state == JobState.failed
    assert job.error_message == "db write failed"


def test_full_success_path():
    orchestrator = _build_orchestrator()
    result = orchestrator.run_end_to_end()
    assert result["ok"] is True
    assert result["job"]["current_state"] == JobState.completed
    assert result["job"]["records_found"] == 4
    assert result["job"]["records_written"] == 4
