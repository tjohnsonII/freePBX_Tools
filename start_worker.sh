#!/bin/bash
cd /var/www/freePBX_Tools
pkill -f "webscraper.*headless" 2>/dev/null || true
sleep 1
export DISPLAY=:99
export WEBSCRAPER_BROWSER=chrome
export WEBSCRAPER_CHROME_PROFILE_DIR=/var/www/freePBX_Tools/webscraper/var/chrome-profile
export CHROME_USER_DATA_DIR=/var/www/freePBX_Tools/webscraper/var/chrome-profile
export WEBSCRAPER_AUTH_TIMEOUT_SEC=300
.venv-webscraper/bin/python -m webscraper --mode headless \
    >> /var/www/freePBX_Tools/var/web-app-launcher/logs/webscraper_worker_service.log 2>&1 &
echo "Worker started PID $! — connect VNC now, you have 5 minutes to log in"
