#!/usr/bin/env python3
"""
Simple script to view the dashboard - creates SSH session for manual testing
"""

import paramiko
from config import FREEPBX_USER, FREEPBX_PASSWORD

host = "69.39.69.102"

print(f"\n✅ Dashboard has been deployed to {host}")
print(f"\n📋 To test the dashboard:")
print(f"   1. SSH to server: ssh {FREEPBX_USER}@{host}")
print(f"   2. Run command: freepbx-callflows")
print(f"   3. You'll see the dashboard with endpoint registration status!")
print(f"\n🔑 Password: {FREEPBX_PASSWORD}")
print(f"\n📊 New widget added: ENDPOINT REGISTRATIONS")
print(f"   - Shows total endpoints, registered count, unregistered count")
print(f"   - Lists first 5 endpoints with ✓/✗ status indicators")
print(f"   - Color coded: GREEN for registered, RED for unregistered")
print()
