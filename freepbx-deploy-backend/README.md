# FreePBX Deploy UI Backend (FastAPI)

This is the backend for the FreePBX Tools deployment web UI.

## What it does
- Starts deploy/uninstall jobs by launching the existing repo scripts:
  - `deploy_freepbx_tools.py`
  - `deploy_uninstall_tools.py`
- Streams job output to the browser over WebSocket.

## Dev run (Windows)
```powershell
cd e:\DevTools\freepbx-tools\freepbx-deploy-backend
E:/DevTools/Python/python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn freepbx_deploy_backend.main:app --reload --host 127.0.0.1 --port 8002
```

## Notes
- Credentials are passed to subprocesses via environment variables:
  - `FREEPBX_USER`
  - `FREEPBX_PASSWORD`
  - `FREEPBX_ROOT_PASSWORD`
- This service is intended to run locally (binds to `127.0.0.1` by default).
