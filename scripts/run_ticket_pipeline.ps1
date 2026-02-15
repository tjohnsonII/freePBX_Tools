param(
    [string[]]$Handles,
    [string]$HandlesFile,
    [int]$MaxHandles = 0,
    [switch]$Show
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv-webscraper\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing python venv at $python" }

$dbPath = Join-Path $RepoRoot "webscraper\output\tickets.sqlite"
$outPath = Join-Path $RepoRoot "webscraper\output\scrape_runs"
$env:TICKETS_DB = $dbPath

$scrapeArgs = @("scripts\scrape_all_handles.py", "--db", $dbPath, "--out", $outPath, "--auth-profile-only")
if ($Handles -and $Handles.Count -gt 0) {
    $scrapeArgs += "--handles"
    $scrapeArgs += $Handles
} elseif ($HandlesFile) {
    $scrapeArgs += @("--handles-file", $HandlesFile)
}
if ($MaxHandles -gt 0) {
    $scrapeArgs += @("--max-handles", "$MaxHandles")
}
if ($Show.IsPresent) { $scrapeArgs += "--show" }

Write-Host "[PIPELINE] Scraping handles..."
& $python @scrapeArgs

Write-Host "[PIPELINE] Starting API..."
$apiCmd = "cd `"$RepoRoot`"; `$env:TICKETS_DB=`"$dbPath`"; & `"$python`" -m uvicorn webscraper.ticket_api.app:app --reload --port 8787"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null

Write-Host "[PIPELINE] Starting UI..."
$uiDir = Join-Path $RepoRoot "webscraper\ticket-ui"
$npmProgramFiles = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
$npm = if (Test-Path $npmProgramFiles) { $npmProgramFiles } else { "npm.cmd" }
$uiCmd = "cd `"$uiDir`"; `$env:NEXT_PUBLIC_TICKET_API_BASE=`"http://127.0.0.1:8787`"; & `"$npm`" install; & `"$npm`" run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $uiCmd | Out-Null

Start-Sleep -Seconds 4
Start-Process "http://localhost:3000" | Out-Null

Write-Host "[PIPELINE] DB quick stats"
& $python -c "import os,sqlite3;db=os.environ.get('TICKETS_DB');conn=sqlite3.connect(db);print('handles=',conn.execute('select count(*) from handles').fetchone()[0]);print('tickets=',conn.execute('select count(*) from tickets').fetchone()[0]);print('runs=',conn.execute('select count(*) from runs').fetchone()[0])"
Write-Host "[PIPELINE] If PowerShell blocks npm.ps1, this script uses npm.cmd directly."
