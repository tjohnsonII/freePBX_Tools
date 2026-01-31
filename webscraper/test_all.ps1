$ErrorActionPreference = "Stop"

$repoRoot = (Get-Location).Path
$venvPath = Join-Path $repoRoot ".venv-webscraper"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"
$requirementsPath = Join-Path $repoRoot "webscraper\requirements.txt"
$smokeTestPath = Join-Path $repoRoot "webscraper\_smoke_test.py"
$chromeDebugPort = 9222
$cookieOutputDir = Join-Path $repoRoot "webscraper\output"
$cookieOutputFile = Join-Path $cookieOutputDir "cookies_live.json"

$results = @()

function Add-Result {
    param(
        [string]$Step,
        [bool]$Passed,
        [string]$Details = ""
    )
    $status = if ($Passed) { "PASS" } else { "FAIL" }
    $results += [PSCustomObject]@{
        Step = $Step
        Status = $status
        Details = $Details
    }
}

function Invoke-Step {
    param(
        [string]$Step,
        [scriptblock]$Action
    )
    Write-Host "==> $Step"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Add-Result -Step $Step -Passed $false -Details "Exit code $LASTEXITCODE"
        return $false
    }
    Add-Result -Step $Step -Passed $true
    return $true
}

if (!(Test-Path $venvPath)) {
    Write-Host "==> Creating venv at $venvPath"
    py -3.12 -m venv $venvPath
}

if (!(Test-Path $venvActivate)) {
    Write-Host "[ERROR] Could not find venv activation script at $venvActivate"
    Add-Result -Step "venv create" -Passed $false -Details "Activation script missing"
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

. $venvActivate

$depsOk = Invoke-Step -Step "pip install" -Action {
    python -m pip install -U pip
    pip install -r $requirementsPath
}
if (-not $depsOk) {
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

$smokeOk = Invoke-Step -Step "smoke test" -Action {
    python $smokeTestPath
}
if (-not $smokeOk) {
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

$legacyOk = Invoke-Step -Step "legacy --help" -Action {
    python .\webscraper\legacy\ticket_scraper.py --help
    python .\webscraper\legacy\scrape_vpbx_tables.py --help
    python .\webscraper\legacy\extract_browser_cookies.py --help
}
if (-not $legacyOk) {
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

Write-Host "==> Checking Chrome debug port on localhost:$chromeDebugPort"
$chromeDebugUp = $false
try {
    $chromeDebugUp = Test-NetConnection -ComputerName "localhost" -Port $chromeDebugPort -InformationLevel Quiet
} catch {
    $chromeDebugUp = $false
}

if (-not $chromeDebugUp) {
    $message = "Chrome remote debugging not detected on localhost:$chromeDebugPort. Start it via webscraper/chrome_debug_setup.bat and re-run."
    Write-Host "[ACTION REQUIRED] $message"
    Add-Result -Step "chrome debug" -Passed $false -Details $message
    Write-Host "\nSummary:"
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 2
}

if (!(Test-Path $cookieOutputDir)) {
    New-Item -ItemType Directory -Path $cookieOutputDir | Out-Null
}

$cookieOk = Invoke-Step -Step "cookie capture" -Action {
    if (Test-Path $cookieOutputFile) {
        Remove-Item $cookieOutputFile -Force
    }
    python .\webscraper\chrome_cookies_live.py --output $cookieOutputFile
}
if (-not $cookieOk) {
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

$cookieExists = Test-Path $cookieOutputFile
$cookieCount = 0
if ($cookieExists) {
    $cookieJson = Get-Content $cookieOutputFile -Raw | ConvertFrom-Json
    if ($cookieJson -is [System.Array]) {
        $cookieCount = $cookieJson.Count
    } elseif ($null -ne $cookieJson) {
        $cookieCount = 1
    }
}

if (-not $cookieExists -or $cookieCount -lt 1) {
    $details = if (-not $cookieExists) { "Cookie output file not found at $cookieOutputFile" } else { "Cookie output file contained zero cookies" }
    Add-Result -Step "cookie validation" -Passed $false -Details $details
    Write-Host "\nSummary:"
    $results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }
    exit 1
}

Add-Result -Step "cookie validation" -Passed $true -Details "Cookies found: $cookieCount"

Write-Host "\nSummary:"
$results | ForEach-Object { "{0}: {1} {2}" -f $_.Step, $_.Status, $_.Details }

$failed = $results | Where-Object { $_.Status -ne "PASS" }
if ($failed.Count -gt 0) {
    exit 1
}

exit 0
