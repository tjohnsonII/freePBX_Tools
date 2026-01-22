# Coding Rules (Must Follow)

These rules exist because this repo runs across **multiple runtimes** (FreePBX Python 3.6, WSL/Windows Python 3.12, Node/Vite/Next.js).

## Repo Zones
### A) FreePBX production CLI tools (STRICT)
Path: `freepbx-tools/bin/`

- MUST remain compatible with **Python 3.6**
- NO modern syntax/features that break 3.6
- Avoid fancy Unicode output unless UTF-8 locale is guaranteed
- Assume many commands require **root** access

### B) Modern Python tooling (OK)
Paths:
- `freepbx-deploy-backend/`
- `webscraper/`
- repo-root helper scripts

- May use Python 3.12 features
- Should run in WSL and/or Windows venv

### C) Node apps
Paths:
- `freepbx-deploy-ui/` (Vite)
- `PolycomYealinkMikrotikSwitchConfig-main/` (Vite)
- `traceroute-visualizer-main/` (Next.js)

- Prefer running via **WSL** if PowerShell blocks npm.ps1

## Rules for changes
- Never change multiple subprojects in one commit unless required.
- Always state which zone you’re editing and why.
- Don’t add new dependencies without updating DEPENDENCIES.md (or relevant requirements/package.json).
- Don’t commit secrets, cookies, or auth tokens — ever.
