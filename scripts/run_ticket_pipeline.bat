@echo off
setlocal
cd /d %~dp0\..

python scripts\run_ticket_pipeline.py %*

endlocal
