# web_manager.py

Legacy Flask + Flask-SocketIO dashboard for FreePBX tools management. Provides a web UI for SSH deployments, phone config analysis, VPBX database queries, and webserver health checks. Superseded by [freepbx-deploy-ui](freepbx-deploy-ui/README.md) + [freepbx-deploy-backend](freepbx-deploy-backend/README.md) for new work.

---

## Quick Start

```bash
pip install flask flask-socketio paramiko
python web_manager.py
```

Opens at **<http://localhost:5000>**.

---

## Routes

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/` | Main dashboard HTML page |
| `GET` | `/api/servers` | List configured target servers |
| `POST` | `/api/deploy` | Start a deployment job — streams logs via SocketIO |
| `GET` | `/api/deployment/{id}` | Poll deployment status by ID |
| `POST` | `/api/traceroute/push-helper` | SCP the traceroute helper script to a remote server |
| `POST` | `/api/phone-config/analyze` | Analyze a phone config file or device response |
| `POST` | `/api/vpbx/query` | Run a canned VPBX SQLite query (returns JSON rows) |
| `POST` | `/api/webserver/check-urls` | Check a list of URLs for HTTP reachability |
| `POST` | `/api/webserver/ssh-run` | SSH into a server and run a shell command |
| `POST` | `/api/webserver/check-one-vhost` | Test a single vhost for response and cert validity |

---

## Real-Time Log Streaming

Deployment jobs run in a background thread. Log lines are emitted to the frontend via SocketIO events:

- `log` — `{deployment_id, message}` — individual log line
- `deployment_complete` — `{deployment_id, status}` — terminal event

Connect from the frontend with `socket.on('log', ...)` and `socket.on('deployment_complete', ...)`.

---

## VPBX Query Types

`POST /api/vpbx/query` accepts `{query_type, params}`:

| query_type | Description |
| ---------- | ----------- |
| `extensions` | List all extensions |
| `devices` | List all devices |
| `routes` | List inbound routes |
| `did_search` | Search by DID |
| *(others)* | See source for full list |

---

## Configuration

No `.env` file. All credentials are passed per-request in the POST body:

| Field | Purpose |
| ----- | ------- |
| `servers` | Newline/comma-separated target IPs |
| `username` | SSH username (default: `123net`) |
| `password` | SSH user password |
| `root_password` | `su root` password |
| `action` | `deploy`, `uninstall`, or `redeploy` |

---

## Status

Functional but no longer the primary interface. Use [freepbx-deploy-ui](freepbx-deploy-ui/README.md) (port 3003) for deployments and [manager-ui](manager-ui/README.md) (port 3004) for scraper management.
