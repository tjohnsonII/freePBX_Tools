[CmdletBinding()]
param(
    [string]$ApiHost = '127.0.0.1',
    [int]$ApiPort = 8787,
    [int]$UiPort = 3000,
    [string]$DbPath = 'webscraper\output\tickets.sqlite',
    [int]$StartupTimeoutSeconds = 45,
    [switch]$SmokeOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

function Write-Pass([string]$Message) { Write-Host "PASS  $Message" -ForegroundColor Green }
function Write-Fail([string]$Message) { Write-Host "FAIL  $Message" -ForegroundColor Red }
function Write-Info([string]$Message) { Write-Host "INFO  $Message" -ForegroundColor Cyan }

function Get-PythonCommand {
    $venvPy = Join-Path $repoRoot '.venv-webscraper\Scripts\python.exe'
    if (Test-Path $venvPy) {
        return @{ Exe = $venvPy; Prefix = @() }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Exe = 'py'; Prefix = @('-3') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Exe = 'python'; Prefix = @() }
    }
    throw 'Python executable not found (tried .venv-webscraper, py -3, python).'
}

function Invoke-CurlJson {
    param([string[]]$Args)
    $resp = & curl.exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe failed (exit $LASTEXITCODE): $($Args -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($resp)) {
        return $null
    }
    return $resp | ConvertFrom-Json
}

function Wait-ApiReady {
    param([string]$Url, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-CurlJson -Args @('--silent', '--show-error', $Url)
            if ($health.status -eq 'ok') {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }
    return $false
}

$python = Get-PythonCommand
$dbAbsolute = Join-Path $repoRoot $DbPath

Write-Info "Ensuring DB indexes for $DbPath"
& $python.Exe @($python.Prefix + @('-c', "from webscraper.ticket_api import db; db.ensure_indexes(r'$dbAbsolute'); print('indexes ensured')"))
if ($LASTEXITCODE -ne 0) { throw 'Failed to ensure DB indexes.' }
Write-Pass 'Database indexes ensured'

$apiBase = "http://$ApiHost`:$ApiPort"

if (-not $SmokeOnly) {
    Write-Info 'Starting API in a new terminal window'
    $apiCmd = "cd /d `"$repoRoot`" && `"$($python.Exe)`" $($python.Prefix -join ' ') -m webscraper.ticket_api.app --host $ApiHost --port $ApiPort --reload --db $DbPath"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/d', '/k', $apiCmd | Out-Null

    Write-Info 'Starting ticket UI in a new terminal window'
    $uiCmd = "cd /d `"$repoRoot\webscraper\ticket-ui`" && set TICKET_API_PROXY_TARGET=$apiBase && npm.cmd run dev -- --port $UiPort"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/d', '/k', $uiCmd | Out-Null
}

if (-not (Wait-ApiReady -Url "$apiBase/api/health" -TimeoutSeconds $StartupTimeoutSeconds)) {
    Write-Fail "API did not become ready at $apiBase/api/health"
    Write-Host 'Next step: verify the API window for traceback/errors.'
    exit 1
}
Write-Pass "API ready: $apiBase/api/health"

try {
    $health = Invoke-CurlJson -Args @('--silent', '--show-error', "$apiBase/api/health")
    if ($health.status -eq 'ok') { Write-Pass 'GET /api/health returned status=ok' } else { throw 'status != ok' }

    $handles = Invoke-CurlJson -Args @('--silent', '--show-error', "$apiBase/api/handles/all?limit=5")
    if ($null -ne $handles.items) { Write-Pass "GET /api/handles/all?limit=5 returned count=$($handles.count)" } else { throw 'missing items' }

    $summary = Invoke-CurlJson -Args @('--silent', '--show-error', "$apiBase/api/handles/summary?limit=5")
    if ($summary -is [System.Array] -or $summary -eq $null) {
        $summaryCount = if ($summary -eq $null) { 0 } else { $summary.Count }
        Write-Pass "GET /api/handles/summary?limit=5 returned items=$summaryCount"
    } else {
        throw 'unexpected summary payload'
    }

    $handleForScrape = $null
    if ($handles.items.Count -gt 0) {
        $handleForScrape = [string]$handles.items[0]
    }
    if ([string]::IsNullOrWhiteSpace($handleForScrape)) {
        Write-Fail 'Cannot run POST /api/scrape because no handles are available in DB.'
        Write-Host 'Next step: run a scrape/import to seed handles, then rerun this script.'
        exit 1
    }
    Write-Info "Using handle '$handleForScrape' for scrape smoke test"

    $payload = @{ handle = $handleForScrape; mode = 'latest'; limit = 5 } | ConvertTo-Json -Compress
    $scrape = Invoke-CurlJson -Args @('--silent', '--show-error', '-X', 'POST', "$apiBase/api/scrape", '-H', 'Content-Type: application/json', '-d', $payload)

    $jobId = [string]$scrape.jobId
    if ([string]::IsNullOrWhiteSpace($jobId)) {
        Write-Fail 'POST /api/scrape did not return a jobId.'
        Write-Host "Response: $($scrape | ConvertTo-Json -Depth 8 -Compress)"
        exit 1
    }
    Write-Pass "POST /api/scrape queued jobId=$jobId"

    $pollOk = $false
    for ($i = 1; $i -le 8; $i++) {
        Start-Sleep -Seconds 2
        $job = Invoke-CurlJson -Args @('--silent', '--show-error', "$apiBase/api/scrape/$jobId")
        if ($null -ne $job.status) {
            Write-Pass "GET /api/scrape/$jobId poll#$i status=$($job.status)"
            $pollOk = $true
            if ($job.status -in @('completed', 'failed')) { break }
        }
    }

    if (-not $pollOk) {
        Write-Fail "Polling never returned a status for jobId=$jobId"
        exit 1
    }

    Write-Host ''
    Write-Pass 'Ticket stack smoke test completed.'
    Write-Host "UI URL: http://127.0.0.1:$UiPort (Next.js may auto-bump to 3001+ if busy)."
    Write-Host 'If tickets are missing in UI, inspect API/UI windows and verify scraper authentication.'
} catch {
    Write-Fail $_.Exception.Message
    Write-Host 'Next step: check API/UI terminal windows, then rerun with -SmokeOnly after services are healthy.'
    exit 1
}
