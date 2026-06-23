# Security Guide

Security practices for the FreePBX Tools Suite.

---

## Secrets Model

### What Secrets Exist

| Secret | Where stored | Purpose |
|--------|-------------|---------|
| `INGEST_API_KEY` | `.env` (server + client) | Authenticates client scraper → server ingest API |
| `INGEST_SERVER_URL` | `.env` (client only) | Server URL for client to POST to |
| `CLIENT_MODE` | `.env` (client only) | Switches ticket API to remote write mode |
| Chrome profile cookies | `webscraper/var/chrome-profile/` | 123.net portal session |
| FreePBX credentials | Environment vars only, never files | Remote PBX server auth |

### The `.env` File

```bash
# Copy template and fill in values
cp .env.example .env
```

The `.env` file is gitignored and must never be committed. It contains real secrets.  
`.env.example` is committed and contains only placeholders.

Generate a secure `INGEST_API_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

The same key must be in `.env` on both the server and the client. If they differ, the client gets 403.

---

## Ingest API Authentication

The server's `/api/ingest/*` endpoints receive scraped data from the client laptop. They use HMAC constant-time comparison to prevent timing attacks:

```python
# ingest_routes.py
if not hmac.compare_digest(key, provided):
    raise HTTPException(status_code=403, detail="Invalid ingest API key.")
```

- Key is set via `INGEST_API_KEY` env var on the server
- Client sends it in `X-Ingest-Key` header
- If the env var is empty on the server, only `127.0.0.1` and `::1` are allowed (safe for local dev)
- All external traffic goes through Apache HTTPS — the key is encrypted in transit

**Rotate the key:**
1. Generate new key: `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. Update `.env` on server
3. Update `.env` on client
4. `sudo systemctl restart freepbx-tools.service` (server)
5. Restart `./start_client.sh` (client)

---

## Network Security

- All public-facing services are behind Apache on port 443 (HTTPS)
- Internal services bind `127.0.0.1` only — not accessible from the network directly
- Apache terminates SSL via Let's Encrypt / certbot
- VPN (`openvpn3`) is required for the client to reach the 123.net portal

---

## Pre-Commit Hooks (Secret Scanning)

Every commit runs `gitleaks` via pre-commit hooks. This blocks secrets from entering git history.

```bash
# Install hooks (once, after cloning)
pip install pre-commit
pre-commit install

# Run manually on all files
pre-commit run -a
```

Never bypass with `--no-verify`. If a hook blocks a legitimate commit:
1. Check if the file contains a real secret — if so, remove it and rotate at the source
2. If it is a false positive, add to `.secrets.baseline`:
   ```bash
   detect-secrets scan > .secrets.baseline
   git add .secrets.baseline
   ```

---

## Data Sensitivity

| Data | Sensitivity | Handling |
|------|------------|---------|
| Ticket content | Customer-confidential | SQLite at `webscraper/var/db/tickets.sqlite` — gitignored |
| Handle list | Internal | `webscraper/configs/handles/handles_master.txt` — committed (codes only, no customer content) |
| Chrome profile | Contains session cookies | `webscraper/var/chrome-profile/` — gitignored |
| Scrape run artifacts | Customer data | `webscraper/var/runs/` — gitignored |

---

## If a Secret Is Accidentally Committed

1. **Immediately rotate the secret at its source** (generate new `INGEST_API_KEY`, invalidate portal session, etc.)
2. Remove from git history:
   ```bash
   pip install git-filter-repo
   git filter-repo --force --invert-paths --path path/to/secret/file
   git push origin --force --all
   ```
3. All collaborators must re-clone after the history rewrite
4. Review access logs for the window during which the secret was exposed

---

## FreePBX Host Credentials

For `freepbx-tools/bin/` scripts connecting to remote FreePBX PBX hosts:

- Pass credentials via environment variables, never hard-coded
- `FREEPBX_USER`, `FREEPBX_PASSWORD`, `FREEPBX_ROOT_PASSWORD`
- Use `config.example.py` as the template — never commit `config.py` with real values
- Prefer SSH key authentication over passwords where possible

---

## Access Control Summary

| System | How accessed | Auth method |
|--------|-------------|------------|
| Server | Chrome Remote Desktop | Google account |
| Server | VNC :5900 (LAN only) | No password — LAN-only, do not expose externally |
| 123.net portal | VPN + browser | Portal credentials in Chrome profile |
| Ingest API | HTTPS + X-Ingest-Key header | HMAC token |
| Manager API | Localhost + Apache proxy | Apache HTTPS |
| Apache | Public HTTPS | SSL cert via certbot |
