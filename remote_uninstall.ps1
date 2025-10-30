#!/usr/bin/env pwsh
# remote_uninstall.ps1 - Clean uninstall FreePBX Tools from remote server

param(
    [string]$Server = "69.39.69.102",
    [string]$Username = "123net",
    [string]$UserPassword,
    [string]$RootPassword
)

Write-Host "🧹 Remote FreePBX Tools Uninstaller" -ForegroundColor Red
Write-Host "====================================" -ForegroundColor Red
Write-Host ""

# Get passwords from environment if not provided
if (-not $UserPassword) {
    if ($env:FREEPBX_USER_PASSWORD) {
        $UserPassword = $env:FREEPBX_USER_PASSWORD
        Write-Host "📋 Using 123net password from environment" -ForegroundColor Green
    } else {
        $securePassword = Read-Host "🔐 Enter password for 123net@$Server" -AsSecureString
        $UserPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    }
}

if (-not $RootPassword) {
    if ($env:FREEPBX_ROOT_PASSWORD) {
        $RootPassword = $env:FREEPBX_ROOT_PASSWORD
        Write-Host "📋 Using root password from environment" -ForegroundColor Green
    } else {
        $securePassword = Read-Host "🔐 Enter root password for $Server" -AsSecureString
        $RootPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    }
}

Write-Host "🔗 Connecting to $Server as $Username..." -ForegroundColor Yellow

# Create the uninstall command
$uninstallCommand = @"
cd /home/123net/freepbx-tools 2>/dev/null || echo 'No freepbx-tools directory found'
if [ -f ./uninstall.sh ]; then
    echo 'Running uninstall.sh...'
    echo '$RootPassword' | su root -c './uninstall.sh --yes --purge-callflows'
    echo 'Uninstall completed'
else
    echo 'No uninstall.sh found, removing manually...'
    echo '$RootPassword' | su root -c 'rm -rf /usr/local/123net/freepbx-tools /usr/local/bin/freepbx-* /usr/local/bin/asterisk-* /home/123net/callflows'
    echo 'Manual cleanup completed'
fi
cd /home/123net
rm -rf freepbx-tools
echo 'Cleanup finished'
"@

try {
    # Execute the uninstall command via SSH
    $sshArgs = @(
        "${Username}@${Server}",
        $uninstallCommand
    )
    
    Write-Host "🗑️  Removing FreePBX Tools installation..." -ForegroundColor Yellow
    
    # Use plink for SSH with password
    $env:SSH_PASSWORD = $UserPassword
    echo $UserPassword | ssh "${Username}@${Server}" $uninstallCommand
    
    Write-Host "✅ Remote uninstall completed successfully!" -ForegroundColor Green
    
} catch {
    Write-Host "❌ Error during remote uninstall: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🏁 Remote uninstall process complete!" -ForegroundColor Green
Write-Host "   Server is now clean and ready for fresh deployment" -ForegroundColor Gray