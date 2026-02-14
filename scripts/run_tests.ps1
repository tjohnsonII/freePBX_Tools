$ErrorActionPreference = 'Stop'

$pythonExe = '.\.venv-webscraper\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    Write-Error "Missing virtual environment python: $pythonExe"
    exit 1
}

& $pythonExe -m pip install -U pip pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

exit 0
