# Webscraper — Architecture Reference

## Overview

The webscraper is a Selenium + requests-based tool for scraping customer
ticket data from the 123NET portal. It exposes a FastAPI REST service
(`ticket_api`) that accepts scrape jobs, persists results to SQLite, and is
consumed by the Next.js `ticket-ui` front-end.

---

## Directory layout

```
webscraper/
├── src/webscraper/          # Python package (src layout)
│   ├── __init__.py
│   ├── __main__.py          # python -m webscraper entrypoint
│   ├── main.py              # thin CLI dispatcher
│   ├── errors.py            # single source of truth for custom exceptions
│   │
│   ├── auth/                # authentication strategies and cookie handling
│   │   ├── types.py         # AuthContext, AuthMode, AuthResult data models
│   │   ├── orchestrator.py  # sequences profile → programmatic → manual strategies
│   │   ├── healthcheck.py   # post-login verification heuristics
│   │   ├── strategies/      # concrete auth strategy implementations
│   │   │   ├── profile.py       # reuse existing browser profile
│   │   │   ├── programmatic.py  # fill username/password form
│   │   │   └── manual.py        # inject cookies from file or prompt
│   │   ├── driver_factory.py    # auth-aware Edge driver creation
│   │   ├── cookie_seeder.py     # seed live cookies into a Selenium session
│   │   └── ...
│   │
│   ├── browser/             # WebDriver lifecycle management
│   │   ├── edge_driver.py   # Edge startup, attach, kill, debugger probing
│   │   ├── launcher.py      # high-level driver launch helper
│   │   ├── selection.py     # resolve browser type from env vars
│   │   └── cookie_store.py  # browser-level cookie persistence helpers
│   │
│   ├── cli/                 # CLI argument parsing
│   │   ├── main.py          # primary CLI (python -m webscraper.cli.main)
│   │   └── attach_parsing.py # --attach / --attach-debugger argument helpers
│   │
│   ├── scrape/              # scraping runners and retry logic
│   │   ├── runner.py        # run_scrape() — main orchestration entrypoint
│   │   ├── selenium_runner.py  # Selenium-based scraping functions
│   │   ├── ticket_search.py    # handle search + ticket link enumeration
│   │   ├── ticket_details.py   # per-ticket detail page scraping
│   │   └── retry_logic.py      # run_with_retry() primitive
│   │
│   ├── parsers/             # HTML extraction helpers
│   │   └── ticket_detail.py # extract labels, contacts, attachments from HTML
│   │
│   ├── models/              # shared data contracts (dataclasses / TypedDicts)
│   │   └── tickets.py       # TicketUrlEntry, TicketDetails
│   │
│   ├── ticket_api/          # FastAPI REST service
│   │   ├── app.py           # FastAPI application, routes, startup logic
│   │   ├── db.py            # SQLite access layer (handles, tickets, auth_cookies)
│   │   ├── models.py        # Pydantic request/response models
│   │   ├── auth.py          # /api/auth/* endpoints
│   │   ├── auth_manager.py  # auth state manager used by API
│   │   ├── auth_store.py    # persistent auth-cookie store
│   │   └── cookie_store.py  # cookie persistence helpers
│   │
│   ├── core/                # low-level shared helpers
│   │   ├── config_loader.py # load WebscraperConfig from env
│   │   ├── paths.py         # output directory helpers
│   │   └── phase_logger.py  # structured phase/step logging
│   │
│   ├── utils/               # general-purpose utilities
│   │   ├── io.py            # safe_write_json, make_run_id, utc_now_iso
│   │   ├── io_utils.py      # compatibility re-export of utils/io.py
│   │   └── schema.py        # JSON schema helpers
│   │
│   ├── kb/                  # knowledge-base index builder
│   │   ├── indexer.py       # convert ticket artifacts to JSONL/sqlite KB
│   │   └── builder.py       # KB build orchestration
│   │
│   ├── vpbx/                # VPBX handle management
│   │   └── handles.py       # load/filter/list customer handles
│   │
│   ├── legacy/              # archived pre-refactor scripts (do not import)
│   │   ├── README.md
│   │   └── *.py             # original standalone scraping scripts
│   │
│   ├── lib/                 # thin internal library helpers
│   │   └── db_path.py       # TICKETS_DB_PATH resolution
│   │
│   ├── config.py            # WebscraperConfig dataclass + load_config()
│   ├── webscraper_config.py # legacy WEBSCRAPER_CONFIG dict (non-Selenium)
│   ├── ultimate_scraper_config.py  # selector defaults for ultimate_scraper
│   ├── ultimate_scraper.py  # thin CLI wrapper (delegates to cli/main.py)
│   ├── ultimate_scraper_legacy.py  # monolithic original scraper (3 700 LOC)
│   ├── http_scraper.py      # requests-based fetch + parse pipeline
│   ├── tickets_discovery.py # Selenium crawl loop + artifact capture
│   ├── run_manager.py       # run lifecycle helpers
│   ├── run_discovery.py     # discovery crawl launcher
│   ├── handles_loader.py    # CSV handle loading
│   ├── ticket_store.py      # SQLite helpers used by discovery crawler
│   ├── scrape_utils.py      # misc string/path/JSON helpers (pre-utils/ era)
│   ├── smoke_test.py        # importable smoke-test module
│   ├── dev_server.py        # combined API + UI dev server launcher
│   ├── logging_config.py    # logging setup
│   ├── login_heuristics.py  # auth-state detection for Selenium pages
│   ├── site_selectors.py    # host-aware CSS/keyword selector maps
│   ├── artifacts_contract.py # run-artifact layout constants
│   ├── paths.py             # legacy path helpers (prefer core/paths.py)
│   ├── chrome_cookies_live.py  # CLI: export cookies via Chrome DevTools Protocol
│   ├── extract_chrome_cookies.py # CLI: extract cookies from local browser store
│   └── auth_diagnostics.py  # standalone auth diagnostics script
│
├── scripts/                 # local dev / operational helper scripts
│   ├── auth_probe.py        # probe current auth session
│   ├── dev_ticket_stack.py  # start full API+UI dev stack
│   ├── doctor.py            # environment health checker
│   ├── seed_and_fetch.py    # seed cookies + run a quick scrape
│   └── debug/               # ad-hoc manual debug scripts (NOT in test suite)
│       ├── README.md
│       ├── _selenium_smoke.py    # smoke-test Edge WebDriver
│       ├── _cookie_test_pause.py # manual cookie inspection pause
│       └── _cookie_dump_pause.py # full cookie dump via CDP
│
├── tests/                   # pytest unit tests
│   ├── conftest.py          # sys.path setup for src layout
│   ├── fixtures/            # static HTML fixtures for parser tests
│   └── test_*.py            # one file per module under test
│
├── configs/                 # static configuration
│   ├── handles/
│   │   └── handles_master.txt   # canonical handle list
│   └── settings.example.yaml   # example runtime settings
│
├── docs/                    # documentation
│   ├── ARCHITECTURE.md      # this file
│   ├── artifacts_contract.md
│   ├── auth_api_changelog.md
│   └── reviews/             # AI-assisted code review artifacts
│       ├── E2E_REVIEW.md
│       ├── STRUCTURAL_QUALITY_REVIEW.md
│       ├── VERIFIED_E2E_REVIEW.md
│       ├── WEBSCRAPER_E2E_REMEDIATION_PLAN.md
│       ├── WEBSCRAPER_MODULE_ARCH_REVIEW.md
│       └── WEB_SCRAPER_REVIEW.md
│
├── ticket-ui/               # Next.js front-end for Ticket History
│   ├── app/                 # Next.js App Router pages
│   ├── lib/                 # shared TypeScript helpers
│   ├── package.json
│   └── README.md
│
├── chromedriver-win64/      # Windows ChromeDriver binary (vendored)
├── README.md                # quickstart guide
├── requirements.txt         # Python runtime deps (selenium, bs4, requests, …)
├── requirements_api.txt     # FastAPI / uvicorn deps
└── pyproject.toml           # package metadata + build config
```

---

## Key data flows

### Scrape pipeline

```
CLI (ultimate_scraper / cli/main.py)
  └─► auth/orchestrator.py        # pick & run auth strategy
        └─► browser/edge_driver.py  # start / attach Edge
              └─► scrape/runner.py  # scrape loop
                    ├─► scrape/ticket_search.py  # enumerate ticket links
                    ├─► scrape/ticket_details.py # fetch each ticket
                    └─► ticket_api/db.py          # persist to SQLite
```

### Ticket API (REST service)

```
POST /api/scrape/start  →  ticket_api/app.py
  └─► launches scrape subprocess (scripts/scrape_all_handles.py)
        └─► persists tickets to var/db/tickets.sqlite
              └─► ticket_api/db.py  (handles + tickets + auth_cookies tables)

GET /api/tickets?handle=X  →  ticket_api/db.py  →  JSON response
```

### Auth strategies (precedence order)

1. **Profile** — reuse an existing browser profile directory.  
   Controlled by `EDGE_PROFILE_DIR` / `EDGE_PROFILE_NAME`.
2. **Programmatic** — fill username/password form fields.  
   Controlled by `SCRAPER_USERNAME` / `SCRAPER_PASSWORD`.
3. **Manual / Cookie injection** — import a JSON or Netscape cookie file.  
   Controlled by `SCRAPER_COOKIE_FILES`.

---

## Known technical debt

| Area | Issue | Severity |
|------|-------|----------|
| `ultimate_scraper_legacy.py` | ~3 700-line monolith; all responsibilities mixed | HIGH |
| `ultimate_scraper_config.py` vs `webscraper_config.py` vs `config.py` | Three config systems; consolidation pending | MEDIUM |
| `ticket_api/app.py` | ~2 100 lines; routes + middleware + business logic | MEDIUM |
| `browser/edge_driver.py` | ~900 lines; process mgmt + debugger + profiles | MEDIUM |
| `scrape_utils.py` | Pre-`utils/` grab-bag; not imported by current code | LOW |
| `auth/driver_factory.py` | Imports from `ultimate_scraper_legacy.py` (circular dep) | MEDIUM |
| Hardcoded IPs/URLs | `DEFAULT_URL = "http://10.123.203.1"` in `ultimate_scraper_config.py` | LOW |

See `docs/reviews/` for detailed remediation plans.

---

## Runtime state (gitignored)

All runtime-generated files live under `var/` (gitignored):

| Path | Contents |
|------|----------|
| `var/profiles/` | Browser user-data directories |
| `var/cookies/` | Exported cookie files |
| `var/db/` | SQLite databases (`tickets.sqlite`) |
| `var/runs/` | Per-run scrape artifacts |
| `var/discovery/` | Discovery crawl artifacts |
| `var/logs/` | Runtime logs |
