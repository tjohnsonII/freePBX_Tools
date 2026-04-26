> **SUPERSEDED (2026-04-27):** This document describes the old Flask-based deployment web UI (`web_manager.py`) with VPBX database queries and Windows PowerShell installation. The current management interface is the **Manager UI** (Next.js, port 3004) backed by the **Manager API** (FastAPI, port 8787). See **manager-ui/README.md** and **docs/ARCHITECTURE.md**. This file is retained as historical context only.

# FreePBX Tools Manager - Web Interface — HISTORICAL

Flask + SocketIO dashboard for FreePBX tool deployments, phone config analysis, VPBX queries, and webserver diagnostics.

## Features

### Deployment Management

- Deploy freepbx-tools to one or more servers via SSH
- Server targets: single IP, comma-separated list, or a server list file (`ProductionServers.txt` / `server_ips.txt`)
- Actions: Install, Uninstall, Clean reinstall (uninstall + install)
- Real-time log streaming to the browser over WebSocket

### Phone Configuration Analyzer

- Upload a Yealink/Polycom `.cfg` file and run `phone_config_analyzer.py` against it
- Returns JSON with SIP accounts, network config, and security findings

### VPBX Database Queries

Requires `vpbx_data.db` (built by `create_vpbx_database.py`). Supported query types:

| `query_type` | Description |
| --- | --- |
| `yealink_companies` | Companies with Yealink phones (sorted by count) |
| `model_search` | Search devices by model substring |
| `vendor_stats` | Phone count grouped by vendor |
| `security_issues` | Security issues grouped by site and severity |

### Webserver Diagnostics

- HTTP health check for a configurable list of vhost URLs
- Run whitelisted Apache commands over SSH (`systemctl status apache2`, `apachectl -S`, `configtest`, `reload`, log tails)
- Check individual vhosts via `/opt/vhost-tools/check-one-vhost.sh` over SSH

### Traceroute Helper Push

Push `scripts/traceroute_server_ctl.sh` to a remote host over SSH/SFTP.

## Installation

### 1. Install Python dependencies

```powershell
pip install -r web_requirements.txt
```

Dependencies: `flask`, `flask-socketio`, `python-socketio`, `eventlet`.

For SSH-based features (deployment, webserver SSH commands, traceroute push), also install:

```powershell
pip install paramiko
```

### 2. Start the web server

From the repo root:

```powershell
python web_manager.py
```

The server listens on `http://0.0.0.0:5000`. Open `http://localhost:5000` in your browser.

## API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Dashboard UI (`templates/index.html`) |
| `GET` | `/api/servers` | List available server files (`ProductionServers.txt`, `server_ips.txt`) |
| `POST` | `/api/deploy` | Start a deployment job; returns `deployment_id` |
| `GET` | `/api/deployment/<id>` | Poll deployment status and log lines |
| `POST` | `/api/phone-config/analyze` | Upload and analyze a phone `.cfg` file |
| `POST` | `/api/vpbx/query` | Run a VPBX DB query (body: `{"query_type": "...", "params": {...}}`) |
| `POST` | `/api/traceroute/push-helper` | Push traceroute helper script to a remote host |
| `POST` | `/api/webserver/check-urls` | HTTP health check for a list of vhost URLs |
| `POST` | `/api/webserver/ssh-run` | Run a whitelisted Apache command over SSH |
| `POST` | `/api/webserver/check-one-vhost` | Run `check-one-vhost.sh` for a specific vhost |

### WebSocket events (Socket.IO)

| Event | Direction | Payload |
| --- | --- | --- |
| `log` | server → client | `{deployment_id, message}` |
| `deployment_complete` | server → client | `{deployment_id, status, error?}` |

## Security notes

- The server binds to `0.0.0.0` — restrict access with a firewall in production.
- SSH credentials are passed in the POST body over HTTP. Use an SSH tunnel or HTTPS reverse proxy in production.
- A temporary `config.py` is written to disk during deployment runs and contains credentials — it is not cleaned up automatically; do not commit it.
- SSH commands via `/api/webserver/ssh-run` are restricted to a hardcoded whitelist (`_WEBSERVER_ALLOWED_COMMANDS`).

## Troubleshooting

### Port already in use

```powershell
# Windows: find and kill the process on port 5000
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### WebSocket connection failed

- Check that `eventlet` is installed (`pip install eventlet`).
- Ensure no proxy is stripping WebSocket upgrade headers.
- Try a hard browser refresh.

### VPBX database not found

```powershell
python create_vpbx_database.py
```

### paramiko not installed (SSH features unavailable)

```powershell
pip install paramiko
```

### Deployment stuck / no logs

- Verify SSH connectivity to the target server manually.
- Check that `ProductionServers.txt` or the entered IPs are reachable.
- Review the log lines returned by `GET /api/deployment/<id>`.

## License

Part of the FreePBX Tools suite.

## Support

For issues or questions:

- Check logs in browser console (F12)
- Review server logs in terminal
- Verify all dependencies installed
