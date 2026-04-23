@echo off
setlocal

call "%~dp0run_py.bat" ".venv-webscraper" "webscraper\ticket_api\db_init.py" %*

exit /b %ERRORLEVEL%
