# freepbx-deploy-backend

FastAPI backend for the FreePBX Tools deploy UI. Handles SSH/SCP-based deployment, job management, remote diagnostics, and live log streaming via WebSocket.

---

## Quick Start

```powershell
cd freepbx-deploy-backend
E:/DevTools/Python/python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn freepbx_deploy_backend.main:app --reload --host 127.0.0.1 --port 8002
```

API at **<http://127.0.0.1:8002>**. Interactive docs at **<http://127.0.0.1:8002/docs>**.

---

## API Routes

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/health` | Liveness check — returns `{ok: true}` |
| `POST` | `/api/diagnostics/summary` | Run diagnostics on a target FreePBX server via SSH (15 s default timeout) |
| `POST` | `/api/jobs` | Create and queue a new deployment job |
| `GET` | `/api/jobs` | List all jobs (sorted newest-first) |
| `GET` | `/api/jobs/{id}` | Get job details + last N log lines |
| `POST` | `/api/jobs/{id}/cancel` | Cancel a running job |
| `WS` | `/api/jobs/{id}/ws` | Stream live log output for a job |
| `POST` | `/api/remote/run` | Run an arbitrary command on a remote server via SSH |

---

## Job Actions

Passed as `action` in the `POST /api/jobs` body:

| Action | What Happens |
| ------ | ------------ |
| `deploy` | SCP scripts to server, SSH in, run `bootstrap.sh` + `install.sh` |
| `uninstall` | SSH in, run `uninstall.sh`, remove symlinks |
| `clean_deploy` | `uninstall` then `deploy` in sequence |
| `connect_only` | Test SSH connection, echo hostname |
| `upload_only` | SCP files without running any install scripts |
| `bundle` | Build `freepbx-tools-bundle.zip` locally from repo root |
| `remote_run` | Run `bundle_name` field value as a shell command on the server |

---

## Request Body — POST /api/jobs

```json
{
  "action": "clean_deploy",
  "servers": "69.39.69.102\n10.0.0.5",
  "workers": 3,
  "username": "123net",
  "password": "...",
  "root_password": "...",
  "bundle_name": "freepbx-tools-bundle.zip"
}
```

`servers` accepts newline, comma, tab, or space-separated host strings. De-duplicated automatically.

---

## WebSocket Log Streaming

Connect to `ws://localhost:8002/api/jobs/{id}/ws` immediately after creating a job. Each message is a plain-text log line. The connection closes when the job reaches a terminal state (`succeeded`, `failed`, `cancelled`).

---

## Environment Variables

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `FREEPBX_DEPLOY_UI_PYTHON` | system `python3` | Python interpreter used to run deploy scripts |
| `FREEPBX_USER` | passed per-request | SSH username forwarded to deploy scripts |
| `FREEPBX_PASSWORD` | passed per-request | SSH password forwarded to deploy scripts |
| `FREEPBX_ROOT_PASSWORD` | passed per-request | `su root` password forwarded to deploy scripts |

---

## Project Structure

```text
src/freepbx_deploy_backend/
  main.py       # FastAPI app — all routes, job runner, SSH/SCP helpers
pyproject.toml  # Package metadata, Python >=3.9
requirements.txt
```

---

## Dependencies

- `fastapi`, `uvicorn` — HTTP + WebSocket server
- `pydantic` — request body validation
- `paramiko` *(optional)* — SFTP file upload; falls back to `cat`-pipe SCP if not installed
