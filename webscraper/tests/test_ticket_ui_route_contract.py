from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_validate_auth_uses_get_contract_in_ui() -> None:
    page = (_repo_root() / "webscraper" / "ticket-ui" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert 'apiGet<ValidateResponse>("/api/auth/validate?domain=secure.123.net&timeout_seconds=10")' in page


def test_ticket_ui_proxy_defaults_to_ticket_api_port_8788() -> None:
    proxy_route = (_repo_root() / "webscraper" / "ticket-ui" / "app" / "api" / "[...path]" / "route.ts").read_text(encoding="utf-8")
    next_cfg = (_repo_root() / "webscraper" / "ticket-ui" / "next.config.js").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8788" in proxy_route
    assert "http://127.0.0.1:8788" in next_cfg


def test_launch_login_uses_existing_backend_route() -> None:
    page = (_repo_root() / "webscraper" / "ticket-ui" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert '"/api/auth/launch-browser"' in page


def test_orchestration_dashboard_exposes_selenium_fallback_route() -> None:
    dashboard = (_repo_root() / "webscraper" / "ticket-ui" / "app" / "components" / "OrchestrationDashboard.tsx").read_text(encoding="utf-8")
    assert "Run Selenium Fallback Scrape" in dashboard
    assert '"/api/scrape/selenium_fallback"' in dashboard
    assert "`/api/jobs/status/${start.job_id}`" in dashboard
    assert "`/jobs/${start.job_id}`" not in dashboard


def test_ticket_ui_exposes_backend_job_status_proxy_route() -> None:
    proxy_route = (_repo_root() / "webscraper" / "ticket-ui" / "app" / "api" / "jobs" / "status" / "[jobId]" / "route.ts").read_text(encoding="utf-8")
    assert 'const API_TARGET = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8788";' in proxy_route
    assert 'const url = `${API_TARGET}/jobs/${jobId}`;' in proxy_route
