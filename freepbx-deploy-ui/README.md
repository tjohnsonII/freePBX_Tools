# freepbx-deploy-ui

React + Vite frontend for deploying and managing FreePBX tools across remote servers. Pairs with [freepbx-deploy-backend](../freepbx-deploy-backend/README.md) (FastAPI, port 8002).

---

## Quick Start

```powershell
cd freepbx-deploy-ui
npm install
npm run dev
```

Opens at **<http://localhost:3003>** (port hardcoded in `vite.config.ts`, `strictPort: true`).

The dev server proxies all `/api` requests to `http://127.0.0.1:8002` — start the backend first.

---

## What It Does

Single-page UI for orchestrating FreePBX tool deployments over SSH/SCP:

| Action | Description |
| ------ | ----------- |
| `deploy` | Upload scripts and run full install on target servers |
| `uninstall` | Remove installed tools from target servers |
| `clean_deploy` | Uninstall then re-deploy in one pass |
| `connect_only` | Test SSH connectivity without deploying |
| `upload_only` | SCP files without running install |
| `bundle` | Build a local zip bundle of all tools |
| `remote_run` | Run an arbitrary remote command via SSH |

Jobs run asynchronously. The UI streams live log output via WebSocket (`/api/jobs/{id}/ws`) and polls for job status every 4 seconds.

---

## Configuration

All settings are entered in-browser — no `.env` file needed for the UI itself.

| Field | Default | Notes |
| ----- | ------- | ----- |
| Action | `clean_deploy` | Drop-down of the 7 actions above |
| Servers | `69.39.69.102` | Newline or comma-separated host IPs |
| Workers | `1` | Parallel SSH workers (1–50) |
| Username | `123net` | SSH username |
| Password | — | SSH user password |
| Root Password | — | `su root` password |
| Bundle Name | `freepbx-tools-bundle.zip` | Only used by `bundle` action |

---

## Project Structure

```text
src/
  App.tsx      # Single-page UI — action picker, server list, job list, log panel
  api.ts       # Typed wrappers for all backend fetch/WebSocket calls
  types.ts     # Action, JobInfo, and other shared TypeScript types
  styles.css   # Global styles
  main.tsx     # React entry point
```

---

## Backend Dependency

This UI is a thin shell. All logic lives in [freepbx-deploy-backend](../freepbx-deploy-backend/README.md).

Start the backend before the UI:

```powershell
cd freepbx-deploy-backend
.venv\Scripts\activate
uvicorn src.freepbx_deploy_backend.main:app --port 8002 --reload
```

---

## Build

```bash
npm run build     # outputs to dist/
npm run preview   # preview production build locally
```
