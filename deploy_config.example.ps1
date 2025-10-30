# deploy_config.example.ps1 - Example configuration for deployment
# Copy this to deploy_config.ps1 and fill in your values
# deploy_config.ps1 is ignored by git for security

# Server configuration
$DeployServer = "your.server.ip.here"
$DeployUsername = "your-username"

# Environment variable setup for passwords
# Set these in your PowerShell profile or session:
# $env:FREEPBX_USER_PASSWORD = "your-123net-user-password"
# $env:FREEPBX_ROOT_PASSWORD = "***REMOVED***"

# Authentication flow:
# 1. SSH connects with 123net user password
# 2. Then switches to root with 'su root' command
# 3. Root password is used for su command

# Alternative: Use SSH keys instead of passwords
# See README.md for SSH key setup instructions