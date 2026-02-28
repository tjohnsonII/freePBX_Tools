from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys

import requests
from pathlib import Path

from webscraper.paths import runs_dir, tickets_db_path


DEPENDENCY_SETS: dict[str, list[tuple[str, str]]] = {
    "ticket-api": [
        ("fastapi", "fastapi>=0.115.0"),
        ("uvicorn", "uvicorn[standard]>=0.30.0"),
        ("multipart", "python-multipart>=0.0.9"),
    ],
    "webscraper-core": [
        ("requests", "requests>=2.31.0"),
        ("bs4", "beautifulsoup4>=4.12.0"),
        ("lxml", "lxml>=4.9.0"),
        ("selenium", "selenium>=4.20.0"),
        ("websocket", "websocket-client>=1.7.0"),
    ],
}


def find_newest_run_dir(scrape_runs_root: Path) -> Path | None:
    if not scrape_runs_root.exists():
        return None
    dirs = [p for p in scrape_runs_root.rglob("*") if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def run_pip_check() -> int:
    overall_missing = False
    for app_name, checks in DEPENDENCY_SETS.items():
        missing = [requirement for module, requirement in checks if importlib.util.find_spec(module) is None]
        if not missing:
            print(f"[OK] {app_name}: dependencies installed")
            continue
        overall_missing = True
        joined = " ".join(missing)
        print(f"[FAIL] {app_name}: missing dependencies")
        for requirement in missing:
            print(f"  - {requirement}")
        print(f"  Install: {sys.executable} -m pip install {joined}")
    return 1 if overall_missing else 0


def run_auth_route_doctor(api_base: str, domain: str, dry_run: bool) -> int:
    checks: list[tuple[str, bool, str]] = []

    def _record(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")

    try:
        health = requests.get(f"{api_base}/api/health", timeout=10)
        _record("GET /api/health", health.ok, f"status={health.status_code}")
    except Exception as exc:
        _record("GET /api/health", False, str(exc))
        return 1

    for route in [
        "/api/auth/import_from_browser",
        "/api/auth/sync_from_browser",
        "/api/auth/import-from-browser",
        "/api/auth/import-browser",
        "/api/auth/sync-from-browser",
    ]:
        response = requests.post(f"{api_base}{route}", json={}, timeout=10)
        _record(f"POST {route}", response.status_code in {200, 422}, f"status={response.status_code}")

    status_resp = requests.get(f"{api_base}/api/auth/status", timeout=10)
    _record("GET /api/auth/status", status_resp.ok, f"status={status_resp.status_code}")

    if not dry_run:
        import_resp = requests.post(
            f"{api_base}/api/auth/import_from_browser",
            json={"browser": "chrome", "profile": "Default", "domain": domain},
            timeout=30,
        )
        _record("POST /api/auth/import_from_browser", import_resp.ok, f"status={import_resp.status_code}")

    validate_resp = requests.get(f"{api_base}/api/auth/validate", params={"domain": domain}, timeout=20)
    validate_ok = validate_resp.ok and bool(validate_resp.json().get("ok"))
    _record("GET /api/auth/validate", validate_ok, f"status={validate_resp.status_code}")

    handles_resp = requests.post(
        f"{api_base}/api/scrape/handles",
        json={"handles": ["ABC"], "mode": "normal", "options": {"rescrape": False}},
        timeout=20,
    )
    body = {}
    try:
        body = handles_resp.json()
    except Exception:
        body = {}
    scrape_ok = handles_resp.status_code in {200, 400} and "Auth validation failed" not in str(body)
    _record("POST /api/scrape/handles", scrape_ok, f"status={handles_resp.status_code}")

    failures = [item for item in checks if not item[1]]
    print("\nSummary:")
    print(f"  Passed: {len(checks) - len(failures)}")
    print(f"  Failed: {len(failures)}")
    if failures:
        print("  Next steps: run auth import in UI, then re-run doctor.")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick doctor checks for ticket scraper DB + output artifacts")
    parser.add_argument("--db", default=str(tickets_db_path()))
    parser.add_argument("--output", default=str(runs_dir()))
    parser.add_argument("--pip-check", action="store_true", help="Validate package dependencies and print install commands")
    parser.add_argument("--auth-e2e", action="store_true", help="Doctor auth routes + validate + scrape smoke against running API")
    parser.add_argument("--api-base", default="http://127.0.0.1:8787")
    parser.add_argument("--domain", default="secure.123.net")
    parser.add_argument("--dry-run", action="store_true", help="Skip cookie import attempt")
    args = parser.parse_args()

    if args.pip_check:
        return run_pip_check()
    if args.auth_e2e:
        return run_auth_route_doctor(args.api_base.rstrip("/"), args.domain, args.dry_run)

    db_path = Path(args.db).resolve()
    output_root = Path(args.output).resolve()
    print(f"DB path: {db_path}")
    if not db_path.exists():
        print("[FAIL] DB file not found")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    handles_count = conn.execute("SELECT COUNT(*) c FROM handles").fetchone()["c"]
    tickets_count = conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
    print(f"counts: handles={handles_count} tickets={tickets_count}")

    print("last 10 handles:")
    for row in conn.execute(
        "SELECT handle,last_status,last_error,last_started_utc,last_finished_utc,last_run_id FROM handles ORDER BY COALESCE(last_finished_utc,last_scrape_utc) DESC LIMIT 10"
    ).fetchall():
        print(
            f"  - {row['handle']} status={row['last_status'] or '-'} error={row['last_error'] or '-'} "
            f"started={row['last_started_utc'] or '-'} finished={row['last_finished_utc'] or '-'} run={row['last_run_id'] or '-'}"
        )

    print("last 5 runs:")
    for row in conn.execute("SELECT run_id,started_utc,finished_utc,failure_reason FROM runs ORDER BY started_utc DESC LIMIT 5").fetchall():
        print(
            f"  - {row['run_id']} started={row['started_utc'] or '-'} finished={row['finished_utc'] or '-'} "
            f"failure_reason={row['failure_reason'] or '-'}"
        )

    newest = find_newest_run_dir(output_root / "scrape_runs")
    print(f"newest scrape_run dir: {newest if newest else '-'}")
    if newest:
        has_tickets_all = (newest / "tickets_all.json").exists()
        print(f"contains tickets_all.json: {has_tickets_all}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
