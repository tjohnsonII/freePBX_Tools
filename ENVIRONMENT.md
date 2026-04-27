# Environment Reference

Source of truth for the server environment, venvs, Node versions, and shell requirements.

---

## Server

| Item | Value |
|------|-------|
| OS | Ubuntu Linux (24.04 LTS) |
| Hostname | 192.168.100.10 (local) |
| User | `tim2` |
| Repo path | `/var/www/freePBX_Tools` |
| Shell | `bash` |
| Remote access | Chrome Remote Desktop (display :20) |
| Virtual display | Xvfb :99 + x11vnc :5900 (for Chrome scraper) |

---

## Python

Three virtual environments at the repo root. Never cross-activate.

| Venv | Python | Used by | Bootstrap |
|------|--------|---------|-----------|
| `.venv` | 3.12.x | General scripts, `web_manager.py` | `python3 -m venv .venv` |
| `.venv-web-manager` | 3.12.x | Manager API (`webscraper_manager/`) | `python3 -m venv .venv-web-manager` |
| `.venv-webscraper` | 3.12.x | Ticket API + scraper (`webscraper/`) | `python3 -m venv .venv-webscraper` |

Create/repopulate all: `python3 scripts/bootstrap_venvs.py`

### Activate
```bash
source .venv/bin/activate               # general
source .venv-web-manager/bin/activate   # manager API
source .venv-webscraper/bin/activate    # ticket API + scraper
```

### Hard rules
- Never activate one venv when working in another project's context
- Never share venv directories across projects
- Deps for each venv are in that project's `requirements.txt` / `pyproject.toml`

---

## Python — FreePBX CLI Tools (Remote Systems)

`freepbx-tools/bin/` runs on actual FreePBX PBX servers (not this server):

| FreePBX host | Python 3.6.7 (fixed) |
|---|---|
| Must run as | `root` |
| Database access | `mysql` CLI via subprocess — no Python DB drivers |

**These tools must remain Python 3.6 compatible.** Do not use:
- Walrus operator (`:=`)
- Pattern matching (`match`/`case`)
- `pathlib` features newer than 3.6
- f-strings with complex expressions (some edge cases)
- Any type annotation syntax requiring `from __future__ import annotations`

Set UTF-8 locale on FreePBX hosts or tools will crash:
```bash
echo 'export LANG=en_US.UTF-8' >> /root/.bashrc
echo 'export LC_ALL=en_US.UTF-8' >> /root/.bashrc
```

---

## Node / npm

| Item | Value |
|------|-------|
| Node | v20+ (LTS recommended) |
| npm | v10+ |
| Package manager | npm (never yarn/pnpm) |

### Front-end apps and their Node setup

| App | Path | Build output |
|-----|------|-------------|
| Manager UI | `manager-ui/` | `.next/` |
| Ticket UI | `webscraper/ticket-ui/` | `.next/` |
| HomeLab Tracker | `HomeLab_NetworkMapping/ccna-lab-tracker/` | `.next/` |
| Traceroute Visualizer | `traceroute-visualizer-main/traceroute-visualizer-main/` | `.next/` |
| Polycom Config UI | `PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/` | `dist/` |
| FreePBX Deploy UI | `freepbx-deploy-ui/` | `dist/` |

### Commands (run from each app's directory)
```bash
npm ci          # clean install (use this, not npm install, in CI/startup)
npm run build   # production build
npm run start   # production server (Next.js) — requires build first
npm run dev     # development server (hot reload — not used in production)
```

### Production vs development
On the server, apps always run in production mode (`npm run start`). The `FULL_START.sh` script rebuilds (`npm run build`) then starts production servers. Never run `npm run dev` on the production server.

---

## Environment Variables

### `.env` (gitignored, must create from `.env.example`)

```bash
# Server mode (leave CLIENT_MODE unset or 0)
INGEST_API_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">

# Client mode (laptop running start_client.sh)
CLIENT_MODE=1
INGEST_SERVER_URL=http://192.168.30.19:8788   # or public HTTPS URL
INGEST_API_KEY=<same value as server>
WEBSCRAPER_PORT=8789   # optional, default 8789
```

### Runtime env vars (set by start scripts)

| Var | Set by | Purpose |
|-----|--------|---------|
| `NEXT_PUBLIC_API_BASE` | `FULL_START.sh` | Manager UI's API base URL |
| `CLIENT_MODE` | `start_client.sh` | Switch ticket API to remote write mode |
| `INGEST_SERVER_URL` | `.env` | Client → which server to POST to |
| `INGEST_API_KEY` | `.env` | Shared secret for ingest auth |
| `DISPLAY` | `start_services.sh` | X display for Chrome (`:99`) |
| `WEBSCRAPER_BROWSER` | scraper scripts | `chrome` |
| `WEBSCRAPER_CHROME_PROFILE_DIR` | scraper scripts | Chrome profile path |

---

## Pyright (Type Checking)

Multi-venv Pyrightconfig lives at `pyrightconfig.json` (root). It maps each project to its venv so Pylance resolves imports correctly across all three environments without false errors.

```json
{
  "venvPath": ".",
  "pythonVersion": "3.12",
  "executionEnvironments": [
    { "root": "webscraper_manager", "venv": ".venv-web-manager" },
    { "root": "webscraper",        "venv": ".venv-webscraper" },
    { "root": ".",                 "venv": ".venv" }
  ]
}
```

---

## VS Code Workspace

Open `freepbx-tools-suite.code-workspace` at the repo root. This is a single-root workspace (one entry, `"."`). Do not add nested folders as additional workspace roots — it causes duplicate explorer entries and confuses tooling.

---

## Git

```bash
git config user.name "Tim Johnson"
git config user.email "tjohnson082083@gmail.com"
```

Pre-commit hooks enforce secret scanning (gitleaks). Install hooks after cloning:
```bash
pip install pre-commit
pre-commit install
```

---

## SSH / Remote Access

| Method | Details |
|--------|---------|
| Chrome Remote Desktop | Display :20, `systemctl status chrome-remote-desktop@tim2` |
| VNC (x11vnc) | Port 5900, display :99, no password (LAN only) |
| OpenVPN | Profile: `/home/tim2/1767636174601.ovpn`, `openvpn3` |

---

## Windows Note (Legacy / Dev Only)

The `ENVIRONMENT.md` previously documented a Windows-first setup. That's outdated. The primary runtime is now the Linux server. Windows / WSL is only relevant for:
- Running the Polycom UI in dev mode locally (`npm run dev`)
- Running the FreePBX Deploy UI locally
- Windows-specific tooling (WinSCP, PuTTY) for accessing FreePBX hosts

The FreePBX CLI tools (`freepbx-tools/`) deploy to FreePBX servers — not to Windows.
