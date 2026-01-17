param(
  [string]$Server = $env:FREEPBX_DIAG_SERVER,
  [string]$Username = $env:FREEPBX_USER,
  [string]$Password = $env:FREEPBX_PASSWORD,
  [string]$RootPassword = $env:FREEPBX_ROOT_PASSWORD,
  [double]$TimeoutSeconds = $(if ($env:FREEPBX_DIAG_TIMEOUT_SECONDS) { [double]$env:FREEPBX_DIAG_TIMEOUT_SECONDS } else { 20 })
)

if (-not $Server) { $Server = "69.39.69.102" }
if (-not $Username) { $Username = "123net" }

$uri = "http://127.0.0.1:8002/api/diagnostics/summary"

$body = @{
  server          = $Server
  username        = $Username
  password        = $Password
  root_password   = $RootPassword
  timeout_seconds = $TimeoutSeconds
} | ConvertTo-Json

Write-Host "POST $uri" -ForegroundColor Cyan
Write-Host "server=$Server username=$Username timeout_seconds=$TimeoutSeconds" -ForegroundColor DarkGray

try {
  $resp = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body
  $resp | ConvertTo-Json -Depth 10
}
catch {
  Write-Host "Request failed: $($_.Exception.Message)" -ForegroundColor Red
  if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
    Write-Host $_.ErrorDetails.Message -ForegroundColor DarkRed
  }
  exit 1
}
