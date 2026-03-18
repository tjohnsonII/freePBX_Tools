# Webscraper End-to-End Architecture Review & Remediation Plan

## A) Executive summary

- The runtime is **still centered on `ultimate_scraper_legacy.py`**, while most newer modules (`/scrape`, `/browser`, `/parsers`, `/core`) are mostly wrappers/re-exports; this creates a dual-architecture maintenance burden.
- Primary CLI entry (`python -m webscraper.ultimate_scraper`) resolves to `webscraper/cli/main.py` and then delegates to `webscraper.ultimate_scraper_legacy.main()` for non-dry-run behavior.
- There are **two storage stacks**: legacy discovery SQLite (`ticket_store.py` -> `tickets.db`) and ticket history SQLite (`db.py` -> `tickets.sqlite`), with partially overlapping schema intent.
- Ticket API (`ticket_api/app.py`) depends on an **external script path** (`scripts/scrape_all_handles.py`) and can fail with UI “Failed to fetch” when API is down, proxy target is wrong, CORS/proxy misconfig exists, or scraper subprocess exits nonzero.
- Auth is resilient in design (profile/programmatic/manual), but still fragile around redirect/login heuristic drift, cookie freshness, and dynamic DOM changes.
- Sensitive-data risk remains high: cookie files (`cookies.json`, `live_cookies.json`, `manual_cookies.json`) and auth diagnostics artifacts are written locally; this is acceptable operationally but must stay ignored and redacted.
- Main reliability pain points: startup/attach complexity, selector drift, auth redirect loops, and per-handle/per-ticket hard failures with limited structured error codes.
- Main performance pain points: repeated page loads, heavy artifact writes, optional screenshot-per-ticket, no delta strategy by `updated_utc` at scrape source, and limited controlled concurrency.
- P0 should prioritize **stability + observability + UI error surfacing**, not feature expansion.

---

## B) Detailed technical report

## 1) Architecture map

### 1.1 Primary entry points / commands

- **Main CLI wrapper**: `webscraper/ultimate_scraper.py` -> imports `webscraper.cli.main.main`.
- **CLI front door**: `webscraper/cli/main.py`
  - `--dry-run`: handles locally in `prepare_run_output_dir()`.
  - otherwise delegates to `webscraper.ultimate_scraper_legacy.main()`.
- **Legacy runtime (real engine)**: `webscraper/ultimate_scraper_legacy.py`
  - `main()` parses args/env/config and calls `selenium_scrape_tickets(...)` or `http_scrape_customers(...)`.
- **Discovery mode**: `webscraper/run_discovery.py` -> `webscraper.tickets_discovery.run_discovery(...)`.
- **API server**: `python -m webscraper.ticket_api.app`.
- **API + UI dev launcher**: `python webscraper/dev_server.py --ticket-stack`.
- **Tests**: `webscraper/tests/test_*.py` (pytest-based in repo config).

### 1.2 Module map and responsibilities

- `webscraper/auth/`
  - Strategy orchestration (`orchestrator.py`) and modes/types (`types.py`).
  - Strategy implementations:
    - `strategies/profile.py`: use existing browser profile.
    - `strategies/programmatic.py`: fill login form with creds.
    - `strategies/manual.py`: cookie file / pasted cookie flow.
  - `healthcheck.py`: auth confirmation heuristics + diagnostics artifacts.
  - `driver_factory.py`: auth-specific driver creation.

- `webscraper/browser/`
  - `edge_driver.py`: Edge startup/attach logic (largely duplicated from legacy).
  - `cookie_store.py`: wrappers to legacy cookie save/load functions.

- `webscraper/core/`
  - `config_loader.py`: load `ultimate_scraper_config.py`.
  - `paths.py`: output dir + metadata/text helpers.
  - `phase_logger.py`: phase logging helper.

- `webscraper/parsers/`
  - `ticket_detail.py`: table/label parsing, contact/attachment extraction.

- `webscraper/scrape/`
  - Mostly wrappers around legacy runtime (`runner.py`, `selenium_runner.py`, `ticket_details.py`, `ticket_search.py`, `retry_logic.py`).

- `webscraper/models/`
  - Lightweight dataclasses (`TicketUrlEntry`, `TicketDetails`).

- `webscraper/ticket_api/`
  - `app.py`: FastAPI endpoints, scrape job orchestration.
  - `db.py`: query/index layer for `tickets.sqlite`, including `scrape_jobs`.
  - `models.py`: response model definitions.

- `webscraper/ticket-ui/`
  - Next.js UI with `/api/*` proxy rewrites and client fetch helpers.

- Legacy/alternate paths
  - `webscraper/legacy/`: older scripts.
  - `webscraper/http_scraper.py`: HTTP-only scrape path.
  - `webscraper/tickets_discovery.py` + `ticket_store.py`: discovery crawler + separate sqlite store.

### 1.3 Full data flow (auth/session/cookies -> driver -> parse -> models -> storage -> API/UI)

1. CLI loads config/env (`ultimate_scraper_legacy.main`).
2. Auth strategy plan built (`build_auth_strategy_plan`) and/or direct driver init.
3. Driver startup/attach (`create_edge_driver`) with profile/remote-debug options.
4. Session establishment:
   - profile reuse, or programmatic login, or cookie injection.
   - auth checks via `auth/healthcheck.py` and login redirect heuristics.
5. Handle navigation/search (`selenium_scrape_tickets` internal handle loop).
6. Parse ticket links (`extract_ticket_urls_from_company_page` internal helper).
7. Optional ticket detail fetch (`scrape_ticket_details`) with auth-redirect retries.
8. Persist:
   - `webscraper/db.py` tables (`handles`, `runs`, `tickets`, `ticket_artifacts`),
   - plus JSON artifacts (`tickets_<HANDLE>.json`, `tickets_all.json`, per-ticket JSON/HTML/PNG).
9. API reads sqlite (`ticket_api/db.py`).
10. UI reads API (`ticket-ui/lib/api.ts`), renders handles/tickets and starts scrape jobs.

### 1.4 Architecture diagram (text)

```text
CLI / Runtime
  webscraper/ultimate_scraper.py
    -> webscraper/cli/main.py::main
      -> (default path) webscraper/ultimate_scraper_legacy.py::main
         -> config/env resolution (ultimate_scraper_config + SCRAPER_* env)
         -> driver/auth init
             -> webscraper/browser/edge_driver.py::create_edge_driver (aliased in legacy)
             -> webscraper/auth/orchestrator.py::authenticate (optional orchestrator)
                -> strategies/profile|programmatic|manual
                -> auth/healthcheck.py::is_authenticated
         -> selenium_scrape_tickets(...)
             -> per-handle process_handle(...)
                 -> parse ticket links (internal helper)
                 -> write tickets_<HANDLE>.json / tickets_all.json
                 -> db.upsert_handle + db.upsert_tickets
                 -> optional scrape_ticket_details(...)
                    -> per-ticket JSON/HTML/PNG + db artifacts

Discovery branch
  webscraper/run_discovery.py::main
    -> webscraper/tickets_discovery.py::run_discovery
       -> Chrome webdriver
       -> BFS crawl + table parsing
       -> webscraper/ticket_store.py::store_rows (tickets.db)

API/UI
  webscraper/ticket_api/app.py
    -> ticket_api/db.py query layer (tickets.sqlite)
    -> subprocess scripts/scrape_all_handles.py (job execution)
  webscraper/ticket-ui/*
    -> lib/api.ts fetches /api/*
    -> Next rewrite proxy (next.config.js) or NEXT_PUBLIC_API_BASE direct base
```

---

## 2) Run paths (exact call sequence + config/env reads)

## 2.1 “Discovery” run

Command:
- `python -m webscraper.run_discovery`

Call sequence:
1. `webscraper/run_discovery.py::main()`
2. Hardcoded URL list + `allowed_hosts` + output root (`webscraper/ticket-discovery-output`).
3. Optional cookie file detection at CWD `cookies.json`.
4. `webscraper/tickets_discovery.py::run_discovery(...)`.
5. Initializes Chrome options and driver; optionally imports `CHROME_BINARY_PATH` / `CHROMEDRIVER_PATH` from `ultimate_scraper_config.py`.
6. For each host/start URL:
   - inject cookies,
   - navigate,
   - `login_heuristics.ensure_authenticated(...)`,
   - BFS link crawl,
   - parse tables/links summary,
   - store normalized rows via `ticket_store.open_db(...)/store_rows(...)`.

Config/env read points:
- `ultimate_scraper_config.CHROME_BINARY_PATH`, `CHROMEDRIVER_PATH`.
- local filesystem cookie file only (`cookies.json`, if present).

## 2.2 “Single ticket scrape”

Typical trigger:
- `python -m webscraper.ultimate_scraper --scrape-ticket-details --max-tickets 1 ...`
- Operationally this still enters handle path first, then detail path.

Call sequence:
1. `ultimate_scraper.py` -> `cli/main.py::main` -> `ultimate_scraper_legacy.main()`.
2. `main()` resolves args/env/config and invokes `selenium_scrape_tickets(...)`.
3. Inside `selenium_scrape_tickets`, per handle `process_handle(handle)` extracts ticket URLs.
4. If `scrape_ticket_details_enabled`, call `scrape_ticket_details(...)` with discovered URLs.
5. In `scrape_ticket_details(...)`:
   - classify URL,
   - navigate to detail page,
   - run auth redirect retry/warm-up,
   - parse detail fields (`extract_ticket_fields`),
   - write `tickets/<handle>/<ticket_id>/ticket.json` (+ optional HTML/screenshot),
   - rate-limit sleep.

Config/env read points:
- CLI flags + env (`SCRAPER_URL`, `SCRAPER_OUT`, `SCRAPER_HANDLES`, `SCRAPER_HEADLESS`, auth env vars).
- optional `tickets_json` file path can seed ticket URLs when `ticket_urls` arg empty.

## 2.3 “Handle scrape”

Command shape:
- `python -m webscraper.ultimate_scraper --handles KPM WS7 --db webscraper/output/tickets.sqlite ...`

Call sequence:
1. `ultimate_scraper_legacy.main()` resolves handles (priority: `--handles-file` > `SCRAPER_HANDLES` > `--handles`).
2. Initializes run metadata + optional DB run (`db.init_db`, `db.start_run`).
3. Driver/auth setup and auth orchestration.
4. Handle loop in `selenium_scrape_tickets` (`for handle in handles`):
   - `process_handle(handle)` -> search/expand/parse links.
   - writes `tickets_<handle>.json`.
   - DB upserts: `db.upsert_handle(...)`, `db.upsert_tickets(...)`.
   - optional detail scrape per handle.
5. Finalize: write `tickets_all.json`, optional KB build, `db.finish_run(...)`.

Config/env read points:
- CLI + env around auth/profile/cookies/attach and runtime URLs.
- config defaults from `ultimate_scraper_config.py`.

## 2.4 “Bulk scrape / legacy ultimate_scraper”

Command shape:
- `python -m webscraper.ultimate_scraper --handles-file customer_handles.txt --scrape-ticket-details ...`

Call sequence:
- Same as 2.3, but large handle list from file and legacy-heavy process path.
- “Bulk” remains same engine (`ultimate_scraper_legacy.selenium_scrape_tickets`) with optional `--build-kb`, `--resume`, and DB persistence.

Config/env read points:
- `ultimate_scraper_config.py` defaults.
- env overrides for auth and mode selection (`SCRAPER_AUTH_*`, `SCRAPER_*`).

---

## 3) Storage / DB review

## 3.1 Current backends

1. **Primary ticket history DB**: SQLite in `webscraper/db.py` (default `webscraper/output/tickets.sqlite`).
2. **Discovery DB**: separate SQLite in `webscraper/ticket_store.py` (typically `webscraper/ticket-discovery-output/tickets.db`).
3. **File outputs**: many JSON/HTML/PNG artifacts under configured output directory.

## 3.2 Schema/model locations

- `webscraper/db.py::init_db()` defines:
  - `handles`, `runs`, `tickets`, `ticket_artifacts`.
- `webscraper/ticket_api/db.py::ensure_indexes()` adds query/job indexes and `scrape_jobs` table.
- `webscraper/ticket_api/models.py` defines API models (Pydantic).
- `webscraper/ticket_store.py` defines legacy discovery `tickets` schema (different shape).

## 3.3 Where fields are stored

- **handle**:
  - `db.py` -> `handles.handle`, `tickets.handle`, `ticket_artifacts.handle`.
- **ticketId**:
  - `db.py` -> `tickets.ticket_id` (PK with handle).
  - discovery DB uses `ticket_store.py` -> `tickets.ticket_id`.
- **timestamps**:
  - `db.py` -> `runs.started_utc/finished_utc`, `tickets.opened_utc/created_utc/updated_utc`, `ticket_artifacts.created_utc`, `handles.last_scrape_utc`.
- **attachments/artifacts**:
  - Structured detail parser returns `associated_files` in JSON payload.
  - Binary/page artifacts tracked by `db.record_artifact(...)` into `ticket_artifacts`.
  - ticket JSON includes file paths (`html_path`, `screenshot_path`) when enabled.

## 3.4 Existing indexes vs gaps

Existing (good):
- `tickets(handle)`, `tickets(status)`, `tickets(updated_utc)` in `db.py`.
- API adds `tickets(handle, updated_utc DESC)`, `tickets(handle, created_utc DESC)`, `tickets(ticket_id)`, status/date indexes, plus optional FTS5 table in `ticket_api/db.py`.

Gaps / recommended additions:
- Add composite for common filter combo: `(handle, status, updated_utc DESC)`.
- Add composite for ticket detail fallback query: `(ticket_id, updated_utc DESC)` (if frequent cross-handle lookup).
- Ensure FTS stays in sync (currently `rebuild` call exists, but no explicit triggers in this module).
- Discovery DB (`ticket_store.py`) lacks indexes entirely; add at minimum:
  - `tickets(host)`, `tickets(ticket_id)`, `tickets(status)`, `tickets(opened)`.

## 3.5 How ticket-ui reads data + “Failed to fetch” causes

Read path:
1. UI uses `ticket-ui/lib/api.ts::apiRequest`.
2. Requests go to:
   - `${NEXT_PUBLIC_API_BASE}/api/*` if base set, else relative `/api/*`.
3. Relative `/api/*` relies on Next rewrite in `ticket-ui/next.config.js` to `TICKET_API_PROXY_TARGET` (default `http://127.0.0.1:8787`).
4. Backend API handlers in `ticket_api/app.py` query sqlite via `ticket_api/db.py`.

“Failed to fetch” can happen when:
- API not running at expected host/port.
- Next rewrite target mismatch (`TICKET_API_PROXY_TARGET` wrong/unset in env-specific run mode).
- `NEXT_PUBLIC_API_BASE` points to unreachable endpoint.
- Browser cannot reach API due to local firewall/proxy.
- API subprocess scrape job fails and UI surfaces generic fetch error from thrown exception.

---

## 4) Reliability + security review

## 4.1 Likely failure points

- **Cookie expiry / invalid session**: stale cookie files used by manual/discovery mode.
- **Login heuristic drift**: `login_heuristics.py` and `auth/healthcheck.py` rely on heuristic selectors/text.
- **Driver startup fragility**: attach/launch/profile locking complexity in `create_edge_driver`.
- **Timeout sensitivity**: page load waits + retries can fail under latency.
- **Auth redirect loops**: keycloak/login redirects handled but still prone to repeated failure.
- **DOM/selector changes**: search input, dropdown item, table shape assumptions in legacy parser path.
- **Rate limiting / anti-bot**: no explicit adaptive backoff for server-side throttling patterns.

## 4.2 Secret/data leakage points

Potentially sensitive write points:
- Cookie dumps:
  - `save_cookies_json(...)` legacy,
  - manual auth writes `manual_cookies.json`, optional `manual_storage.json`.
- Auth diagnostics:
  - `auth_failure_diagnostics.json`, `auth_failure_page.html`, screenshots.
- Discovery writes per-host `cookies.json` in output tree.
- Legacy config module (`webscraper_config.py`) is high-risk and should remain redacted/template-safe.

Hardening status:
- Repo guidance warns against committing cookies/credentials.
- But runtime still logs many operational details; ensure logs never print full cookie values or credentials.

Required controls:
- Keep all generated auth/cookie artifacts under ignored output paths.
- Add explicit redaction utility for any debug logging touching headers/cookies.
- Add startup warning when cookie path points to tracked location.

---

## 5) Tech debt + cleanup

Major debt:
- **Duplicate logic**:
  - `browser/edge_driver.py` vs `ultimate_scraper_legacy.create_edge_driver`.
  - parser/auth helpers duplicated/re-exported across wrapper modules.
- **Legacy domination**:
  - “new” modules (`/scrape`, `/core`, `/browser`) are mostly facades; real behavior lives in legacy monolith.
- **Mixed storage paradigms**:
  - discovery DB and main DB diverge in schema and indexing.
- **Inconsistent naming/layout**:
  - `ultimate_scraper.py` (thin wrapper) vs `ultimate_scraper_legacy.py` (real engine) is non-obvious.

Testing/type coverage gaps:
- Good unit tests exist for auth heuristics/retry/CLI parsing/db utilities.
- Missing higher-confidence integration contract tests for:
  - scraper -> sqlite -> API -> UI query flow,
  - auth strategy fallback matrix,
  - UI/API error surface consistency.
- Typing still partial (many `Any`, large untyped internal closures in legacy runtime).

Consolidation target:
- one `ScraperPipeline` interface with explicit stages (auth, search, parse, detail, persist).
- move “real” implementations from legacy into dedicated modules, then leave legacy as compatibility shim only.

---

## 6) Performance review

Current slow spots:
- browser/session heavy startup logic and potential restarts.
- full page/screenshot artifacts per ticket handle/detail (I/O bound).
- no strict delta fetch by last `updated_utc` at source; scrape is often broad.
- repeated DOM parse and multiple waits per handle.

Measurable improvements:
- **Session reuse**: single long-lived authenticated session for batch runs (already partly done; formalize and enforce).
- **Concurrency controls**: introduce bounded worker pool for ticket detail pages (e.g., 2-4 tabs/tasks max) with shared auth session.
- **Incremental scraping**:
  - use last seen `updated_utc` per handle from DB,
  - stop scraping older ticket pages once threshold crossed.
- **Artifact policy**:
  - default `save_html=False`, `save_screenshot=False` for steady-state runs,
  - enable only on failures or sampled captures.
- **Request-level retry/backoff**:
  - classify transient failures and apply jittered backoff.

---

## 7) Prioritized action plan

## P0 (must-fix, S/M effort)

1. **Stabilize auth + redirect recovery telemetry** (M)
   - Files:
     - `webscraper/ultimate_scraper_legacy.py`
     - `webscraper/auth/healthcheck.py`
     - `webscraper/auth/orchestrator.py`
   - Changes:
     - introduce structured error codes for auth failures (`AUTH_LOGIN_URL`, `AUTH_COOKIE_STALE`, etc.).
     - persist per-handle auth failure summaries to sqlite `runs` adjunct JSON.
     - unify retry decision logic for auth redirects.

2. **UI/API error surfacing upgrade** (S)
   - Files:
     - `webscraper/ticket_api/app.py`
     - `webscraper/ticket-ui/lib/api.ts`
     - `webscraper/ticket-ui/app/page.tsx`
   - Changes:
     - return richer error payloads from API scrape/job endpoints.
     - display actionable UI diagnostics (API unreachable vs scraper failed vs timeout).
     - include request correlation id in logs and response.

3. **Sensitive artifact safety guardrails** (S)
   - Files:
     - `webscraper/auth/strategies/manual.py`
     - `webscraper/tickets_discovery.py`
     - `webscraper/ultimate_scraper_legacy.py`
   - Changes:
     - enforce output path under ignored dirs for cookie/auth diagnostics.
     - redact sensitive tokens from any log lines.
     - emit startup warning if cookie file is in tracked path.

## P1 (high value, M effort)

1. **Unify driver creation path** (M)
   - Files:
     - `webscraper/browser/edge_driver.py`
     - `webscraper/ultimate_scraper_legacy.py`
     - `webscraper/auth/driver_factory.py`
   - Changes:
     - make `browser/edge_driver.py` authoritative.
     - replace in-legacy duplicate implementation with imported module calls only.

2. **Index + query optimization pass** (S/M)
   - Files:
     - `webscraper/db.py`
     - `webscraper/ticket_api/db.py`
     - `webscraper/ticket_store.py`
   - Changes:
     - add composite indexes (`handle,status,updated_utc`; `ticket_id,updated_utc`).
     - add indexes for discovery DB.
     - verify query plans for main list/filter endpoints.

3. **Incremental scrape mode** (M)
   - Files:
     - `webscraper/ultimate_scraper_legacy.py`
     - `webscraper/db.py`
     - possibly `webscraper/scrape/*` wrappers
   - Changes:
     - read last successful `updated_utc` per handle.
     - stop scraping when older-than-watermark detected.

## P2 (cleanup / modernization, M/L)

1. Extract monolith into staged pipeline modules.
2. Add integration tests covering scraper->db->api contract.
3. Deprecate obsolete legacy sub-scripts with explicit migration docs.

---

## C) Definition of done checklist

- [ ] Single documented runtime path for scrape execution (legacy shim optional but non-authoritative).
- [ ] Driver/auth path has deterministic retry states and machine-readable error codes.
- [ ] UI shows clear actionable status for API unreachable, scrape failure, and timeout.
- [ ] Cookie/auth artifacts always written under ignored directories; redaction verified in logs.
- [ ] DB indexes cover key queries (`handle`, `ticketId`, `updatedAt/createdAt`, `status`, text search).
- [ ] Incremental scrape mode implemented and benchmarked vs baseline.
- [ ] End-to-end integration test validates one handle scrape updates API-visible ticket data.
- [ ] Operational runbook updated (`webscraper/README.md` + API/UI docs).

---

## Proposed PR breakdown

## PR1 — Stability

Title: **webscraper: harden auth/session recovery and error telemetry**

File list:
- `webscraper/ultimate_scraper_legacy.py`
- `webscraper/auth/healthcheck.py`
- `webscraper/auth/orchestrator.py`
- `webscraper/ticket_api/app.py`

Implementation steps:
1. Add normalized error taxonomy and attach to scrape job status payload.
2. Improve auth redirect retry state machine and timeout handling.
3. Persist failure context (reason code + URL class + retry count).
4. Expose clear API error payloads consumed by UI.

## PR2 — Performance

Title: **webscraper: optimize sqlite queries and incremental ticket scraping**

File list:
- `webscraper/db.py`
- `webscraper/ticket_api/db.py`
- `webscraper/ticket_store.py`
- `webscraper/ultimate_scraper_legacy.py`

Implementation steps:
1. Add missing composite indexes and verify plans.
2. Implement per-handle watermark (`updated_utc`) and delta stopping logic.
3. Make artifact capture conditional on failure/debug flags.
4. Add lightweight benchmark script/test for before/after elapsed time.

## PR3 — UI/API integration

Title: **webscraper ticket stack: resilient fetch UX and clearer job diagnostics**

File list:
- `webscraper/ticket-ui/lib/api.ts`
- `webscraper/ticket-ui/app/page.tsx`
- `webscraper/ticket-ui/README.md`
- `webscraper/ticket_api/app.py`
- `webscraper/dev_server.py`

Implementation steps:
1. Normalize fetch error classes (network/proxy/HTTP/timeout).
2. Render actionable “Failed to fetch” guidance in UI.
3. Expose `/health` status and configuration hints in UI header.
4. Document proxy/base env combinations and troubleshooting matrix.

