@echo off
setlocal

if not exist .venv-webscraper (
  py -3 -m venv .venv-webscraper
  if errorlevel 1 exit /b 1
)

.venv-webscraper\Scripts\python.exe -m pip install -U pip
if errorlevel 1 exit /b 1
.venv-webscraper\Scripts\pip.exe install -r webscraper\requirements.txt
if errorlevel 1 exit /b 1

.venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py
if errorlevel 1 exit /b 1
.venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help
if errorlevel 1 exit /b 1
.venv-webscraper\Scripts\python.exe webscraper\legacy\ticket_scraper.py --help
if errorlevel 1 exit /b 1
.venv-webscraper\Scripts\python.exe webscraper\legacy\scrape_vpbx_tables.py --help
if errorlevel 1 exit /b 1

if "%WEBSCRAPER_LIVE_COOKIES%"=="1" (
  call webscraper\chrome_debug_setup.bat
  if errorlevel 1 exit /b 1
  .venv-webscraper\Scripts\python.exe webscraper\chrome_cookies_live.py
  if errorlevel 1 exit /b 1
)

echo Webscraper cmd smoke checks completed.
