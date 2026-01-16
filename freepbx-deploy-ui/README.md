# FreePBX Tools Deploy UI (React/Vite)

Frontend for running deployments/uninstalls against FreePBX servers.

## Dev run
```powershell
cd e:\DevTools\freepbx-tools\freepbx-deploy-ui
npm install
npm run dev
```

Backend must be running at `http://127.0.0.1:8002`.

## Notes
- This UI calls the backend endpoints under `/api/*` (proxied by Vite).
- Credentials are sent to the backend per-run and passed to deploy scripts via environment variables.
