# ENVIRONMENT.md

This repository is a **multi-app, multi-OS workspace** that intentionally spans:

- **Windows 10/11 (domain-joined)**
- **WSL2 Ubuntu (Linux tooling)**
- **Remote FreePBX servers (older Linux + Python 3.6)**
- **Node / React webapps (local dev servers)**

This document is the **source of truth** for how this repo is expected to run.

If something behaves differently than expected, **check here first**.

---

## 🚦 HARD RULES (Read First)

These rules are not preferences — they are constraints discovered through use.

- **Node / npm work happens in Windows CMD**
- **WSL is the fallback for Node or Linux tooling**
- **PowerShell is NOT used for Node or npm**
- **No execution policy changes are required or expected**
- **FreePBX CLI tools must remain Python 3.6 compatible**
- **VS Code must use a single-root workspace**

---

## 1) Repository location & workspace layout

### Windows (host)
- **Repo root:**  
  `E:\DevTools\freepbx-tools`

### WSL2 (Linux)
- **Mounted path:**  
  `/mnt/e/DevTools/freepbx-tools`

### VS Code workspace
- **Workspace file:** `freepbx-tools-suite.code-workspace`

#### REQUIRED workspace configuration
```json
"folders": [
  { "path": "." }
]
❗ Do NOT add nested subfolders as workspace roots

Doing so causes:

Duplicate folders in Explorer

Confusing imports

Incorrect tooling behavior

“Nested repo” illusions

2) Shell usage by task (IMPORTANT)
Windows CMD (PRIMARY)
Used for:

Node / npm

Vite / Next.js / React dev servers

Anything that runs npm

Why:

CMD runs npm.cmd

CMD is not blocked by execution policy

CMD works on domain-joined machines

PowerShell (LIMITED USE)
Used only for:

Git commands

Editing files

Reading logs

Running non-script binaries

⚠ PowerShell is NOT used for Node, npm, or venv activation

Execution policy cannot be changed on this machine and does not need to be.

WSL2 (Ubuntu)
Distro: Ubuntu 24.04 LTS

Shell: bash

Used for:

Python development

Web scraping

Linux-only utilities

Node tooling here is fallback only if CMD has filesystem or watcher issues.

WSL is preferred for:

webscraper/

Backend Python testing

Bash scripts

3) Remote FreePBX servers
OS: Older CentOS / RHEL variants

Python: 3.6.7 (fixed)

Shell: bash

Permissions: root required

⚠ All FreePBX CLI tools must be run as root

su root
# or
sudo <command>
Running as the SSH user (e.g. 123net) will fail for:

MySQL access

fwconsole

Snapshot generation

4) Python versions & compatibility (CRITICAL)
Observed Python versions
Environment	Python
FreePBX servers	3.6.7
WSL	3.12.x
Windows	3.12.x
Compatibility rules
freepbx-tools/bin/**
MUST remain Python 3.6 compatible

❌ Do NOT use:

Walrus operator (:=)

Pattern matching

Modern pathlib assumptions

Advanced typing features

✅ Use:

subprocess

Conservative string formatting

Defensive error handling

Backend, scrapers, UI tooling
May use Python 3.10+ / 3.12

Each project MUST have its own virtual environment

Do NOT share venvs across subprojects

5) Python virtual environments
Windows
Virtualenvs exist but are not activated via PowerShell on this machine.

If needed, use:

CMD

or WSL

WSL / Linux
python3 -m venv .venv
source .venv/bin/activate
⚠ Do NOT:

Activate Linux venvs from PowerShell

Activate Windows venvs from WSL

Share .venv directories between projects

6) Node / npm workflow (MANDATORY)
The rule
Use Windows CMD

Do NOT use PowerShell

Do NOT change execution policy

If CMD works and PowerShell fails — that is expected.

Verify Node (CMD)
cd /d E:\DevTools\freepbx-tools
node -v
npm -v
Run apps (CMD)
FreePBX Deploy UI

cd /d E:\DevTools\freepbx-tools\freepbx-deploy-ui
npm install
npm run dev
Polycom / Yealink / Mikrotik Config UI

cd /d E:\DevTools\freepbx-tools\PolycomYealinkMikrotikSwitchConfig-main\PolycomYealinkMikrotikSwitchConfig-main
npm install
npm run dev
Traceroute Visualizer UI

cd /d E:\DevTools\freepbx-tools\traceroute-visualizer-main\traceroute-visualizer-main
npm install
npm run dev
7) Locale & Unicode (FreePBX servers)
Problem
Python 3.6 + ASCII locale causes crashes:

UnicodeEncodeError: 'ascii' codec can't encode character
REQUIRED fix
Add to both:

/root/.bashrc

/home/123net/.bashrc

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
Log out and back in.

❌ Do NOT strip Unicode from scripts
(see KNOWN_ISSUES.md)

8) Git & repository rules
Branch: main

Remote: origin

Secure pushes enforced via:

pre-commit

gitleaks

scripts/secure_push.py

⚠ Large generated files exist (see KNOWN_ISSUES.md).
New derived data must not be added without review.

9) Summary
Area	Rule
Node / npm	Windows CMD only
PowerShell	Git + editing only
WSL	Python & Linux tooling
FreePBX CLI	Python 3.6, root required
VS Code	Single-root workspace
Unicode	UTF-8 locale REQUIRED