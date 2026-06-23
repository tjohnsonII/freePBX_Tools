# Known Issues

Recurring and structural issues in the FreePBX Tools suite. These are **not bugs to immediately fix** — they are environmental or architectural constraints to understand and work around.

Check here first when something breaks unexpectedly.

---

## Server Issues

### 1. Apache Config Invalid After Cert Expiry

**Symptoms:**
- `apache2ctl configtest` fails
- Services start but are unreachable externally
- `journalctl -u apache2` shows SSL cert errors

**Root Cause:** Let's Encrypt certs expire every 90 days. If auto-renewal failed, Apache won't reload with an expired cert config.

**Fix:**
```bash
sudo certbot renew --force-renewal
sudo systemctl reload apache2
# Or let FULL_START.sh handle it — it tries renewal if configtest fails
```

**Prevention:** `freepbx-tools-watchdog.service` should catch this on boot. Verify timer is active: `systemctl status freepbx-tools-watchdog.timer`

---

### 2. Stale Port on Restart

**Symptoms:** Service fails to start, logs say `address already in use`

**Fix:**
```bash
# Kill whatever is holding the port
sudo lsof -ti tcp:8788 | xargs kill 2>/dev/null
sudo lsof -ti tcp:8787 | xargs kill 2>/dev/null

# Or use RESTART.sh which handles this automatically
sudo ./RESTART.sh ticket-api
```

`FULL_START.sh` kills all known ports (3004, 3005, 3006, 3011, 5000, 8787, 8788) before starting services.

---

### 3. Front-End Not Updating After Code Change

**Symptoms:** Browser shows old UI after a `git pull`

**Root Cause:** `FULL_START.sh` uses MD5 source hashing to skip unchanged builds. If the hash file is stale, the build won't trigger.

**Fix:**
```bash
sudo ./FULL_START.sh --force-rebuild
# Or clear specific hash
rm manager-ui/.src_hash
sudo ./FULL_START.sh
```

---

### 4. Chrome Scraper Fails to Authenticate (Client)

**Symptoms:** Scraper starts but can't log in to 123.net portal; auth loop or timeout

**Root Cause:** Chrome session cookie expired or profile corrupted. The scraper must authenticate interactively at least once.

**Fix:**
1. VPN must be connected: `openvpn3 session-start --config /home/tim2/1767636174601.ovpn`
2. Start Chrome with the profile and log in manually
3. Restart the scraper worker: `sudo ./RESTART.sh worker`

If the profile is corrupt:
```bash
rm -rf webscraper/var/chrome-profile/
# Then re-authenticate interactively
```

---

### 5. VPN Not Connected (Client Mode)

**Symptoms:** Client scraper starts but gets 401/403 from 123.net portal or timeout on all pages

**Fix:**
```bash
openvpn3 sessions-list                        # check if session exists
openvpn3 session-start --config /home/tim2/1767636174601.ovpn
ip addr show tun0                             # verify tun0 has an IP
```

Via RESTART.sh: `sudo ./RESTART.sh vpn`

---

### 6. Chrome Remote Desktop Session Lost

**Symptoms:** Can't connect via Chrome Remote Desktop; session shows offline in browser

**Root Cause:** Xorg :20 process from previous CRD session wasn't cleaned up, or the service crashed.

**Fix:**
```bash
sudo ./RESTART.sh crd
# Or manually:
sudo systemctl stop chrome-remote-desktop@tim2
sudo kill $(pgrep -f "Xorg :20") 2>/dev/null
sudo rm -f /tmp/.X20-lock
sudo systemctl start chrome-remote-desktop@tim2
```

Wait ~30 seconds for CRD to appear online in the browser.

---

### 7. Ingest API Rejecting Client Requests (403)

**Symptoms:** Client scraper logs show `403 Invalid ingest API key`

**Root Cause:** `INGEST_API_KEY` in client `.env` doesn't match server `.env`.

**Fix:**
1. On server: `grep INGEST_API_KEY /var/www/freePBX_Tools/.env`
2. On client: update `.env` with the same value
3. Restart client: `./start_client.sh`

If `INGEST_API_KEY` is empty on the server, only localhost can POST to ingest — set the key.

---

### 8. systemd Service Fails After Unit File Change

**Symptoms:** `systemctl restart freepbx-tools.service` fails with "Unit file changed"

**Root Cause:** systemd unit files in `systemd/` are root-owned. systemd needs a daemon-reload after any change.

**Fix:**
```bash
# Files are root-owned — edit as root
sudo cp systemd/freepbx-tools.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart freepbx-tools.service
```

Note: `systemd/` in the repo is the source; `/etc/systemd/system/` is what systemd reads.

---

## Scraper / Data Issues

### 9. Ticket API DB Schema Mismatch

**Symptoms:** Ticket API starts but queries fail; `sqlite3.OperationalError: no such column`

**Root Cause:** Schema was updated but existing DB wasn't migrated.

**Fix:**
```bash
source .venv-webscraper/bin/activate
python -c "from webscraper.ticket_api.db_init import ensure_schema; ensure_schema('webscraper/var/db/tickets.sqlite')"
```

If that fails, the DB can be deleted (data is re-scraped on next run):
```bash
rm webscraper/var/db/tickets.sqlite
sudo ./RESTART.sh ticket-api
```

---

## FreePBX CLI Tools (Remote PBX Hosts)

### 10. Unicode / Locale Failures on FreePBX Hosts

**Symptoms:**
```
UnicodeEncodeError: 'ascii' codec can't encode character
```

**Root Cause:** FreePBX hosts run Python 3.6.7 with ASCII locale by default.

**Fix:** Add to `/root/.bashrc` and `/home/123net/.bashrc` on the FreePBX host:
```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

Log out and back in. Do not strip Unicode from tool output — it reduces diagnostic clarity.

---

### 11. FreePBX CLI Requires Root

**Symptoms:** `fwconsole` errors, database access denied, snapshot failures

**Fix:**
```bash
su root
# or
sudo <command>
```

All `freepbx-tools/bin/` scripts require root on the FreePBX host.

---

## Python Version Notes

| Environment | Python | Rules |
|-------------|--------|-------|
| This server | 3.12.x | Three isolated venvs |
| Client laptop | 3.12.x | Same venv layout |
| FreePBX PBX hosts | 3.6.7 (fixed) | `freepbx-tools/bin/` only |

Do not attempt to upgrade Python on FreePBX hosts — it will break the system.

---

## Git

### 12. Root-Owned Files Blocking Merges

**Symptoms:** `git merge` or `git checkout` fails with `Permission denied` on `systemd/` files

**Root Cause:** Systemd unit files are owned by root. Git can read them but cannot write/delete them.

**Workaround:**
```bash
# Stage the file (git can read it even without write permission)
git add systemd/freepbx-tools.service
# Now the merge sees no local modification and can proceed
```

---

## Not Issues (Expected Behavior)

- **`npm run dev` not working on server** — Production builds use `npm run build` + `npm run start`. Dev mode is for local development only.
- **PowerShell npm failures** — Irrelevant. The server runs Ubuntu/bash. Any Windows-specific npm notes in old docs are outdated.
- **VS Code multi-root warnings** — Workspace is single-root. Multi-root causes duplicate explorer entries. See `freepbx-tools-suite.code-workspace`.
