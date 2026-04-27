# FreePBX Tools Suite — Runbook

Exact commands for running, restarting, debugging, and health-checking every service.

---

## Server Environment

| Item | Value |
|------|-------|
| Host | Ubuntu Linux (always-on server) |
| Repo | `/var/www/freePBX_Tools` |
| User | `tim2` |
| Root required | `FULL_START.sh`, `RESTART.sh`, systemd ops |
| External IP | Accessible via Chrome Remote Desktop |

---

## Service Registry

| Service | Port | Process | Venv |
|---------|------|---------|------|
| Manager API | 8787 | uvicorn `webscraper_manager.api.server:app` | `.venv-web-manager` |
| Manager UI | 3004 | `npm run start` (Next.js) | — |
| Ticket API | 8788 | uvicorn `webscraper.ticket_api.app:app` | `.venv-webscraper` |
| Ticket UI | 3005 | `npm run start` (Next.js) | — |
| Traceroute UI | 3006 | `npm run start` (Next.js) | — |
| HomeLab Tracker | 3011 | `npm run start` (Next.js) | — |
| Scraper Worker | — | `python -m webscraper` | `.venv-webscraper` |
| FreePBX Web Mgr | 5000 | `python web_manager.py` | `.venv` |
| Apache | 80/443 | systemd `apache2` | — |

---

## Startup Scripts

### FULL_START.sh — Full Rebuild and Start
Use after code changes, fresh clones, or cert renewals.

```bash
cd /var/www/freePBX_Tools
sudo ./FULL_START.sh

# Force-rebuild all front ends regardless of source hash
sudo ./FULL_START.sh --force-rebuild
```

What it does (in order):
1. Git pull (`--rebase`) on current branch
2. Rebuild each front end only if source changed (MD5 hash check)
3. Write `.env.local` for manager-ui (`NEXT_PUBLIC_API_BASE`)
4. Stop all services + kill stale ports (3004, 3005, 3006, 3011, 5000, 8787, 8788)
5. Start/reload Apache (renews certbot if config invalid)
6. `python3 scripts/run_all_web_apps.py --webscraper-mode api --extras`
7. Health check each port (20 second timeout each)

Logs: `var/logs/startup/full_start_YYYYMMDD_HHMMSS.log`

---

### RESTART.sh — Per-Service Restart (Interactive)

```bash
sudo ./RESTART.sh           # interactive menu
sudo ./RESTART.sh all       # → runs FULL_START.sh
sudo ./RESTART.sh manager-api
sudo ./RESTART.sh manager-ui
sudo ./RESTART.sh ticket-api
sudo ./RESTART.sh ticket-ui
sudo ./RESTART.sh worker
sudo ./RESTART.sh apache
sudo ./RESTART.sh vpn
sudo ./RESTART.sh vnc
sudo ./RESTART.sh crd       # Chrome Remote Desktop
sudo ./RESTART.sh desktop   # VNC + CRD together
```

---

### scripts/start_services.sh — Lean Boot Startup
Called by `freepbx-tools.service` on boot. No git pull, no front-end rebuild.

```bash
sudo bash /var/www/freePBX_Tools/scripts/start_services.sh
```

---

### start_client.sh — Client Mode (Laptop)
Run on the client laptop, not the server.

```bash
cd /path/to/freePBX_Tools
cp .env.example .env       # fill in INGEST_SERVER_URL and INGEST_API_KEY
./start_client.sh
```

---

## Systemd

```bash
# Service status
systemctl status freepbx-tools.service
systemctl status freepbx-tools-watchdog.service

# Start / stop / restart
sudo systemctl start freepbx-tools.service
sudo systemctl stop freepbx-tools.service
sudo systemctl restart freepbx-tools.service

# Follow live logs
journalctl -fu freepbx-tools.service

# After editing unit files (files in systemd/ are root-owned)
sudo systemctl daemon-reload
sudo systemctl restart freepbx-tools.service
```

---

## Manual Service Commands

These are what `RESTART.sh` runs under the hood. All commands from `/var/www/freePBX_Tools`.

### Manager API
```bash
source .venv-web-manager/bin/activate
uvicorn webscraper_manager.api.server:app --host 127.0.0.1 --port 8787 &
```

### Manager UI
```bash
npm --prefix manager-ui run start -- --port 3004 --hostname 127.0.0.1 &
```

### Ticket API
```bash
source .venv-webscraper/bin/activate
uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8788 &
```

### Ticket UI
```bash
npm --prefix webscraper/ticket-ui run start -- --port 3005 --hostname 127.0.0.1 &
```

### Traceroute UI
```bash
npm --prefix traceroute-visualizer-main/traceroute-visualizer-main run start -- --port 3006 --hostname 127.0.0.1 &
```

### HomeLab Tracker
```bash
npm --prefix HomeLab_NetworkMapping/ccna-lab-tracker run start -- --port 3011 --hostname 127.0.0.1 &
```

### Scraper Worker
```bash
sudo -H -u tim2 -- env DISPLAY=:20 \
  WEBSCRAPER_BROWSER=chrome \
  WEBSCRAPER_CHROME_PROFILE_DIR=/var/www/freePBX_Tools/webscraper/var/chrome-profile \
  HOME=/home/tim2 \
  .venv-webscraper/bin/python -m webscraper --mode headless &
```

### FreePBX Web Manager
```bash
source .venv/bin/activate
python web_manager.py &
```

---

## Health Checks

```bash
# Quick port check
curl -sf http://127.0.0.1:8787/api/health && echo OK
curl -sf http://127.0.0.1:8788/api/health && echo OK

# Check all ports are listening
ss -tlnp | grep -E '3004|3005|3006|3011|5000|8787|8788'

# Full health check (same as FULL_START.sh does)
for port in 3004 3005 3006 3011 8787 8788; do
  curl -sf "http://127.0.0.1:$port/" -o /dev/null && echo "$port OK" || echo "$port FAIL"
done

# Public URLs
curl -sf https://tickets.123hostedtools.com/ -o /dev/null && echo "tickets OK"
curl -sf https://manager-api.123hostedtools.com/api/health && echo ""
```

---

## Building Front Ends

### All at once (FULL_START.sh handles this)
```bash
sudo ./FULL_START.sh --force-rebuild
```

### Individual app rebuild
```bash
# Manager UI (Next.js)
cd /var/www/freePBX_Tools/manager-ui
npm ci && npm run build

# Ticket UI (Next.js)
cd /var/www/freePBX_Tools/webscraper/ticket-ui
npm ci && npm run build

# Polycom/Yealink Config UI (Vite)
cd /var/www/freePBX_Tools/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main
npm ci && npm run build

# HomeLab Tracker (Next.js)
cd /var/www/freePBX_Tools/HomeLab_NetworkMapping/ccna-lab-tracker
npm ci && npm run build

# Traceroute (Next.js)
cd /var/www/freePBX_Tools/traceroute-visualizer-main/traceroute-visualizer-main
npm ci && npm run build
```

---

## Python Venvs

### Create / repopulate all three venvs
```bash
python3 scripts/bootstrap_venvs.py
```

### Activate manually
```bash
source .venv/bin/activate               # general
source .venv-web-manager/bin/activate   # manager API
source .venv-webscraper/bin/activate    # ticket API + scraper
```

---

## Apache

```bash
# Test config
apache2ctl configtest

# Reload (keeps connections alive)
sudo systemctl reload apache2

# Restart (drops connections)
sudo systemctl restart apache2

# Renew SSL certs
sudo certbot renew --force-renewal
sudo systemctl reload apache2

# View vhosts
apache2ctl -S

# Regenerate vhost configs from templates
source .venv/bin/activate
python3 scripts/generate_vhosts.py
```

---

## VPN

```bash
# Status
openvpn3 sessions-list

# Connect
openvpn3 session-start --config /home/tim2/1767636174601.ovpn

# Disconnect
openvpn3 session-manage --disconnect --config /home/tim2/1767636174601.ovpn

# Check tun0
ip addr show tun0

# Via RESTART.sh
sudo ./RESTART.sh vpn
```

---

## Logs

| Service | Log path |
|---------|---------|
| FULL_START | `var/logs/startup/full_start_*.log` |
| Manager API | `var/web-app-launcher/logs/webscraper_manager_api.log` |
| Manager UI | `var/web-app-launcher/logs/manager_ui_frontend.log` |
| Ticket API | `var/web-app-launcher/logs/webscraper_ticket_api.log` |
| Ticket UI | `var/web-app-launcher/logs/webscraper_ticket_ui.log` |
| Scraper Worker | `var/web-app-launcher/logs/webscraper_worker_service.log` |
| systemd (all) | `journalctl -fu freepbx-tools.service` |
| Apache | `journalctl -fu apache2` or `/var/log/apache2/` |

```bash
# Tail a specific service log
tail -f /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_manager_api.log

# Follow systemd service
journalctl -fu freepbx-tools.service

# Last 50 lines from all service logs
tail -50 /var/www/freePBX_Tools/var/web-app-launcher/logs/*.log
```

---

## Database

```bash
# Check DB health
source .venv/bin/activate
python3 scripts/db_check.py

# Direct SQLite access
sqlite3 webscraper/var/db/tickets.sqlite

# Useful queries
sqlite3 webscraper/var/db/tickets.sqlite "SELECT COUNT(*) FROM tickets;"
sqlite3 webscraper/var/db/tickets.sqlite "SELECT handle, last_updated_utc FROM handles ORDER BY last_updated_utc DESC LIMIT 20;"
sqlite3 webscraper/var/db/tickets.sqlite ".tables"
```

---

## Scraping

```bash
# Run scrape for specific handles (server mode, writes to SQLite)
source .venv-webscraper/bin/activate
python3 scripts/scrape_all_handles.py --handles KPM WS7 --timeout-seconds 180

# Validate handles input file
python3 scripts/validate_handles_csv.py webscraper/configs/handles/handles_master.txt

# Via RESTART.sh (runs worker in background)
sudo ./RESTART.sh worker
```

---

## Ingest API (Client → Server)

The server exposes `/api/ingest/*` for client POSTs. All endpoints require `X-Ingest-Key` header.

```bash
# Test ingest auth from client
curl -sf https://manager-api.123hostedtools.com/api/ingest/ping \
  -H "X-Ingest-Key: $INGEST_API_KEY"

# Health check (no auth required)
curl -sf https://manager-api.123hostedtools.com/api/health
```

---

## Git Workflow

```bash
# Normal development — work on main
git checkout main
git pull origin main
# ... make changes ...
git push origin main

# Update server and client branches from main
git checkout server && git rebase main && git push origin server --force-with-lease
git checkout client && git rebase main && git push origin client --force-with-lease
git checkout main
```

---

## FreePBX CLI Tools (Remote — Separate System)

These run on actual FreePBX PBX servers, not this server.

```bash
# SSH to FreePBX host
ssh 123net@<pbx-host-ip>
su root

# Run tools
freepbx-callflows       # interactive menu
freepbx-dump            # JSON snapshot of FreePBX DB
freepbx-diagnostic      # full system diagnostic
```

Requires: UTF-8 locale (`export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8` in `.bashrc`).
