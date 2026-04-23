# 🔒 Security Guidelines for FreePBX Tools

## Password Management

### ⚠️ NEVER commit passwords to Git!

### Safe Usage Options:

#### Option 1: Environment Variables (Recommended)
```powershell
# Set environment variables (PowerShell)
$env:FREEPBX_USER_PASSWORD = "your-123net-password"
$env:FREEPBX_ROOT_PASSWORD = "***REMOVED***"
.\deploy_freepbx_tools.ps1
```

```bash
# Set environment variables (Bash)
export FREEPBX_USER_PASSWORD="your-123net-password"
export FREEPBX_ROOT_PASSWORD = "***REMOVED***"
./deploy_freepbx_tools.sh
```

#### Option 2: Command Line Parameters
```powershell
.\deploy_freepbx_tools.ps1 -UserPassword "your-123net-password" -RootPassword "your-root-password"
```

#### Option 3: Interactive Prompt (Most Secure)
```powershell
# Just run without password - will prompt securely
.\deploy_freepbx_tools.ps1
```

## SSH Key Authentication (Best Practice)

Instead of passwords, set up SSH key authentication:

```bash
# Generate SSH key pair
ssh-keygen -t rsa -b 4096 -C "your-email@domain.com"

# Copy public key to server
ssh-copy-id username@server-ip

# Test passwordless login
ssh username@server-ip
```

## Files Protected by .gitignore

- `deploy_config.ps1` - Local configuration
- `ProductionServers.txt` - Server lists
- `*.key`, `*.pem` - SSH keys
- `*password*`, `*secret*` - Any files with sensitive data

## Security Checklist

- [ ] No passwords in code
- [ ] .gitignore includes sensitive patterns
- [ ] Environment variables used for secrets
- [ ] SSH keys preferred over passwords
- [ ] Production server lists not committed
- [ ] Regular security review of repository

## If You Accidentally Commit Sensitive Data

1. **Immediately** change the exposed passwords
2. Remove from Git history:
   ```bash
   git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch path/to/sensitive/file' --prune-empty --tag-name-filter cat -- --all
   git push origin --force --all
   ```
3. Contact affected systems administrators
4. Review and update security practices