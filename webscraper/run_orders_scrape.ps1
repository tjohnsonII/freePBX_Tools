#Requires -Version 5.1
<#
.SYNOPSIS
    Client-side orders scraper launcher.
    Runs scrape_orders.py with CLIENT_MODE=1 — scrapes 123.net admin pages
    and POSTs results to the ingest server defined in .env.
#>

$ErrorActionPreference = "Stop"

$scriptDir   = $PSScriptRoot
$venvActivate = Join-Path $scriptDir ".venv-webscraper\Scripts\Activate.ps1"
$envFile      = Join-Path $scriptDir ".env"
$scraperPath  = Join-Path $scriptDir "scripts\scrape_orders.py"

# Load .env into the current process environment
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and $line -notmatch "^\s*#") {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
            }
        }
    }
} else {
    Write-Warning ".env not found at $envFile — ORDERS_123NET_USERNAME/PASSWORD must already be set"
}

if (!(Test-Path $venvActivate)) {
    Write-Error "venv not found. Run: py -3.12 -m venv .venv-webscraper && .venv-webscraper\Scripts\pip install -r src\requirements.txt"
}

. $venvActivate

Write-Host "$(Get-Date -Format 'HH:mm:ss')  Starting orders scrape (CLIENT_MODE=1 → $env:INGEST_SERVER_URL)"
python $scraperPath
$exit = $LASTEXITCODE
if ($exit -ne 0) {
    Write-Warning "Scraper exited with code $exit"
} else {
    Write-Host "$(Get-Date -Format 'HH:mm:ss')  Done."
}
exit $exit
