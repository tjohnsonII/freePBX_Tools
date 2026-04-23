# VS Code Debug Guide (Windows + cmd.exe)

This workspace now separates **normal dev running** from **debug runs**:

- **Normal runner:** `Start Everything + CLI` task (no debugger attached)
- **Debug runner:** launch configs in `.vscode/launch.json` (F5)

## 1) Run everything normally (no debugger)

1. Press `Ctrl+Shift+B`.
2. Select **Start Everything + CLI**.
3. This starts background services in parallel, including:
   - `webscraper:ticket-api`
   - `webscraper:ticket-ui`
   - `webscraper:dev`
4. Use this for regular development when breakpoints are not required.

## 2) Debug Ticket API with breakpoints

1. Open **Run and Debug** (`Ctrl+Shift+D`).
2. Select **Ticket API (Debug)**.
3. Press `F5`.
4. Set breakpoints in Python files (for example under `webscraper/ticket_api/`).
5. Requests to `http://127.0.0.1:8787` should hit breakpoints.

Notes:
- This config runs `uvicorn` without `--reload` to keep debugger behavior stable.
- It uses `.venv-webscraper\Scripts\python.exe` when available; otherwise `py -3`.

## 3) Attach to debugpy

1. Select **Ticket API (Attach - debugpy)**.
2. Press `F5`.
3. VS Code starts `webscraper:ticket-api (debugpy)`:
   - `python -m debugpy --listen 5678 --wait-for-client -m uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8787`
4. VS Code attaches to port `5678` and breakpoints activate after attach.

## 4) Debug Next.js fetch calls in Edge

Use one of these launch configs and press `F5`:

- **Ticket UI (Next Dev + Edge)**
- **Traceroute Visualizer (Next Dev + Edge)**

This launches Microsoft Edge with the JS debugger attached.

Tips:
- Put breakpoints in client code and API route handlers.
- Use Edge DevTools Network tab to inspect fetch/XHR requests.
- Keep backend/API tasks running for end-to-end calls.

## 5) Debug background scrape jobs

Use Python launch configs:

- **Webscraper Ultimate Scraper (Debug)**
- **FreePBX Tools Manager CLI (Debug)**

Set breakpoints in long-running loops and inspect local variables/watch expressions.

## Troubleshooting

### Port already in use

Symptoms: task fails to bind on `3000`, `5173`, `5174`, `8002`, or `8787`.

Kill port manually in `cmd.exe`:

```bat
for /f "tokens=5" %A in ('netstat -ano ^| findstr :8787 ^| findstr LISTENING') do taskkill /F /PID %A
```

(Replace `8787` with the port you need.)

### `npm.ps1` blocked

If PowerShell blocks npm scripts, use `npm.cmd`.

All debug tasks in this workspace already call `npm.cmd` for Windows compatibility.

### PowerShell execution policy warnings

Preferred approach in this workspace: use `cmd.exe` tasks with `npm.cmd`.

If you must use PowerShell, adjust policy in an elevated shell as needed (organization policy permitting):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Debugger does not attach to Ticket API

- Confirm port `5678` is listening for debugpy attach mode.
- Ensure only one Ticket API process is running.
- Restart the `webscraper:ticket-api (debugpy)` task, then start attach config again.
