# AGENTS.md – freePBX_Tools workspace

This repo is a multi-tool workspace (Python + Shell + Node/TypeScript) for FreePBX operations, deployments, diagnostics, config generation, traceroute visualization, and scraping/knowledge-base automation.

**High risk:** parts of this repo interact with customer systems and can produce/contain sensitive data (cookies, credentials, customer exports). Follow the hard rules.

If anything is unclear, **do not guess**. Add a **TODO/VERIFY** note and point to the specific file that needs to be updated.

---

## Hard rules (non-negotiable)

### Secrets / sensitive data
- **Never** create, modify, or commit:
  - cookies, sessions, headers, auth tokens
  - usernames/passwords/credentials
  - internal-only docs/dumps/scrapes/exported customer data
  - databases or analysis outputs containing customer information
- Treat anything under these patterns as **off-limits** for commits:
  - `cookies*`, `*_cookies.*`, `*_credentials.*`, `*password*`, `.env*`
  - `123net_internal_docs/` (and any mirrored copies)
  - scrape/export outputs such as `scraped_tickets/`, `webscraper/output/`, `webscraper/ticket-discovery-output/`
  - `tickets.json`, `customers_raw.html`, `*.db`, bulk `*.csv`/`*.json` outputs
- **Do not open or scan ignored output folders** (anything ignored by `.gitignore`) unless explicitly asked.
- If a folder/file is ignored by `.gitignore`, treat it as private/local-only unless explicitly instructed otherwise.
- If a change would require adding sensitive output files, **stop** and propose an alternative.

### Repo safety workflow
- Prefer **small, scoped diffs**.
- Do not reformat unrelated files.
- Always state what you changed + what you tested.
- One task = one commit/PR when possible. Avoid drive-by refactors.
- Output files must go to ignored folders; if in doubt, add an ignore rule first.

### Secure push requirement
- **Always** use secure push workflow instead of raw `git push` when `git spush` is available.
- This repo ships `scripts/secure_push.py`; some environments configure `git spush` as a local alias in `.git/config` or a global Git config.
- **Important:** if `git spush` is configured, verify it does not hard-code a machine-specific Python path. Prefer `py -3` / `python` in docs.

### Line endings
- Default to **LF** for new files.
- Respect `.gitattributes` (enforces LF for certain patterns).

---

## Source of truth order (do not invent commands)
1. `README*` and `RUN_APPS.md`
2. `package.json` scripts
3. `pyproject.toml` / `requirements.txt`
4. VS Code tasks (if that’s how a tool is run)

If the repo doesn’t explicitly document a command, add **TODO/VERIFY**.

---

## Repo map (deep-dive)

### Core FreePBX tool suite (deployable)
- `freepbx-tools/`
  - Shell + Python diagnostics, analyzers, callflow utilities
  - Scripts under `freepbx-tools/bin/`
  - Installer scripts present: `bootstrap.sh`, `install.sh`, `uninstall.sh`, `make_executable.sh`
  - Config: `freepbx-tools/version_policy.json`, `freepbx-tools/requirements.txt`

### Deployment web app (FastAPI + Vite)
- `freepbx-deploy-backend/` (Python/FastAPI)
- `freepbx-deploy-ui/` (React/Vite)

### Config generator web app (React/Vite + Storybook)
- `PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/`
  - Includes Storybook config and at least one test file (`*.test.tsx`)
  - Includes a GitHub Actions workflow under `.github/workflows/`

### Traceroute visualizer (Next.js + Python backends included)
- `traceroute-visualizer-main/traceroute-visualizer-main/` (Next.js frontend)
- Python backend entrypoints exist under:
  - `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/traceroute_server.py`
  - `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/fastapi_traceroute_server.py`
  - `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/traceroute_server_py2.py`
- Additional backend dependency folder exists:
  - `traceroute-visualizer-main/backend/requirements.txt`

### Webscraper (Selenium) – HIGH SENSITIVITY
- `webscraper/`
  - Selenium scraping utilities and discovery runs
  - Has `webscraper/requirements.txt`, `webscraper/ultimate_scraper.py`, and `webscraper/ultimate_scraper_config.py`
  - Contains chromedriver artifacts (tracked). Treat as sensitive/large and avoid touching unless required.

### Knowledge base + scraping + analysis tools (repo root)
- Ticket/KB tooling: `ticket_scraper.py`, `build_unified_kb.py`, `unified_knowledge_base.py`, `kb_quickstart.py`, `query_ticket_kb.py`, etc.
- Analysis tooling: `phone_config_analyzer.py`, `deep_analyze_scraped_data.py`, `analyze_vpbx_phone_configs.py`, etc.
- Safety tooling: `verify_commit_safety.py`, `scripts/secure_push.py`

### Flask web UI (repo root)
- `web_manager.py`, `static/`, `templates/`, `web_requirements.txt`

### Network config templates / generators
- `mikrotik/` (templates + README + helper scripts)
- `cisco switches/` (templates + helper scripts)

### Misc utilities
- `CAGE_INFO/` (shell scripts for cage/host diagnostics)
- `scripts/` (smoke tests, selenium tests, remote diagnostics, secure push tooling)

---

## Subprojects: setup/run/test (Windows-friendly)

### 1) `freepbx-deploy-backend/` (FastAPI)
Install (PowerShell):
- `py -3 -m venv .venv`
- `\.venv\Scripts\python -m pip install -U pip`
- `\.venv\Scripts\python -m pip install -r requirements.txt`

Run:
- `\.venv\Scripts\python -m uvicorn freepbx_deploy_backend.main:app --reload --host 127.0.0.1 --port 8002`

Test:
- TODO/VERIFY (check README/pyproject for `pytest` or other test runner)

Config:
- `requirements.txt`, `pyproject.toml`, `.env*` (DO NOT COMMIT)

### 2) `freepbx-deploy-ui/` (React/Vite)
Install:
- `npm install`

Run:
- Use `npm run <script>` from `package.json` as source of truth.
- Example: `npm run dev`

Test:
- TODO/VERIFY (run the test script defined in `package.json`, if present)

Config:
- `package.json`, `vite.config.ts`, `tsconfig.json`

### 3) `PolycomYealinkMikrotikSwitchConfig-main/.../` (React/Vite)
Install:
- `npm install`

Run:
- Use `npm run <script>` from `package.json` as source of truth.
- Example: `npm run dev`

Test:
- TODO/VERIFY (project contains `*.test.tsx`; use the defined `package.json` test script)

Config:
- `package.json`, `vite.config.ts`, `.storybook/`, `.prettierrc`, `eslint.config.js`

### 4) `traceroute-visualizer-main/traceroute-visualizer-main/` (Next.js)
Install:
- `npm install`

Run:
- Use `npm run <script>` from `package.json` as source of truth.
- Example: `npm run dev`

Test:
- TODO/VERIFY (use the defined `package.json` test/lint scripts)

Config:
- `package.json`, `next.config.ts`, `.env.local` (DO NOT COMMIT)

### 5) Traceroute Python backends (entrypoints included)
Entrypoints (choose one):
- `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/traceroute_server.py`
- `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/fastapi_traceroute_server.py`
- `traceroute-visualizer-main/traceroute-visualizer-main/src/backend/traceroute_server_py2.py`

Install:
- TODO/VERIFY which requirements file is authoritative:
  - `traceroute-visualizer-main/backend/requirements.txt`
  - and/or any requirements referenced by the backend scripts

Run/Test:
- TODO/VERIFY – do not guess flags/ports; follow the README for the traceroute project.

### 6) `webscraper/` (Selenium) – HIGH SENSITIVITY
Install:
- TODO/VERIFY (use `webscraper/requirements.txt` and `webscraper/README.md`)

Run/Test:
- TODO/VERIFY (follow `webscraper/README.md`)

Config:
- `webscraper/ultimate_scraper_config.py` may reference sensitive behavior. Never commit real creds/cookies.

### 7) `freepbx-tools/` (deployable server-side scripts)
Install/Run/Test:
- TODO/VERIFY exact invocation patterns from `freepbx-tools/README.txt`
- Scripts do exist: `bootstrap.sh`, `install.sh`, `uninstall.sh`, `make_executable.sh` (confirm usage in README before documenting exact commands)

Config:
- `freepbx-tools/requirements.txt`, `freepbx-tools/version_policy.json`

### 8) Flask web UI (repo root)
Install/Run/Test:
- TODO/VERIFY – use `RUN_APPS.md` and `web_requirements.txt` as sources of truth

Config:
- `web_requirements.txt`, and any `.env*` (DO NOT COMMIT)

### 9) KB / analysis scripts (repo root)
Run/Test:
- Several test entrypoints exist (e.g., `test_kb_system.py`, `test_selenium.py`, `test_dashboard.py`, `test_phone_analyzer_integration.py`).
- TODO/VERIFY the intended runner (plain `python`, `pytest`, or other) from `README.md` / `QUICK_TEST.md` / `TEST_KNOWLEDGE_BASE.md`.

Config:
- Use `config.example.py` and `scraper_config.example.py` as templates only. Do not commit real `config.py` / `scraper_config.py`.

---

## Existing repo conventions & tooling (observed)
- Ignore rules: `.gitignore` (sensitive outputs and artifacts are intentionally ignored)
- Line endings: `.gitattributes`
- Secret scanning / hooks: `.pre-commit-config.yaml`, `.gitleaks.toml`
- Secure push wrapper: `scripts/secure_push.py` (may be invoked by `git spush` if configured)
- Workspace/editor config: `.vscode/settings.json`, `freepbx-tools-suite.code-workspace`
- GitHub/Copilot guidance: `.github/copilot-instructions.md` and subproject copilot instructions

If pre-commit is installed, run:
- `pre-commit run -a`

---

## Adding new tools/scripts safely
1. Put new scripts under `scripts/` or a dedicated subfolder.
2. Ensure outputs go to an ignored folder (`output/`, `data/`, etc.) and update `.gitignore` first.
3. If a script needs secrets, use environment variables + a `*.example.*` template.
4. Update the nearest README / RUN_APPS.md with exact run steps.
5. Never commit binaries, dumps, or customer exports.

---

## TODO/VERIFY (do not guess)
- Confirm authoritative run/test commands for:
  - `webscraper/` (from `webscraper/README.md`)
  - traceroute backend scripts (from traceroute README)
  - Flask web UI (`RUN_APPS.md` / `docs/WEB_INTERFACE_README.md` if present)
  - repo-root KB/analysis test runner expectations (README/quick test docs)
- If a `git spush` alias is configured in global or repo-local config, verify it is portable (avoid hard-coded interpreter paths).

---

## Sources inspected (evidence list)
The following tracked paths were used to derive the repo map / tooling inventory:
- `.git/config`
- Output of `git ls-files`
- `README.md`
- `RUN_APPS.md`
- `QUICK_TEST.md`
- `freepbx-deploy-backend/README.md`
- `freepbx-deploy-ui/README.md`
- `PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/README.md`
- `traceroute-visualizer-main/traceroute-visualizer-main/README.md`
- `webscraper/README.md`
- `freepbx-tools/README.txt`
- `web_requirements.txt`
- `web_manager.py`
- `.gitignore`
- `.gitattributes`
- `.pre-commit-config.yaml`
- `.gitleaks.toml`
- `freepbx-tools-suite.code-workspace`