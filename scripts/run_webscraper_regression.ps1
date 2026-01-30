$ErrorActionPreference = "Stop"

function Fail($message) {
  Write-Host "FAIL: $message" -ForegroundColor Red
  exit 1
}

function Pass($message) {
  Write-Host "PASS: $message" -ForegroundColor Green
}

try {
  Write-Host "Running argparse help checks..."
  python .\webscraper\legacy\ticket_scraper.py --help | Out-Null
  python .\webscraper\legacy\scrape_vpbx_tables.py --help | Out-Null
  Pass "Argparse help checks"

  $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
  $cookieDir = Join-Path $tempRoot "cookies"
  New-Item -ItemType Directory -Path $cookieDir | Out-Null

  $cookiesTxt = Join-Path $cookieDir "cookies.txt"
  @"
# Netscape HTTP Cookie File
.123.net\tTRUE\t/\tFALSE\t0\tPHPSESSID\tDUMMY
"@ | Set-Content -Path $cookiesTxt -Encoding ASCII

  Push-Location $cookieDir
  python (Join-Path $repoRoot "webscraper\\legacy\\convert_cookies.py") | Out-Null
  Pop-Location

  $cookiesJson = Join-Path $cookieDir "cookies.json"
  if (-not (Test-Path $cookiesJson)) {
    Fail "convert_cookies.py did not create cookies.json"
  }
  Pass "Cookie conversion test"

  $seleniumDir = Join-Path $tempRoot "selenium"
  $inputDir = Join-Path $seleniumDir "input"
  $outputDir = Join-Path $seleniumDir "output"
  New-Item -ItemType Directory -Path $inputDir | Out-Null
  New-Item -ItemType Directory -Path $outputDir | Out-Null

  $fixturePath = Join-Path $inputDir "scrape_results_TEST.json"
  @'
{"ticket_details":[{"id":"123","subject":"Test","status":"Open","priority":"Low","created_date":"2024-01-01","messages":[]}]} 
'@ | Set-Content -Path $fixturePath -Encoding UTF8

  python .\webscraper\legacy\selenium_to_kb.py --input-dir $inputDir --out-dir $outputDir | Out-Null

  $dbPath = Join-Path $outputDir "TEST_tickets.db"
  $jsonPath = Join-Path $outputDir "TEST_tickets.json"
  if (-not (Test-Path $dbPath)) {
    Fail "selenium_to_kb.py did not create TEST_tickets.db"
  }
  if (-not (Test-Path $jsonPath)) {
    Fail "selenium_to_kb.py did not create TEST_tickets.json"
  }
  Pass "Selenium-to-KB parse-only test"

  Pass "All regression checks"
  exit 0
} catch {
  Fail $_.Exception.Message
}
