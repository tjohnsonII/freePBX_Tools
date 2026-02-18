@echo off
setlocal

set "VENV_PY=.venv-webscraper\Scripts\python.exe"
set "DB_INIT_SCRIPT=webscraper\ticket_api\db_init.py"

if exist "%VENV_PY%" (
    call "%VENV_PY%" "%DB_INIT_SCRIPT%"
) else (
    call py -3 "%DB_INIT_SCRIPT%"
)

exit /b %ERRORLEVEL%
