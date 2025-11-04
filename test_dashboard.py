#!/usr/bin/env python3
"""Test dashboard on remote server"""

import paramiko
import sys
from config import FREEPBX_USER, FREEPBX_PASSWORD

def test_dashboard(host):
    """SSH to server and run dashboard menu"""
    print(f"Testing dashboard on {host}...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(host, username=FREEPBX_USER, password=FREEPBX_PASSWORD, timeout=10)
        
        # Run the menu - just press Enter to see dashboard without choosing an option
        stdin, stdout, stderr = ssh.exec_command('echo "" | freepbx-callflows 2>&1 | head -100', timeout=30)
        
        output = stdout.read().decode('utf-8')
        errors = stderr.read().decode('utf-8')
        
        print("\n" + "="*70)
        print("Dashboard Output:")
        print("="*70)
        print(output)
        
        if errors:
            print("\n" + "="*70)
            print("Errors:")
            print("="*70)
            print(errors)
        
        ssh.close()
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_dashboard("69.39.69.102")
