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
     - Run filters to remove files and replace sensitive strings.
3. Force push to the remote and ask collaborators to re-clone.

## Pre-Commit Guardrails
- Add a pre-commit hook to scan for secrets:
  - Install `pre-commit` and `detect-secrets` or `gitleaks`.
  - Configure `.pre-commit-config.yaml` and run `pre-commit install`.

## Ongoing Practices
- Keep `config.py` ignored (see .gitignore) and empty of real secrets.
- Never commit cookie files, session tokens, or raw scrape outputs.
- Prefer `cookies` via secure runtime injection, not version control.

## Incident Response
- Treat leaked cookies/tokens as compromised; invalidate sessions and regenerate.
- Audit access logs around the leak window.
- Re-scan the repo with GitGuardian or `gitleaks` after cleanup.
