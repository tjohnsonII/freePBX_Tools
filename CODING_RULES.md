# Coding Rules

These rules reflect the current server architecture. Read before making any changes.

---

## Repository Zones

### Zone A — FreePBX CLI Tools (STRICT)
**Path:** `freepbx-tools/bin/`

- Deployed to production FreePBX PBX servers (not this server)
- Must remain **Python 3.6 compatible** — these hosts run 3.6.7 and cannot be upgraded
- Run as `root` on remote FreePBX hosts
- No modern Python: no walrus operator, no pattern matching, no advanced typing
- No Python DB drivers — use `mysql -NBe` via subprocess
- Assume UTF-8 locale may be missing (see KNOWN_ISSUES.md #1)

### Zone B — Server Python (Current)
**Paths:** `webscraper/`, `webscraper_manager/`, `scripts/`, root helpers

Three isolated venvs — never cross-activate:

| Venv | Path | Used by |
|------|------|---------|
| `.venv` | Root | General scripts, `web_manager.py` |
| `.venv-web-manager` | Root | `webscraper_manager/` (Manager API :8787) |
| `.venv-webscraper` | Root | `webscraper/` (Ticket API :8788, scraper) |

- Python 3.12.x
- Always update `requirements.txt` or `pyproject.toml` before installing packages
- Never install packages into the system Python

### Zone C — Front-End Apps (Node)
**Paths:** `manager-ui/`, `webscraper/ticket-ui/`, `PolycomYealinkMikrotikSwitchConfig-main/`, `traceroute-visualizer-main/`, `HomeLab_NetworkMapping/ccna-lab-tracker/`, `freepbx-deploy-ui/`

- Node 20+ LTS, npm (not yarn/pnpm)
- On the server: always `npm ci` + `npm run build` + `npm run start` (production mode)
- Dev mode (`npm run dev`) is for local development only — never run on the server
- `FULL_START.sh` handles builds automatically (MD5 source hash to skip unchanged apps)
- Never run `npm install` by hand — use `npm ci` in scripts; `npm install --save` when adding deps

### Zone D — Client Scraper
**Path:** `start_client.sh`, `.env` with `CLIENT_MODE=1`

- Runs on a laptop connected to 123.net portal via VPN
- Sends all scraped data to the server via `POST /api/ingest/*` with `X-Ingest-Key`
- Never writes to local SQLite in client mode
- Requires `INGEST_SERVER_URL` and `INGEST_API_KEY` in `.env`

---

## Rules for All Changes

1. **Never commit secrets** — `.env`, cookies, auth tokens, session data, credentials. Ever.
2. **Never cross-activate venvs** — each zone has its own venv; mixing causes silent breakage.
3. **Never run `dev` mode on the server** — always production builds.
4. **Never commit to `server` or `client` branch directly** — develop on `main`, rebase branches from it.
5. **One task = one commit** — don't bundle unrelated changes.
6. **Always state which zone you're editing** — in the commit message and PR description.
7. **Update the relevant `requirements.txt` or `package.json` before adding any dependency.**
8. **Don't reformat unrelated files** — scoped diffs only.
9. **Outputs go to ignored folders** — `var/`, `webscraper/var/`, `dist/`, `.next/`. Add `.gitignore` entries first.
10. **Zone A code (freepbx-tools/) stays Python 3.6 compatible.** Verify on 3.6 before committing.

---

## Port Registry (Authoritative)

| Port | Service | Venv/Runtime |
|------|---------|-------------|
| 3004 | Manager UI | npm (Next.js) |
| 3005 | Ticket UI | npm (Next.js) |
| 3006 | Traceroute UI | npm (Next.js) |
| 3011 | HomeLab Tracker | npm (Next.js) |
| 5000 | FreePBX Web Manager | `.venv` (Flask) |
| 8787 | Manager API | `.venv-web-manager` (FastAPI) |
| 8788 | Ticket API | `.venv-webscraper` (FastAPI) |
| 8789 | Client Trigger API | `.venv-webscraper` (FastAPI, client only) |

---

## Secrets Model

| Secret | Where | How to generate |
|--------|-------|----------------|
| `INGEST_API_KEY` | `.env` (gitignored) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `CLIENT_MODE` | `.env` on client | Set to `1` |
| `INGEST_SERVER_URL` | `.env` on client | Server URL |

Copy `.env.example` → `.env` and never commit the result.

---

## Commit Safety

All pushes run through pre-commit hooks (gitleaks). Never skip with `--no-verify`.

If a push fails secret scanning:
1. Remove the secret from the staged file
2. Rotate the secret at its source
3. Run `pre-commit run -a` to verify clean
4. Commit again
