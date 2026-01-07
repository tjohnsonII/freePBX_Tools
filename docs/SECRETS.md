# Secrets Remediation and Handling

This repository previously contained high-entropy values and cookie artifacts flagged by GitGuardian. To prevent future leaks and remediate existing incidents, follow these steps.

## Immediate Cleanup
- Remove sensitive artifacts from git tracking (kept locally):
  - cookies.txt
  - cookies_header_string.txt
- Commit and push the removal.

## Credential Management
- Use environment variables for FreePBX credentials:
  - FREEPBX_USER
  - FREEPBX_PASSWORD
  - FREEPBX_ROOT_PASSWORD
- The committed `config.py` only loads from env and validates presence.
- Example: see `config.example.py` for the pattern.

## History Rewrite (if secrets were committed)
If any real secrets were pushed previously, rotate them and scrub history.

1. Rotate secrets at their source (FreePBX, portals, APIs).
2. Rewrite history to remove files and values:
   - Option A: BFG Repo-Cleaner
     - Download BFG: https://rtyley.github.io/bfg-repo-cleaner/
     - Create a `bfg.txt` with file/name patterns (e.g., `cookies.txt`, `config.py`).
     - Run: `java -jar bfg.jar --delete-files cookies.txt --delete-files cookies_header_string.txt repo.git`
   - Option B: git filter-repo
     - Install: https://github.com/newren/git-filter-repo
     - Use a purge list to remove generated outputs:
       - Create `sensitive_paths.txt` with:
         - `webscraper/output/`
         - `webscraper/ticket-discovery-output/`
       - Run: `git filter-repo --force --invert-paths --paths-from-file sensitive_paths.txt`
3. Force push to the remote and ask collaborators to re-clone.

## Gitleaks Configuration

To reduce noise from generated artifacts (while still preferring history purge), add an allowlist config:

- `.gitleaks.toml`:
  - `[allowlist]`
  - `paths = ["webscraper/output", "webscraper/ticket-discovery-output"]`

This affects scans only and does not replace history purge.

## Pre-Commit Guardrails
- Add a pre-commit hook to scan for secrets:
  - Install `pre-commit` and `detect-secrets` or `gitleaks`.
  - Configure `.pre-commit-config.yaml` and run `pre-commit install`.

## Secure Push Workflow (Default Mirror)
- One command does everything:
  - `python scripts/secure_push.py`
  - Automatically stages, runs hooks, commits (if changes exist), then scans history and pushes securely.
- What it does:
  - Runs pre-commit hooks (`detect-secrets`, `gitleaks`), normalizes allowlist pragmas, and blocks staged sensitive files.
  - Scans repo history with `gitleaks`; if leaks are detected, automatically runs a history purge and re-scans.
  - Defaults to force `--mirror` push so remote refs match local after any rewrite.
- Optional: Normal (non-mirror) push for routine non-rewrite commits:
  - `python scripts/secure_push.py --normal`
  - Provide a custom commit message:
    - `python scripts/secure_push.py --message "update: docs and config"`
- Note: Mirror pushing is destructive and overwrites remote refs; use `--normal` for routine commits if you do not want to mirror.

## Will This Prevent Committing Passwords?
- Yes, the workflow prevents committing passwords in normal use by:
  - Pre-commit hooks (`detect-secrets`, `gitleaks`) scanning all files before commit/push.
  - A staged-file safety check that explicitly blocks known sensitive artifacts.
  - Allowlist pragmas only on placeholder/example lines, to avoid false positives without masking real secrets.
- Caveats:
  - If hooks are bypassed (`git commit --no-verify`) or pushes occur outside the script, protections may not run.
  - Keep real credentials out of the repo entirely; use environment variables and runtime injection.

## Ongoing Practices
- Keep `config.py` ignored (see .gitignore) and empty of real secrets.
- Never commit cookie files, session tokens, or raw scrape outputs.
- Prefer `cookies` via secure runtime injection, not version control.

## Incident Response
- Treat leaked cookies/tokens as compromised; invalidate sessions and regenerate.
- Audit access logs around the leak window.
- Re-scan the repo with GitGuardian or `gitleaks` after cleanup.
