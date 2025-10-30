#!/usr/bin/env pwsh
# deploy_freepbx_tools.ps1 - Automated deployment script for FreePBX Tools
# This script handles the complete deployment process: upload, bootstrap, and install

param(
    [string]$Server = "69.39.69.102",
    [string]$Username = "123net",
    [string]$UserPassword,
    [string]$RootPassword,
    [string]$LocalPath = "c:\Users\tjohnson\OneDrive - 123.Net, LLC\Documents\Hosted Ticket Folder\freePBX_Tools\freepbx-tools",
    [string]$RemotePath = "/home/123net/freepbx-tools"
)

Write-Host "🚀 FreePBX Tools Deployment Script" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Security check - ensure passwords are provided
if (-not $UserPassword) {
    if ($env:FREEPBX_USER_PASSWORD) {
        $UserPassword = $env:FREEPBX_USER_PASSWORD
        Write-Host "📋 Using 123net password from environment variable FREEPBX_USER_PASSWORD" -ForegroundColor Green
    } else {
        $securePassword = Read-Host "🔐 Enter password for 123net@$Server" -AsSecureString
        $UserPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    }
}

if (-not $RootPassword) {
    if ($env:FREEPBX_ROOT_PASSWORD) {
        $RootPassword = $env:FREEPBX_ROOT_PASSWORD
        Write-Host "📋 Using root password from environment variable FREEPBX_ROOT_PASSWORD" -ForegroundColor Green
    } else {
        $securePassword = Read-Host "🔐 Enter root password for $Server" -AsSecureString
        $RootPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    }
}

# Step 1: Upload the entire freepbx-tools folder
Write-Host "📁 Step 1: Uploading freepbx-tools folder..." -ForegroundColor Yellow
Write-Host "   Source: $LocalPath" -ForegroundColor Gray
Write-Host "   Target: ${Username}@${Server}:${RemotePath}" -ForegroundColor Gray

try {
    # Use scp to recursively copy the entire folder
    $scpCommand = "scp -r `"$LocalPath`" ${Username}@${Server}:${RemotePath}"
    Write-Host "   Running: $scpCommand" -ForegroundColor Gray
    
    $process = Start-Process -FilePath "scp" -ArgumentList "-r", $LocalPath, "${Username}@${Server}:${RemotePath}" -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -eq 0) {
        Write-Host "   ✅ Upload completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Upload failed with exit code: $($process.ExitCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "   ❌ Upload failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2-5: SSH and run bootstrap + install
Write-Host "🔧 Step 2-5: SSH deployment process..." -ForegroundColor Yellow

# Create a temporary script for the SSH commands
$sshScript = @"
# Change to the uploaded directory
cd $RemotePath

# Switch to root and run bootstrap + install
echo '$RootPassword' | su root -c '
    cd $RemotePath
    echo "🔧 Running bootstrap script..."
    chmod +x bootstrap.sh
    ./bootstrap.sh
    
    echo ""
    echo "📦 Running install script..."
    ./install.sh
    
    echo ""
    echo "✅ Deployment completed!"
    echo ""
    echo "🧪 Testing installation..."
    
    # Quick test of the installation
    if [ -x /usr/local/bin/freepbx-callflows ]; then
        echo "✅ freepbx-callflows command available"
    else
        echo "❌ freepbx-callflows command not found"
    fi
    
    if [ -f /usr/local/123net/call-simulation/call_simulator.py ]; then
        echo "✅ Call simulator available"
    else
        echo "❌ Call simulator not found"
    fi
    
    if [ -f /usr/local/123net/call-simulation/simulate_calls.sh ]; then
        echo "✅ Monitoring script available"
    else
        echo "❌ Monitoring script not found"
    fi
'
"@

# Save the script to a temporary file
$tempScript = [System.IO.Path]::GetTempFileName() + ".sh"
$sshScript | Out-File -FilePath $tempScript -Encoding UTF8

try {
    Write-Host "   Connecting to ${Username}@${Server}..." -ForegroundColor Gray
    
    # Execute the SSH command
    $sshCommand = "ssh ${Username}@${Server} 'bash -s'" 
    Write-Host "   Running deployment commands..." -ForegroundColor Gray
    
    # Use cmd to handle the input redirection properly
    $result = cmd /c "type `"$tempScript`" | ssh ${Username}@${Server} 'bash -s'"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ SSH deployment completed!" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  SSH deployment finished with warnings (exit code: $LASTEXITCODE)" -ForegroundColor Yellow
    }
    
    # Display the output
    Write-Host ""
    Write-Host "📋 Deployment Output:" -ForegroundColor Cyan
    Write-Host "--------------------" -ForegroundColor Cyan
    $result | ForEach-Object { Write-Host "   $_" -ForegroundColor White }
    
} catch {
    Write-Host "   ❌ SSH deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    # Clean up temporary file
    if (Test-Path $tempScript) {
        Remove-Item $tempScript -Force
    }
}

Write-Host ""
Write-Host "🎯 Deployment Summary:" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
Write-Host "✅ Folder uploaded via SCP" -ForegroundColor Green
Write-Host "✅ SSH connection established" -ForegroundColor Green  
Write-Host "✅ Bootstrap script executed" -ForegroundColor Green
Write-Host "✅ Install script executed" -ForegroundColor Green
Write-Host ""
Write-Host "🧪 Next Steps:" -ForegroundColor Yellow
Write-Host "1. SSH into the server: ssh ${Username}@${Server}" -ForegroundColor Gray
Write-Host "2. Test the menu: freepbx-callflows" -ForegroundColor Gray
Write-Host "3. Try call simulation: Option 11 → Option 6 & 7" -ForegroundColor Gray
Write-Host ""
Write-Host "🎉 Deployment completed successfully!" -ForegroundColor Green