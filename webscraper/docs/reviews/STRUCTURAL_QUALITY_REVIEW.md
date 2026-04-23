# Webscraper Structural + Quality Review (current state)

## 1) Module inventory grouped by role

### 1.1 CLI entrypoints / scripts
- `webscraper/ultimate_scraper.py` — monolithic primary CLI + orchestration + scraping + parsing + persistence.
- `webscraper/run_discovery.py` — discovery crawl launcher with hardcoded targets/hosts/output path.
- `webscraper/chrome_cookies_live.py` — CLI for Chrome DevTools Protocol cookie export.
- `webscraper/extract_chrome_cookies.py` — local browser cookie extraction helper CLI.
- `webscraper/dev_server.py` — health-only development HTTP server with FastAPI/Flask/fallback modes.
- `webscraper/smoke_test.py` and `webscraper/_smoke_test.py` — environment smoke scripts.
- Ad-hoc diagnostic scripts: `webscraper/_cookie_test.py`, `webscraper/_cookie_test_pause.py`, `webscraper/_cookie_dump_pause.py`, `webscraper/_cdp_cookie_test.py`, `webscraper/_storage_test.py`, `webscraper/_selenium_smoke.py`.

### 1.2 Browser/driver support
- `webscraper/browser/edge_driver.py` — Edge startup/attach/kill/debugger probing, profile handling, process checks.
- `webscraper/auth/driver_factory.py` — auth wrapper around Edge driver creation (delegates to `ultimate_scraper.create_edge_driver`).

### 1.3 Scrape runners
- `webscraper/tickets_discovery.py` — Selenium crawl loop, cookie injection, artifact capture, link traversal, table extraction, sqlite writes.
- `webscraper/scrape/selenium_runner.py` — compatibility re-export of Selenium scraping functions from `ultimate_scraper.py`.
- `webscraper/http_scraper.py` — requests-based fetch + HTML parsing pipeline for customer/ticket/circuit data.

### 1.4 Parsing logic
- `webscraper/parsers/ticket_detail.py` — ticket detail parser helpers (labels/contacts/files extraction).
- `webscraper/site_selectors.py` — host-aware keyword/synonym selector maps.
- `webscraper/login_heuristics.py` — minimal authenticated-state heuristic for Selenium pages.

### 1.5 Storage / KB logic
- `webscraper/ticket_store.py` — sqlite helpers used by discovery crawler.
- `webscraper/kb/indexer.py` — ticket folder to JSONL/sqlite KB index builder.

### 1.6 Utilities + config
- `webscraper/scrape_utils.py` — misc helper functions (paths, json/text persistence, config loading).
- `webscraper/ultimate_scraper_config.py` — Selenium defaults/selectors/paths.
- `webscraper/webscraper_config.py` — legacy non-Selenium config dict.
- package init modules: `webscraper/__init__.py`, `webscraper/auth/__init__.py`, `webscraper/parsers/__init__.py`, `webscraper/scrape/__init__.py`, `webscraper/utils/__init__.py`, `webscraper/browser/__init__.py`, `webscraper/kb/__init__.py`.

### 1.7 Legacy stubs
- `webscraper/legacy/*.py` files are shim wrappers intended to forward to moved legacy scripts, with some marked `TODO/VERIFY` for missing implementations.

---

## 2) Per-module responsibility, boundary quality, coupling

### 2.1 Core monolith and near-core
1. `ultimate_scraper.py`
   - Responsibility: end-to-end scraping CLI and runtime pipeline.
   - Boundary quality: poor (multiple unrelated responsibilities in one file, ~3250 lines).
   - Coupling: high; imports driver, parser, KB indexer, auth, and still retains overlapping implementations.

2. `browser/edge_driver.py`
   - Responsibility: Edge process/driver lifecycle and attach fallback logic.
   - Boundary quality: mixed; domain is coherent, but file is too large (~900 lines) and internally duplicated.
   - Coupling: moderate; Selenium- and Windows-specific behavior tightly intertwined.

3. `auth/*`
   - `types.py`: clear SRP and low coupling (data models only).
   - `healthcheck.py`: clear SRP for post-login checks, moderate Selenium coupling.
   - `orchestrator.py`: mostly clear orchestration boundary but contains path resolution + default cookie policy that could be separated.
   - `strategies/profile.py`, `strategies/programmatic.py`, `strategies/manual.py`: strategy intent is good; manual strategy mixes prompting, file parsing, cookie sanitation, and auth attempt execution.
   - `driver_factory.py`: poor boundary because it imports runtime driver factory from monolith, creating reverse dependency to `ultimate_scraper.py`.

### 2.2 Runner and parser modules
4. `tickets_discovery.py`
   - Responsibility: crawl and extract ticket-like data.
   - Boundary quality: poor-to-mixed; mixes webdriver setup, crawl queue, cookie persistence, DOM summarization, file outputs, table classification, DB persistence in one function.
   - Coupling: high; directly couples to config, selector maps, auth heuristics, and sqlite helpers.

5. `http_scraper.py`
   - Responsibility: requests-based fetch and parser utilities.
   - Boundary quality: mixed; fetch/session/cookie loading + parsing + auth detection all in one module.
   - Coupling: moderate; depends on requests/bs4 and internal cookie file format assumptions.

6. `parsers/ticket_detail.py`
   - Responsibility: extraction from ticket detail HTML/text.
   - Boundary quality: good; focused parsing helpers.
   - Coupling: low/moderate (bs4 only).

7. `site_selectors.py`
   - Responsibility: selector synonym/keyword maps.
   - Boundary quality: good.
   - Coupling: low.

8. `login_heuristics.py`
   - Responsibility: simple auth check helper.
   - Boundary quality: good but too minimal for reusable policy.
   - Coupling: low/moderate (Selenium only).

### 2.3 Storage/util/config/support
9. `ticket_store.py`
   - Responsibility: sqlite storage for discovery rows.
   - Boundary quality: acceptable but narrow and schema-coupled.
   - Coupling: low/moderate.

10. `kb/indexer.py`
   - Responsibility: convert ticket artifacts to KB JSONL/sqlite index.
   - Boundary quality: mostly good; does file traversal + transform + persistence, still manageable.
   - Coupling: moderate due to hardcoded artifact layout assumptions (`tickets/<handle>/<ticket_id>/ticket.json`).

11. `scrape_utils.py`
   - Responsibility: generic utility helpers.
   - Boundary quality: weak cohesion (string/path/log/config/json helpers bundled together).
   - Coupling: low.

12. `ultimate_scraper_config.py` and `webscraper_config.py`
   - Responsibility: runtime defaults/selectors and legacy config.
   - Boundary quality: mixed; explicit constants are fine, but hardcoded URLs and output paths should be environment/profile driven.
   - Coupling: high to specific deployment targets and filesystem layout.

13. `run_discovery.py`, `dev_server.py`, `smoke_test.py`, underscore test scripts
   - Responsibility: operational helpers/diagnostics.
   - Boundary quality: mixed; several scripts encode environment assumptions and hardcoded outputs.
   - Coupling: low-to-moderate (mostly direct imports).

14. `legacy/*.py`
   - Responsibility: migration compatibility wrappers.
   - Boundary quality: poor in current state, because many wrappers compute a forwarding path that re-points to nested `webscraper/legacy/...` and may recurse/misroute.
   - Coupling: low but fragile.

---

## 3) Structural issues detected

1. Duplicate logic that should be centralized
- `EdgeStartupError` exists in both `ultimate_scraper.py` and `browser/edge_driver.py`.
- Edge helper logic is duplicated: `_validate_path`, `edge_binary_path`, `create_edge_driver` style behavior appears in both files.
- Ticket parsing helper names in `ultimate_scraper.py` overlap `parsers/ticket_detail.py` extraction responsibilities.
- Cookie handling paths/logic repeated across `tickets_discovery.py`, `http_scraper.py`, auth/manual strategy, and cookie utility CLIs.

2. Unused/low-value modules or imports (likely)
- `scrape/selenium_runner.py` appears to be only a pass-through export module.
- Several underscore-prefixed `*_test*.py` files are diagnostics rather than automated tests and may be stale.
- `dev_server.py` may be isolated from scraper runtime and not integrated with tests.

3. Modules with unrelated responsibilities
- `ultimate_scraper.py`: CLI, auth, driver lifecycle, traversal, parser logic, storage, logging, metadata writing.
- `tickets_discovery.py`: browser setup + crawler + parser + persistence + artifact writer.
- `auth/strategies/manual.py`: user IO prompting + file parser + cookie sanitizer + webdriver flow.
- `http_scraper.py`: cookie/session handling + request transport + parsing + auth detection.

4. Circular dependencies
- `ultimate_scraper.py` imports `webscraper.auth` while `auth/driver_factory.py` imports `create_edge_driver` from `ultimate_scraper.py`, producing a cycle (`ultimate_scraper -> auth -> auth.driver_factory -> ultimate_scraper`).

5. Repeated type/class definitions
- `EdgeStartupError` duplicated in at least two modules (`ultimate_scraper.py`, `browser/edge_driver.py`).

---

## 4) Maintenance blockers / risk points

1. Files still too large
- `ultimate_scraper.py` (~3250 lines) and `browser/edge_driver.py` (~904 lines) are too large for safe incremental editing and high-confidence review.

2. Limited testability
- No clear unit-test package around parser/auth/storage behaviors; only smoke/diagnostic scripts under `webscraper/`.
- Parsing and selector behavior has TODO/VERIFY notes without accompanying fixture-based tests.

3. Mixed concerns
- CLI argument handling, business logic, parser transforms, and persistence are intertwined in key modules.

4. Hardcoded selectors/URLs
- `run_discovery.py` hardcodes start URLs and allowed hosts.
- `ultimate_scraper_config.py` hardcodes defaults for URL/output/cookie path and extensive selector lists.

5. Output directories encoded in code
- Multiple modules write to `webscraper/output` or other fixed directories rather than receiving output policy from one configuration layer.

6. Legacy compatibility fragility
- `legacy/*.py` wrappers may not reliably forward due to path construction patterns and missing target implementations (`TODO/VERIFY` in some stubs).

7. Encoding and tooling friction
- Several underscore scripts carry BOM/non-printable characters, making AST/static analysis tooling brittle.

---

## 5) Recommended clean architecture (refill plan)

### 5.1 Target structure under `webscraper/`
- `webscraper/cli/`
  - `main_scrape.py`
  - `main_discovery.py`
  - `main_cookie_tools.py`
  - `main_smoke.py`
- `webscraper/core/`
  - `models.py`
  - `settings.py`
  - `run_context.py`
- `webscraper/browser/`
  - `edge_driver.py` (canonical only)
  - `session_attach.py` (debugger probing/target switching)
- `webscraper/auth/`
  - `types.py`
  - `orchestrator.py`
  - `healthcheck.py`
  - `cookie_loader.py` (json/netscape/manual parsing + sanitize)
  - `strategies/{profile.py,programmatic.py,manual.py}`
- `webscraper/scrape/`
  - `selenium_runner.py` (real runner)
  - `discovery_runner.py`
  - `http_runner.py`
  - `link_graph.py`
  - `artifact_writer.py`
- `webscraper/parsers/`
  - `ticket_detail.py`
  - `tables.py`
  - `customer_page.py`
- `webscraper/storage/`
  - `ticket_store.py`
  - `kb_indexer.py`
  - `schemas.py`
- `webscraper/config/`
  - `selectors.py`
  - `defaults.py`
- `webscraper/legacy/`
  - `README.md`
  - minimal deterministic shims only (or remove with migration notes)
- `webscraper/tests/`
  - `test_ticket_detail_parser.py`
  - `test_cookie_loader.py`
  - `test_auth_healthcheck.py`
  - `test_kb_indexer.py`
  - `test_discovery_table_classifier.py`

### 5.2 Function movement guidance
- Move all driver creation/attach logic out of `ultimate_scraper.py` into canonical `browser/edge_driver.py` only.
- Keep `ultimate_scraper.py` as a thin CLI delegator (or deprecate entirely in favor of `cli/main_scrape.py`).
- Extract cookie parsing/sanitization/load from auth/manual and crawler modules into `auth/cookie_loader.py`.
- Extract DOM summarize/table classify/table map logic from `tickets_discovery.py` into parser modules.
- Move output writing helpers to `scrape/artifact_writer.py` and consume a shared runtime config object.
- Merge/rename storage modules under `storage/` and keep schema definitions centralized.

### 5.3 Modules to deprecate/delete
- Deprecate `webscraper/webscraper_config.py` once legacy callers are migrated.
- Replace `webscraper/scrape/selenium_runner.py` pass-through with real implementation (or remove if unused).
- Remove or relocate underscore ad-hoc test scripts after equivalent pytest coverage exists.
- Replace fragile legacy wrappers with either verified launchers or explicit deprecation errors.

### 5.4 Modules requiring tests first
- `parsers/ticket_detail.py` (fixtures for label/contacts/files extraction).
- new `auth/cookie_loader.py` (json/netscape/malformed input cases).
- `auth/healthcheck.py` (HTML fixture/mocked driver signals).
- `storage/kb_indexer.py` and `storage/ticket_store.py` (sqlite temp-dir tests).
- `scrape/discovery_runner.py` table classification + link filtering units.

---

## 6) Recommended modules (post-refactor): one-line purpose + caller imports

1. `webscraper.core.settings`
- Purpose: normalize env/CLI/file config into a typed runtime settings object.
- Caller imports:
  - `from webscraper.core.settings import ScraperSettings, load_settings`

2. `webscraper.browser.edge_driver`
- Purpose: single source of truth for Edge driver startup/attach/fallback behavior.
- Caller imports:
  - `from webscraper.browser.edge_driver import create_edge_driver, EdgeStartupError, kill_edge_processes`

3. `webscraper.auth.cookie_loader`
- Purpose: parse/sanitize/load cookie inputs from json, Netscape, or prompt dumps.
- Caller imports:
  - `from webscraper.auth.cookie_loader import load_cookies_from_file, sanitize_cookie, parse_netscape_cookie_line`

4. `webscraper.auth.orchestrator`
- Purpose: sequence auth strategies and return typed auth result with diagnostics.
- Caller imports:
  - `from webscraper.auth.orchestrator import authenticate`
  - `from webscraper.auth.types import AuthContext, AuthMode, AuthResult`

5. `webscraper.scrape.selenium_runner`
- Purpose: orchestrate Selenium scraping run using injected browser/auth/parser/storage services.
- Caller imports:
  - `from webscraper.scrape.selenium_runner import run_selenium_scrape`

6. `webscraper.scrape.discovery_runner`
- Purpose: bounded link discovery crawl with explicit inputs (urls, hosts, depth/pages, auth state).
- Caller imports:
  - `from webscraper.scrape.discovery_runner import run_discovery`

7. `webscraper.parsers.ticket_detail`
- Purpose: convert ticket detail HTML into normalized structured fields.
- Caller imports:
  - `from webscraper.parsers.ticket_detail import extract_ticket_fields`

8. `webscraper.parsers.tables`
- Purpose: classify and map HTML tables to typed ticket/customer records.
- Caller imports:
  - `from webscraper.parsers.tables import is_ticket_table, map_table_rows`

9. `webscraper.storage.ticket_store`
- Purpose: write/read normalized ticket rows and crawl summaries from sqlite.
- Caller imports:
  - `from webscraper.storage.ticket_store import open_db, store_rows`

10. `webscraper.storage.kb_indexer`
- Purpose: build/update KB JSONL/sqlite from scraped artifact folders.
- Caller imports:
  - `from webscraper.storage.kb_indexer import build_kb_index`

11. `webscraper.cli.main_scrape`
- Purpose: CLI entrypoint that parses args and calls `run_selenium_scrape`.
- Caller imports:
  - `from webscraper.cli.main_scrape import main`

12. `webscraper.cli.main_discovery`
- Purpose: CLI entrypoint for discovery crawl with configurable targets and output policy.
- Caller imports:
  - `from webscraper.cli.main_discovery import main`

13. `webscraper.cli.main_cookie_tools`
- Purpose: unified cookie tooling commands (extract/live/convert) behind one CLI surface.
- Caller imports:
  - `from webscraper.cli.main_cookie_tools import main`


---

## Refactor update (current pass)

- `webscraper/ultimate_scraper.py` is now a thin CLI wrapper that only dispatches to `webscraper.cli.main`.
- `webscraper/cli/main.py` is now an executable module (`python -m webscraper.cli.main`) that delegates to legacy runtime behavior.
- Added `webscraper/errors.py` as the **single source of truth** for custom exceptions, including `EdgeStartupError`.
- `webscraper/browser/edge_driver.py` and `webscraper/ultimate_scraper_legacy.py` now import `EdgeStartupError` from `webscraper.errors` (no duplicate class definitions).
- Added typed models package `webscraper/models/` (`TicketUrlEntry`, `TicketDetails`) for shared data contracts.
- Added `webscraper/scrape/runner.py` with `run_scrape(config)` as orchestration entrypoint.
- Added core helpers with explicit typing:
  - `webscraper/core/config_loader.py` (`load_config`, `_load_config` compatibility alias)
  - `webscraper/core/paths.py` (`ensure_output_dir`, `runtime_edge_profile_dir`, metadata/text writers)
- Added basic retry primitive in `webscraper/scrape/retry_logic.py` (`run_with_retry`).
- Added tests under `webscraper/tests/` for config/paths, retry logic, and CLI `--help` smoke behavior.
- Updated `.gitignore` with explicit runtime output ignores for:
  - `webscraper/browser/output/`
  - `webscraper/**/edge_tmp_profile/`

