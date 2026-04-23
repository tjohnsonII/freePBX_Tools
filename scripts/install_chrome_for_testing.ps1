Param(
    [string]$Base = 'E:\DevTools'
)
$ErrorActionPreference = 'Stop'
$chromeDir = Join-Path $Base 'Chromium'
$driverDir = Join-Path $Base 'WebDriver'
$tmp = Join-Path $Base 'Temp'
New-Item -ItemType Directory -Force -Path $chromeDir,$driverDir,$tmp | Out-Null

$metaUrl = 'https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json'
$metaJson = Invoke-WebRequest -UseBasicParsing -Uri $metaUrl | Select-Object -ExpandProperty Content | ConvertFrom-Json
$stable = $metaJson.channels.Stable
$chromeUrl = ($stable.downloads.chrome | Where-Object { $_.platform -eq 'win64' } | Select-Object -First 1).url
$driverUrl = ($stable.downloads.chromedriver | Where-Object { $_.platform -eq 'win64' } | Select-Object -First 1).url

$czip = Join-Path $tmp 'chrome-win64.zip'
$dzip = Join-Path $tmp 'chromedriver-win64.zip'
Invoke-WebRequest -UseBasicParsing -Uri $chromeUrl -OutFile $czip
Invoke-WebRequest -UseBasicParsing -Uri $driverUrl -OutFile $dzip

$ctmp = Join-Path $tmp 'chrome'
$dtmp = Join-Path $tmp 'driver'
if (Test-Path $ctmp) { Remove-Item $ctmp -Recurse -Force }
if (Test-Path $dtmp) { Remove-Item $dtmp -Recurse -Force }
Expand-Archive -Force -Path $czip -DestinationPath $ctmp
Expand-Archive -Force -Path $dzip -DestinationPath $dtmp

$chromeExe = Get-ChildItem -Recurse -Filter chrome.exe $ctmp | Select-Object -First 1 -ExpandProperty FullName
$driverExe = Get-ChildItem -Recurse -Filter chromedriver.exe $dtmp | Select-Object -First 1 -ExpandProperty FullName
Copy-Item $chromeExe (Join-Path $chromeDir 'chrome.exe') -Force
Copy-Item $driverExe (Join-Path $driverDir 'chromedriver.exe') -Force

[Environment]::SetEnvironmentVariable('CHROME_PATH', (Join-Path $chromeDir 'chrome.exe'), 'User')
[Environment]::SetEnvironmentVariable('CHROMEDRIVER_PATH', (Join-Path $driverDir 'chromedriver.exe'), 'User')
Write-Output "Installed Chrome-for-Testing and driver to $Base"
