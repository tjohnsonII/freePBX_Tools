@echo off
setlocal

cd /d "%~dp0\.."

echo ============================================================
echo Webscraper CMD test runner
echo Repo: %CD%
echo ============================================================

REM 1) venv + deps
if not exist .venv-webscraper\Scripts\python.exe (
  echo [INFO] Creating venv .venv-webscraper
  py -3.12 -m venv .venv-webscraper
)
echo [INFO] Upgrading pip + installing requirements
.venv-webscraper\Scripts\python.exe -m pip install -U pip
.venv-webscraper\Scripts\pip.exe install -r webscraper\requirements.txt
if errorlevel 1 goto :fail

REM 2) smoke
echo [TEST] smoke test
.venv-webscraper\Scripts\python.exe webscraper\_smoke_test.py
if errorlevel 1 goto :fail

REM 3) help checks (fast sanity)
echo [TEST] ultimate_scraper --help
.venv-webscraper\Scripts\python.exe webscraper\ultimate_scraper.py --help
if errorlevel 1 goto :fail

echo [TEST] legacy scripts --help
.venv-webscraper\Scripts\python.exe webscraper\legacy\ticket_scraper.py --help
if errorlevel 1 goto :fail
.venv-webscraper\Scripts\python.exe webscraper\legacy\scrape_vpbx_tables.py --help
if errorlevel 1 goto :fail
.venv-webscraper\Scripts\python.exe webscraper\legacy\extract_browser_cookies.py --help
if errorlevel 1 goto :fail

echo.
echo [OK] Webscraper basic tests passed.
exit /b 0

:fail
echo.
echo [FAIL] Webscraper tests failed with errorlevel %errorlevel%.
exit /b 1
