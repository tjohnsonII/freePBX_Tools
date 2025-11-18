
#!/usr/bin/env python3
"""
Simple script to view the dashboard - creates SSH session for manual testing

This script provides instructions for connecting to a FreePBX server and testing the dashboard.
It prints out the SSH command, credentials, and describes the dashboard features for manual verification.
No actual SSH connection is made; this is a helper for human testers.
"""


# Import paramiko (not used directly here, but may be used for SSH automation in future)
import paramiko
# Import FreePBX credentials from config file
from config import FREEPBX_USER, FREEPBX_PASSWORD


# The IP address of the FreePBX server where the dashboard is deployed
host = "69.39.69.102"


# Print deployment and testing instructions for the dashboard
print(f"\n✅ Dashboard has been deployed to {host}")
print(f"\n📋 To test the dashboard:")
print(f"   1. SSH to server: ssh {FREEPBX_USER}@{host}")
print(f"   2. Run command: freepbx-callflows")
print(f"   3. You'll see the dashboard with endpoint registration status!")

# Print the password for the FreePBX user
print(f"\n🔑 Password: {FREEPBX_PASSWORD}")

# Describe the new dashboard widget for endpoint registrations
print(f"\n📊 New widget added: ENDPOINT REGISTRATIONS")
print(f"   - Shows total endpoints, registered count, unregistered count")
print(f"   - Lists first 5 endpoints with ✓/✗ status indicators")
print(f"   - Color coded: GREEN for registered, RED for unregistered")
print()
