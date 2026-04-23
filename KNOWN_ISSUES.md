# KNOWN_ISSUES.md

This document tracks **known, recurring, or structural issues** in the FreePBX Tools workspace.

These are **not bugs to immediately fix** — they are **environmental or architectural constraints** that must be understood and worked around.

If you encounter unexpected behavior, check here first.

---

## 1. FreePBX Unicode / Locale Failures (CRITICAL)

### Symptoms
- CLI tools (e.g. `freepbx-callflows`) crash with:
UnicodeEncodeError: 'ascii' codec can't encode character

- Failures often occur when printing:
- Unicode symbols (✓ ✖ ⚠)
- Emoji-style markers
- Box-drawing characters

### Root Cause
- FreePBX hosts run **Python 3.6.7**
- System locale defaults to **ASCII**, not UTF-8
- Python attempts to print Unicode to a non-UTF terminal

### Affected Components
- `freepbx-tools/bin/*.py`
- Especially `freepbx_callflow_menu.py`

### Mitigation (REQUIRED)
Set UTF-8 locale on FreePBX hosts:

```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
Permanent Fix
Add the exports to both:

/root/.bashrc

/home/123net/.bashrc

Then log out and back in.

❌ Not Recommended
Stripping Unicode characters from CLI output
This reduces usability and diagnostic clarity.

2. Python Version Fragmentation (STRUCTURAL)
Observed Versions
Environment	Python
FreePBX servers	3.6.7
WSL (Ubuntu)	3.12.x
Windows	3.12.x
Risk
Modern Python features will break FreePBX tools.

Common failure sources:

Advanced typing

Modern pathlib behavior

Subtle f-string formatting changes

Rules
freepbx-tools/bin/**

MUST remain Python 3.6 compatible

❌ No walrus operator, pattern matching, or modern typing

Backend, scrapers, and UI tooling:

May use Python 3.10+ / 3.12

Must be isolated in their own virtual environments

3. Node / npm Does Not Work in PowerShell (EXPECTED)
Symptoms
npm -v or npm run dev fails in PowerShell

Errors referencing npm.ps1

Root Cause
PowerShell resolves npm → npm.ps1

Script execution is restricted on domain-joined machines

Execution policy cannot and should not be changed

Resolution (MANDATORY)
Use Windows CMD for all Node / npm work

WSL is the fallback

This is by design and documented in ENVIRONMENT.md.

❌ Do NOT
Change execution policy

Attempt to “fix” PowerShell

Add PowerShell-based npm instructions

4. Duplicate Folder Appearance in VS Code (Workspace Issue)
Symptoms
Duplicate folders in VS Code Explorer

Confusing “nested repo” appearance

Incorrect imports or tooling behavior

Root Cause
VS Code workspace included multiple overlapping roots

Resolution
Workspace file must include only the repo root:

"folders": [
  { "path": "." }
]
Status
Fixed

Do not reintroduce multi-root layouts

5. Virtual Environment Confusion (Windows vs WSL)
Symptoms
source fails in Windows

Activate.ps1 fails in WSL

Python packages appear “missing”

Root Cause
Mixing Windows and Linux virtual environments

Rules
Windows venvs → activated from CMD (or unused)

WSL venvs → activated via source .venv/bin/activate

❌ Never cross-activate environments

❌ Never share .venv directories between projects

6. Large Generated / Data Files Tracked in Repo
Examples
unified_knowledge_base.db

vpbx_data.db

all_tickets.json

Risk
Repository bloat

Slow clones

Accidental propagation of derived data

Status
Currently tracked

Do not add new generated data without review

Candidate for .gitignore or external storage later

7. FreePBX Permission Constraints
Symptoms
fwconsole errors

Database access denied

Snapshot or diagnostic failures

Root Cause
FreePBX tooling requires root access

Rule
All FreePBX CLI tools must be run as root:

su root
# or
sudo <command>
Running as the SSH user (e.g. 123net) is insufficient.

Summary
These issues are known, intentional constraints, not defects.

Do not attempt to “fix” them by:

upgrading Python on FreePBX

changing PowerShell execution policy

collapsing environments

simplifying runtime assumptions