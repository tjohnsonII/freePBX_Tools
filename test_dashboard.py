#!/usr/bin/env python3
"""
Test dashboard on remote server
--------------------------------
This script connects to a remote FreePBX server via SSH and runs the dashboard menu tool (freepbx-callflows).
It prints the dashboard output and any errors for verification.

====================================
Variable Map Legend (Key Variables)
====================================

host (str): IP address or hostname of the remote FreePBX server
ssh (paramiko.SSHClient): SSH client instance for remote connection
stdin, stdout, stderr: Streams returned by exec_command for command I/O
output (str): Captured standard output from the dashboard command
errors (str): Captured standard error from the dashboard command

"""

import paramiko
import sys
from config import FREEPBX_USER, FREEPBX_PASSWORD


def test_dashboard(host):
    """
    Connect to a remote FreePBX server via SSH and run the dashboard menu tool.
    Prints the dashboard output and any errors for verification.
    Args:
        host (str): IP address or hostname of the remote server.
    """
    print(f"Testing dashboard on {host}...")

    # Initialize SSH client
    ssh = paramiko.SSHClient()
    # Automatically add the server's host key (not secure for production)
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connect to the remote server using credentials from config.py
        ssh.connect(host, username=FREEPBX_USER, password=FREEPBX_PASSWORD, timeout=10)

        # Run the dashboard menu tool (freepbx-callflows) and capture output
        # 'echo "" | ...' simulates pressing Enter to show the dashboard
        # 'head -100' limits output to first 100 lines
        stdin, stdout, stderr = ssh.exec_command('echo "" | freepbx-callflows 2>&1 | head -100', timeout=30)

        # Read command output and errors
        output = stdout.read().decode('utf-8')
        errors = stderr.read().decode('utf-8')

        # Print dashboard output
        print("\n" + "="*70)
        print("Dashboard Output:")
        print("="*70)
        print(output)

        # Print any errors if present
        if errors:
            print("\n" + "="*70)
            print("Errors:")
            print("="*70)
            print(errors)

        # Close SSH connection
        ssh.close()

    except Exception as e:
        # Print error and exit if SSH or command fails
        print(f"Error: {e}")
        sys.exit(1)


# Entry point: test dashboard on a specific server IP
if __name__ == "__main__":
    test_dashboard("69.39.69.102")
