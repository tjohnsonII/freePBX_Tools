# PowerShell script to test the updated callflow validator with debug logging
# This uploads the updated file and runs a test validation

$server = "69.39.69.102"
$user = "123net" 
$keyPath = "$env:USERPROFILE\.ssh\id_rsa"

Write-Host "🔍 Testing Updated CallFlow Validator with Debug Logging" -ForegroundColor Cyan
Write-Host "=" * 60

# Upload the updated callflow validator
Write-Host "`n📤 Uploading updated callflow_validator.py..." -ForegroundColor Yellow
$localFile = "freepbx-tools\bin\callflow_validator.py"
$remoteFile = "/tmp/callflow_validator.py"

scp -i $keyPath $localFile "${user}@${server}:${remoteFile}"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to upload callflow_validator.py" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Upload successful" -ForegroundColor Green

# Test the validator with debug logging
Write-Host "`n🧪 Testing callflow validator with debug logging..." -ForegroundColor Yellow
Write-Host "Command: python3 /tmp/callflow_validator.py 2485815200 --debug" -ForegroundColor Gray

# Run the test with debug mode
$testCommand = "cd /tmp && python3 callflow_validator.py 2485815200 --debug"
$output = ssh -i $keyPath "${user}@${server}" $testCommand

Write-Host "`n📊 Test Output:" -ForegroundColor Cyan
Write-Host $output

# Check for the debug log file
Write-Host "`n📋 Checking debug log..." -ForegroundColor Yellow
$logCommand = "ls -la /tmp/callflow_validator.log && echo '--- Log Contents (last 20 lines) ---' && tail -20 /tmp/callflow_validator.log"
$logOutput = ssh -i $keyPath "${user}@${server}" $logCommand

Write-Host $logOutput

Write-Host "`n🎯 Test Complete!" -ForegroundColor Green
Write-Host "Check the output above for:" -ForegroundColor Yellow
Write-Host "  ✓ Debug logging messages" -ForegroundColor Gray  
Write-Host "  ✓ Localhost detection logic" -ForegroundColor Gray
Write-Host "  ✓ SSH vs local execution path" -ForegroundColor Gray
Write-Host "  ✓ Any error messages" -ForegroundColor Gray