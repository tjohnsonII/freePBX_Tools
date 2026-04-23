# DEPENDENCIES.md

This document describes **dependency boundaries and classes**, not every installed package.

Exact versions are defined in:
- `package.json` / lock files (Node apps)
- `requirements.txt` / `pyproject.toml` (Python apps)

If something breaks due to a dependency, **check the section for that subproject first**.

---

## 1. System-Level Dependencies

### FreePBX Servers (Production / Lab)
- Linux (CentOS / RHEL derivatives)
- **Python 3.6.7 (fixed, non-upgradable)**
- MySQL (FreePBX-managed)
- `mysql` CLI (used via subprocess)
- `fwconsole`
- Bash
- SSH access
- UTF-8 locale (**required**)

⚠ These systems are legacy-constrained. Tooling must adapt to them — not the other way around.

---

### Windows (Domain-Joined)
- Windows 10/11
- CMD (required for Node/npm)
- PowerShell (limited use: Git, editing, reading logs)
- Python 3.12.x
- Node.js (modern, non-LTS acceptable; v24 observed)
- Git for Windows
- VS Code

⚠ PowerShell execution policy **cannot be changed** and is intentionally avoided for Node/npm.

---

### WSL2 (Ubuntu 24.04 LTS)
- Bash shell
- Python 3.12.x
- Node.js
- npm
- Chromium / Chrome (for Selenium)
- Linux utilities (`grep`, `sed`, `awk`, etc.)

WSL is treated as a **Linux-first development environment**, not a Windows replacement.

---

## 2. Python Dependencies (by Area)

### A. FreePBX CLI Tools (Server-Side)

**Location**
- `freepbx-tools/bin/*.py`

**Runtime**
- Python **3.6.7 ONLY**

**Hard Constraints**
- Must run on legacy FreePBX hosts
- Must run as `root`
- Must tolerate ASCII/UTF-8 quirks

**Dependencies**
- `mysql` CLI (invoked via `subprocess`)
- `argparse`
- `json`
- `os`, `sys`
- `subprocess` (stdlib)

**Explicitly Forbidden**
- Python DB drivers (`mysqlclient`, `pymysql`)
- Walrus operator (`:=`)
- Pattern matching
- Modern `pathlib` assumptions
- Advanced typing / annotations

---

### A2. Deployment & Orchestration Scripts

**Files**
- `deploy_freepbx_tools.py`
- `deploy_uninstall_tools.py`
- `scripts/*`

**Runtime**
- Python 3.12.x (Windows / WSL)

**Dependencies**
- `paramiko`
- `scp` / `ssh` (external tools)
- `requests`
- `subprocess`

These scripts **do not run on FreePBX hosts**.

---

### B. FreePBX Deploy Backend (FastAPI)

**Location**
- `freepbx-deploy-backend/`

**Runtime**
- Python 3.12.x

**Dependencies**
- `fastapi`
- `uvicorn`
- `pydantic`
- `requests`
- `python-dotenv`

Defined in:
- `requirements.txt`
- `pyproject.toml`

Runs locally for development and testing.

---

### C. Webscraper / Knowledge Base Tooling

**Locations**
- `webscraper/`
- Root-level scraper scripts

**Runtime**
- Python 3.12.x
- WSL preferred

**Dependencies**
- `selenium`
- `beautifulsoup4`
- `lxml`
- `requests`
- `sqlite3` (stdlib)

**External Requirements**
- Chrome / Chromium
- Matching WebDriver version

⚠ WebDriver version **must match browser version**.

---

## 3. Node / Frontend Dependencies

### Shared Stack
- Node.js
- npm
- TypeScript
- React

### Tooling
- Vite
- ESLint
- PostCSS
- esbuild

---

### A. FreePBX Deploy UI

**Location**
- `freepbx-deploy-ui/`

**Commands**
- `npm install`
- `npm run dev`
- `npm run build`
- `npm run preview`

Runs via **Windows CMD** (required).

---

### B. Polycom / Yealink / Mikrotik Config UI

**Location**
- `PolycomYealinkMikrotikSwitchConfig-main/`

**Purpose**
- Generate configuration files
- UI-only
- No backend or deployment logic

---

### C. Traceroute Visualizer (Frontend)

**Location**
- `traceroute-visualizer-main/`

**Notes**
- UI runs locally
- Backend typically runs remotely on FreeBSD
- Local FastAPI backend exists for development/testing

---

## 4. What Is Explicitly NOT Tracked Here

- Individual `node_modules` packages
- Transitive npm dependencies
- Virtual environment contents
- Copilot-installed helper libraries

These are defined in lock files and intentionally excluded.

---

## 5. Guidance for Codex / AI Agents

- Do **not** assume a single runtime for the repo
- Always check folder context before proposing changes
- Never introduce modern Python into FreePBX CLI tools
- Do not replace MySQL CLI calls with Python DB drivers
- Prefer WSL for scraping and backend experimentation
- Treat CMD as the authoritative Node environment on Windows

---

## Status

This file should change **rarely**.

If it changes often, dependency boundaries are leaking and must be corrected.
