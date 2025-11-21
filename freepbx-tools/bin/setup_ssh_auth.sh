#!/bin/bash

# SSH Key Setup for FreePBX Call Simulation
# Sets up passwordless SSH authentication for testing
#
# VARIABLE MAP (Key Script Variables)
# -----------------------------------
# SERVER_IP      : Target FreePBX server IP address
# SSH_USER       : SSH username for remote server access
# SERVER_PASSWORD: SSH password (from env or prompt)
# GREEN, BLUE, YELLOW, RED, NC : ANSI color codes for output
#
# FUNCTION MAP (Major Script Sections)
# ------------------------------------
# (main script body) : Checks for SSH key, generates if needed, copies key to server, verifies auth
#

set -euo pipefail

SERVER_IP="69.39.69.102"
SSH_USER="123net"
SERVER_PASSWORD="${SSH_SERVER_PASSWORD:-}"

# Security check - ensure password is provided
if [[ -z "$SERVER_PASSWORD" ]]; then
    echo "🔐 Enter SSH password for $SSH_USER@$SERVER_IP:"
    read -s SERVER_PASSWORD
    echo ""
fi

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🔐 SSH KEY SETUP FOR FREEPBX SERVER${NC}"
echo "=================================="
echo "Server: $SERVER_IP"
echo "User: $SSH_USER"
echo ""

# Check if SSH key exists
if [ ! -f ~/.ssh/id_rsa ]; then
    echo -e "${YELLOW}📝 No SSH key found, generating new key...${NC}"
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N "" -C "freepbx-testing-$(whoami)@$(hostname)"
    echo -e "${GREEN}✅ SSH key generated${NC}"
else
    echo -e "${GREEN}✅ SSH key already exists${NC}"
fi

# Check if we can already connect without password
echo -e "\n${BLUE}🔍 Testing current SSH connectivity...${NC}"
if ssh -o ConnectTimeout=10 -o BatchMode=yes "$SSH_USER@$SERVER_IP" "echo 'SSH key auth working'" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ SSH key authentication already working!${NC}"
    echo "No setup needed - you can proceed with testing."
    exit 0
fi

# Need to copy SSH key using password
echo -e "${YELLOW}🔑 Need to set up SSH key authentication${NC}"
echo "This will copy your public key to the server for passwordless access."
echo ""

# Check if sshpass is available for automated key copying
if command -v sshpass >/dev/null 2>&1; then
    echo -e "${BLUE}📤 Copying SSH key using sshpass...${NC}"
    
    # Copy the public key
    sshpass -p "$SERVER_PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ SSH key copied successfully${NC}"
    else
        echo -e "${RED}❌ Failed to copy SSH key${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  sshpass not available - manual setup required${NC}"
    echo ""
    echo "Please run this command manually and enter the password when prompted:"
    echo "ssh-copy-id $SSH_USER@$SERVER_IP"
    echo ""
    echo "Password: $SERVER_PASSWORD"
    echo ""
    echo "After copying the key, re-run this script to verify setup."
    exit 1
fi

# Verify SSH key authentication works
echo -e "\n${BLUE}🧪 Testing SSH key authentication...${NC}"
if ssh -o ConnectTimeout=10 -o BatchMode=yes "$SSH_USER@$SERVER_IP" "echo 'SSH key auth successful'" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ SSH key authentication working perfectly!${NC}"
else
    echo -e "${RED}❌ SSH key authentication failed${NC}"
    echo "You may need to manually copy the key or check server configuration."
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 SSH SETUP COMPLETE!${NC}"
echo "You can now run the call simulation tools without entering passwords."
echo ""
echo "Next steps:"
echo "1. Deploy the FreePBX tools suite:"
echo "   ./deploy_freepbx_tools.ps1  (from Windows)"
echo "   ./deploy_freepbx_tools.sh   (from Linux/WSL)"
echo ""
echo "2. Test a call simulation:"
echo "   ssh $SSH_USER@$SERVER_IP"
echo "   freepbx-simulate-calls test-playback zombies"