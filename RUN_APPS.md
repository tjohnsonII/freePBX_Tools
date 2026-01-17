# Run Apps (VS Code Tasks)

This repo contains multiple independent apps/tools. The easiest way to run them is via VS Code tasks.

Open the Command Palette → **Tasks: Run Task** and use the labels below.

## FreePBX Deploy Backend (FastAPI)

- Task: **FreePBX Deploy UI: backend dev (localhost:8002)**
- URL: http://127.0.0.1:8002/api/health
- Notes: This backend now also serves remote-host diagnostics at `POST /api/diagnostics/summary`.

## FreePBX Deploy UI (React/Vite)

- Task: **FreePBX Deploy UI: dev (backend + frontend)**
- UI: http://localhost:3003/

## Polycom/Yealink/Mikrotik Config App (React/Vite)

- Task: **Polycom Config App: dev**
- UI: http://localhost:3002/

## Diagnostics “stack” (backend + Polycom app)

- Task: **Start: Diagnostics Stack (backend:8002 + polycom:3002)**

## FreePBX Tools Manager Web App (Flask)

- Tasks: **FreePBX Tools Web Manager: venv create**, **FreePBX Tools Web Manager: deps install**, **FreePBX Tools Web Manager: dev (localhost:5000)**
- UI: http://localhost:5000/

## Fetch a remote FreePBX diagnostics summary

1) Start the backend:
- **Start: FreePBX Deploy Backend (localhost:8002)**

2) Set env vars (PowerShell example):
- `setx FREEPBX_DIAG_SERVER 69.39.69.102`
- `setx FREEPBX_USER 123net`
- `setx FREEPBX_PASSWORD <ssh_password>`
- `setx FREEPBX_ROOT_PASSWORD <root_password>`

3) Run the task:
- **FreePBX Diagnostics: fetch summary (env vars)**

It runs `scripts/test_diagnostics_summary.py` which calls:
- `POST http://127.0.0.1:8002/api/diagnostics/summary`

- **FreePBX Diagnostics: fetch summary (no prompt / env-only)**

It runs `scripts/test_diagnostics_summary_prompt.py --no-prompt` (no interactive prompts; uses env vars/defaults only).

- **FreePBX Diagnostics: fetch summary (prompt creds)**

It runs `scripts/test_diagnostics_summary_prompt.py` and prompts for `FREEPBX_PASSWORD` / `FREEPBX_ROOT_PASSWORD` if they are not already set.

- **FreePBX Diagnostics: fetch summary (prompt server+user+creds)**

Same as “prompt creds”, but also prompts (via VS Code Task inputs) for server, username, and timeout.

## Traceroute Visualizer (existing)

- Tasks: **Traceroute Visualizer: dev**, **Traceroute Backend (FastAPI): run (localhost:8001)**

## Remote traceroute_server_update.py (background + real-time logs)

If you have a remote host with `traceroute_server_update.py` (like the shell session you pasted) and want it running in the background while still getting live terminal output, use the helper script:

- Script: `scripts/traceroute_server_ctl.sh`
- Commands: `start`, `stop`, `restart`, `status`, `logs`, `start-follow`, `foreground`

Typical use on the remote box:

- `chmod +x traceroute_server_ctl.sh`
- `./traceroute_server_ctl.sh start` (runs `python3 -u traceroute_server_update.py` in background, logs to `traceroute_server.log`)
- `./traceroute_server_ctl.sh logs` (real-time output via `tail -F`)

Copy to the remote box (example):

- `scp scripts/traceroute_server_ctl.sh user@host:/path/with/traceroute/`
- If the remote box is very old and scp fails with `subsystem request failed`, force legacy scp protocol:
	- `scp -O scripts/traceroute_server_ctl.sh user@host:/path/with/traceroute/`
- `ssh user@host 'cd /path/with/traceroute; chmod +x traceroute_server_ctl.sh; ./traceroute_server_ctl.sh start-follow'`

## Start everything

- Task: **Start: Everything (deploy ui + polycom)**
	- Starts: Deploy UI backend+frontend + Polycom app
- Task: **Start: Everything (ALL apps)**
	- Starts: Deploy UI backend+frontend + Polycom app + Traceroute visualizer+backend + FreePBX Tools Web Manager

- Task: **Start: Everything (ALL apps + CLI manager)**
	- Starts: everything above, plus the interactive `freepbx_tools_manager.py` menu (will take over a terminal and wait for input)
