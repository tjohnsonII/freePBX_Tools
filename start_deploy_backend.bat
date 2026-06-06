@echo off
cd /d "%~dp0"
echo Starting FreePBX Deploy Backend on localhost:8002...
set PYTHONPATH=%~dp0freepbx-deploy-backend\src
"E:\DevTools\Python\python.exe" -m uvicorn freepbx_deploy_backend.main:app --host 0.0.0.0 --port 8002
pause
