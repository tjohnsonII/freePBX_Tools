#!/usr/bin/env python3
"""
Verify FreePBX Tools deployment
"""
import paramiko

# Test server
SERVER = "69.39.69.102"
USER = "123net"
PASSWORD = "dH10oQW6jQ2rc&402B%e"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect(SERVER, username=USER, password=PASSWORD, timeout=15)
    
    # Check if tools are installed
    commands = [
        "ls -la /usr/local/123net/freepbx-tools/",
        "which freepbx-dump",
        "which freepbx-callflows",
        "freepbx-dump --help | head -5"
    ]
    
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"Running: {cmd}")
        print('='*60)
        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode()
        errors = stderr.read().decode()
        if output:
            print(output)
        if errors:
            print(f"Errors: {errors}")
    
    ssh.close()
    print("\n✅ Deployment verification complete!")
    
except Exception as e:
    print(f"❌ Error: {e}")
