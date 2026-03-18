@echo off
setlocal EnableExtensions

if "%~1"=="" (
  echo [ensure_node_deps] ERROR: Missing app directory argument.
  exit /b 1
)

set "APP_REL=%~1"
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "APP_DIR=%REPO_ROOT%\%APP_REL%"

if not exist "%APP_DIR%\package.json" (
  echo [ensure_node_deps] ERROR: package.json not found: "%APP_DIR%\package.json"
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ensure_node_deps] ERROR: npm.cmd not found in PATH.
  exit /b 1
)

if exist "%APP_DIR%\node_modules" (
  echo [ensure_node_deps] OK: node_modules already present for %APP_REL%
  exit /b 0
)

echo [ensure_node_deps] node_modules missing for %APP_REL% - running npm install
pushd "%APP_DIR%" >nul
npm.cmd install
set "RC=%ERRORLEVEL%"
popd >nul

if not "%RC%"=="0" (
  echo [ensure_node_deps] ERROR: npm install failed for %APP_REL%
  exit /b %RC%
)

echo [ensure_node_deps] OK: npm install completed for %APP_REL%
exit /b 0
