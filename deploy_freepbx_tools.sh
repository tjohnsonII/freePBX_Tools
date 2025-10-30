#!/bin/bash
# deploy_freepbx_tools.sh - Automated deployment script for FreePBX Tools

set -euo pipefail

# Configuration
SERVER="69.39.69.102"
USERNAME="123net"
USER_PASSWORD="${FREEPBX_USER_PASSWORD:-}"
ROOT_PASSWORD="${FREEPBX_ROOT_PASSWORD:-}"
LOCAL_PATH="./freepbx-tools"
REMOTE_PATH="/home/123net/freepbx-tools"

echo "🚀 FreePBX Tools Deployment Script"
echo "================================="
echo ""

# Security check - ensure passwords are provided
if [[ -z "$USER_PASSWORD" ]]; then
    echo "🔐 Enter password for 123net@$SERVER:"
    read -s USER_PASSWORD
    echo ""
fi

if [[ -z "$ROOT_PASSWORD" ]]; then
    echo "🔐 Enter root password for $SERVER:"
    read -s ROOT_PASSWORD
    echo ""
fi

# Step 1: Upload the entire freepbx-tools folder
echo "📁 Step 1: Uploading freepbx-tools folder..."
echo "   Source: $LOCAL_PATH"
echo "   Target: ${USERNAME}@${SERVER}:${REMOTE_PATH}"

if scp -r "$LOCAL_PATH" "${USERNAME}@${SERVER}:${REMOTE_PATH}"; then
    echo "   ✅ Upload completed successfully!"
else
    echo "   ❌ Upload failed!"
    exit 1
fi

echo ""

# Step 2-5: SSH and run bootstrap + install
echo "🔧 Step 2-5: SSH deployment process..."
echo "   Connecting to ${USERNAME}@${SERVER}..."

ssh "${USERNAME}@${SERVER}" << EOF
    # Change to the uploaded directory
    cd $REMOTE_PATH
    
    # Switch to root and run bootstrap + install
    echo '$ROOT_PASSWORD' | su root -c '
        cd $REMOTE_PATH
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
EOF

echo ""
echo "🎯 Deployment Summary:"
echo "====================="
echo "✅ Folder uploaded via SCP"
echo "✅ SSH connection established"  
echo "✅ Bootstrap script executed"
echo "✅ Install script executed"
echo ""
echo "🧪 Next Steps:"
echo "1. SSH into the server: ssh ${USERNAME}@${SERVER}"
echo "2. Test the menu: freepbx-callflows"
echo "3. Try call simulation: Option 11 → Option 6 & 7"
echo ""
echo "🎉 Deployment completed successfully!"