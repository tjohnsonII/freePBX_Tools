# Webscraper Modular Review (browser/scrape/parsers/kb/auth)

## Scope and method
- Reviewed `webscraper/browser`, `webscraper/scrape`, `webscraper/parsers`, `webscraper/kb`, and supporting auth integration points.
- Performed static inspection plus lint/type checks:
  - `python -m ruff check webscraper/browser webscraper/scrape webscraper/parsers webscraper/kb webscraper/auth webscraper/ultimate_scraper.py`
  - `pyright webscraper/browser/edge_driver.py webscraper/ultimate_scraper.py webscraper/auth webscraper/parsers webscraper/kb`

---

## 1) Structural overview

### High-level architecture
- **Entry facade (current reality):** `webscraper/scrape/selenium_runner.py` re-exports `scrape_ticket_details` and `selenium_scrape_tickets` from `webscraper.ultimate_scraper` (thin compatibility layer, not a true orchestration module).
- **Browser layer:** `webscraper/browser/edge_driver.py` contains Edge startup, attach, and process control logic.
- **Parsing layer:** `webscraper/parsers/ticket_detail.py` contains HTML-to-ticket-field extraction helpers.
- **KB layer:** `webscraper/kb/indexer.py` transforms ticket artifacts into JSONL/SQLite KB records.
- **Auth layer:** `webscraper/auth/*` defines typed auth context/result models and strategy orchestration (`profile`, `programmatic`, `manual`).
- **Monolith remains:** `webscraper/ultimate_scraper.py` still contains large implementations of browser/parsing/KB logic and then aliases names back to modular implementations at file end.

### Module inventory and principal APIs
- `webscraper/browser/edge_driver.py`
  - `EdgeStartupError`
  - `edge_binary_path`, `probe_edge_debugger`, `edge_debug_targets`, `switch_to_target_tab`, `create_edge_driver`, `kill_edge_processes`
  - Public API explicitly listed via `__all__`.
- `webscraper/scrape/selenium_runner.py`
  - Re-export only: `scrape_ticket_details`, `selenium_scrape_tickets`.
- `webscraper/parsers/ticket_detail.py`
  - External: `extract_ticket_fields` (and potentially `normalize_label` by convention)
  - Internal helpers: `_value_for_keys`, `_extract_contacts`, `_extract_associated_files`.
- `webscraper/kb/indexer.py`
  - External: `build_kb_index`
  - Internal helpers: `_parse_year_month`, `_load_existing_kb_keys`, `_init_kb_sqlite`, `_upsert_kb_record`.
- `webscraper/auth/types.py`
  - `AuthMode`, `AuthContext`, `AuthAttempt`, `AuthResult`.
- `webscraper/auth/orchestrator.py`
  - External: `authenticate`
  - Internal: path/cookie resolution helpers.
- `webscraper/auth/strategies/*.py`
  - External strategy functions: `try_profile`, `try_programmatic`, `try_manual`.

### Relationship map (runtime dependency flow)
1. `ultimate_scraper` imports modular browser/kb/parser implementations.
2. `auth.driver_factory` imports `create_edge_driver` from `ultimate_scraper` (not directly from `browser.edge_driver`).
3. Auth strategies call `driver_factory.create_edge_driver_for_auth` and `healthcheck.is_authenticated`.
4. `selenium_runner` exports selected `ultimate_scraper` functions.

This means `ultimate_scraper` is still the central dependency hub, even after modular extraction.

---

## 2) Code smells, design issues, bug/merge-conflict risk

### Critical
1. **Hard duplicate implementations in `browser/edge_driver.py`**
   - `_validate_path`, `edge_binary_path`, and `create_edge_driver` are each declared twice.
   - This causes redeclaration diagnostics and very high merge-conflict risk in future edits.

2. **Partial modularization with shadowing in `ultimate_scraper.py`**
   - The file defines large local implementations (browser/parsing/KB) and later reassigns names to modular imports.
   - Confusing ownership of behavior; static tools flag redeclaration/reassignment issues.

3. **Extremely large monolithic file still active**
   - `ultimate_scraper.py` is still thousands of lines and remains the practical integration point.
   - Refactor was only partially completed, creating split-brain maintenance.

### Medium
4. **Tight coupling from auth back to monolith**
   - `auth/driver_factory.py` imports `create_edge_driver` from `ultimate_scraper` rather than `browser.edge_driver`, reintroducing circular conceptual dependency.

5. **Many broad `except Exception` blocks in critical runtime paths**
   - Can hide true failures, reduce observability, and make automated recovery logic non-deterministic.

6. **Mixed public API signaling conventions**
   - Some modules use `__all__`, some rely on underscore naming, some are empty package files. Public contract is not uniformly explicit.

---

## 3) Unused imports, duplicate logic, inconsistent patterns, duplicate exception/type declarations

### Duplicate declarations / duplicate logic
- `browser/edge_driver.py`: duplicate top-level defs for `_validate_path`, `edge_binary_path`, `create_edge_driver`.
- `ultimate_scraper.py`: local `EdgeStartupError` and local implementations are later overwritten by imported modular aliases.
- `ultimate_scraper.py` and modular files still share equivalent KB/parsing/browser logic, increasing drift risk.

### Unused imports / variables (from ruff)
- Unused imports in `ultimate_scraper.py`: `io`, `contextlib`, local `webdriver`, local `NoSuchElementException`.
- Unused local variable in `ultimate_scraper.py`: exception variable `e` assigned but unused.

### Undefined symbol / type issues
- `browser/edge_driver.py` uses `cast(...)` but does not import it.

### Inconsistent naming/patterns
- Two competing styles for exposing API:
  - explicit `__all__` (`browser`, `auth`, `scrape/selenium_runner`)
  - implicit “underscore means private” (`parsers`, `kb`) without `__all__`.
- Multiple places implement similar helper functions (`as_str`, label/value parsing, KB indexing patterns), indicating incomplete consolidation.

---

## 4) API boundaries (external vs helper)

### Clearly external today
- `webscraper.auth.authenticate` via `auth/__init__.py`.
- `webscraper.auth.strategies.try_profile|try_programmatic|try_manual` via strategies `__init__.py`.
- `webscraper.browser.edge_driver` public surface via `__all__`.
- `webscraper.scrape.selenium_runner` as facade for `scrape_ticket_details`, `selenium_scrape_tickets`.
- `webscraper.kb.indexer.build_kb_index` and `webscraper.parsers.ticket_detail.extract_ticket_fields` by naming/use.

### Helpers/internal by convention
- Leading underscore helpers in auth strategies, auth orchestrator, parser internals, and KB internals.
- In practice, internals are still imported ad hoc in monolith areas; hard boundary not yet enforced.

---

## 5) High-value refactor recommendations (no code rewrite here)

1. **Resolve duplicate defs in `browser/edge_driver.py` first**
   - Keep one canonical implementation for each public symbol.
   - Add focused regression tests around attach/fallback/temp-profile behavior before cleanup.

2. **Finish “extract and delegate” in `ultimate_scraper.py`**
   - Remove local shadow implementations for modules already extracted.
   - Keep only orchestration/CLI concerns in monolith.

3. **Repoint auth driver factory to browser module directly**
   - `auth/driver_factory.py` should import from `webscraper.browser.edge_driver`, not from `ultimate_scraper`.
   - Reduces accidental coupling and import side effects.

4. **Define explicit package APIs for parser/kb**
   - Add package-level exports (`__all__` in non-empty package modules) to make boundary intentional.

5. **Introduce one canonical “shared primitives” module**
   - Consolidate utility duplicates (`as_str`, text normalization/date helpers) to reduce drift.

6. **Narrow exception handling in auth/browser hot paths**
   - Keep context-rich logging; avoid silent generic catches where exact recovery behavior matters.

---

## 6) Missing tests, formatting issues, and type-hint concerns

### Missing tests (high-value)
- `browser.edge_driver`:
  - attach mode selection (`ATTACH_EXPLICIT`, `ATTACH_AUTO`, fallback)
  - stale lock cleanup behavior
  - temp profile retry behavior
- `auth.orchestrator`:
  - strategy ordering and reason aggregation
  - cookie/profile path resolution under relative/absolute paths
- `auth.strategies.manual`:
  - JSON cookie parsing and Netscape parsing edge cases
  - prompt gating (`SCRAPER_MANUAL_PROMPT`, `_MANUAL_PROMPTED` behavior)
- `parsers.ticket_detail`:
  - robust extraction across varied HTML table shapes
  - contact/file extraction false positives
- `kb.indexer`:
  - resume behavior/idempotency
  - malformed `ticket.json` handling and path fallback logic

### Formatting/lint
- Fails lint checks due to redeclaration and unused import/variable errors in `browser/edge_driver.py` and `ultimate_scraper.py`.

### Type hint issues (Pyright/Pylance-relevant)
- Redeclaration errors for duplicated functions in `browser/edge_driver.py`.
- Undefined `cast` in `browser/edge_driver.py`.
- Assignment type conflict where `ultimate_scraper.EdgeStartupError` is reassigned to `browser.edge_driver.EdgeStartupError` alias.
- Optional iterable complaint in `auth/strategies/manual.py` around cookie parsing branch.

---

## 7) Tidy summary

### Potential dead code
- Local implementations in `ultimate_scraper.py` for `EdgeStartupError`, `edge_binary_path`, `create_edge_driver`, `extract_ticket_fields`, and `build_kb_index` are effectively superseded by bottom-of-file alias assignments.
- Duplicate definitions in `browser/edge_driver.py` imply one copy is dead/shadowed at runtime.

### OS/platform-specific dependencies
- Strong **Windows specificity** in browser startup/process handling (`ProgramFiles*`, `wmic`, `taskkill`, `msedge.exe`, `msedgedriver.exe`).
- Selenium/browser runtime assumes Edge + Windows process semantics in key paths.

### AWS dependencies
- No direct AWS SDK/dependency surfaced in reviewed modules.

### Security risks
- Auth orchestration auto-discovers cookie files in common paths; manual strategy can write pasted cookie payloads to disk (`manual_cookies.json`).
- High risk of accidental sensitive artifact persistence if output hygiene is not enforced consistently.

### Maintenance hotspots
1. `webscraper/ultimate_scraper.py` (size + partial modular migration)
2. `webscraper/browser/edge_driver.py` (duplicated declarations + startup complexity)
3. `webscraper/auth/strategies/manual.py` (stateful prompt logic + credential/cookie handling)
