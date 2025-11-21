#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_module_status.py
------------------------
Quick FreePBX module status checker - simplified version of the full analyzer.
Shows just the enabled/disabled status of all modules.
✓ Python 3.6 compatible.

VARIABLE MAP (Key Script Variables)
-----------------------------------
args           : Parsed command-line arguments (if any)
modules        : List of module status dictionaries
stdout, stderr, rc : Output, error, and return code from fwconsole command

Key Function Arguments:
-----------------------
cmd            : Command string to pass to fwconsole
line           : Line of output from fwconsole

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    run_fwconsole_command     : Run fwconsole command and return output
    get_module_list           : Get list of all FreePBX modules and their status
    print_module_status       : Print enabled/disabled status for all modules
    main                     : CLI entry point, prints module status
"""

import subprocess, sys, re

def run_fwconsole_command(cmd):
    """Run fwconsole command and return output."""
    try:
        full_cmd = ["fwconsole"] + cmd.split()
        p = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), 1

def get_module_list():
    """Get list of all FreePBX modules using fwconsole ma list."""
    stdout, stderr, rc = run_fwconsole_command("ma list")
    if rc != 0:
        print(f"Error running fwconsole ma list: {stderr}")
        return []
    
    modules = []
    for line in stdout.split('\n'):
        # Parse fwconsole ma list output
        # Format is typically: Module Name | Version | Status | etc
        if '|' in line and not line.strip().startswith('Module'):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                module_name = parts[0]
                version = parts[1] if len(parts) > 1 else ""
                status = parts[2] if len(parts) > 2 else ""
                enabled = parts[3] if len(parts) > 3 else ""
                
                modules.append({
                    'name': module_name,
                    'version': version,
                    'status': status,
                    'enabled': enabled
                })
    
    return modules

def main():
    print("🔍 FreePBX Module Status Check")
    print("=" * 50)
    
    modules = get_module_list()
    if not modules:
        print("❌ Could not retrieve module list")
        sys.exit(1)
    
    # Categorize modules
    enabled_modules = []
    disabled_modules = []
    broken_modules = []
    
    for module in modules:
        status = module['status'].lower()
        enabled = module['enabled'].lower()
        
        if 'enabled' in status or 'enabled' in enabled:
            enabled_modules.append(module)
        elif 'disabled' in status or 'disabled' in enabled:
            disabled_modules.append(module)
        else:
            broken_modules.append(module)
    
    # Summary
    print(f"📊 Summary:")
    print(f"   Total modules: {len(modules)}")
    print(f"   Enabled: {len(enabled_modules)}")
    print(f"   Disabled: {len(disabled_modules)}")
    print(f"   Other/Unknown: {len(broken_modules)}")
    print()
    
    # Enabled modules
    if enabled_modules:
        print("✅ Enabled Modules:")
        print("-" * 30)
        for module in sorted(enabled_modules, key=lambda x: x['name']):
            print(f"  {module['name']} (v{module['version']})")
        print()
    
    # Disabled modules
    if disabled_modules:
        print("❌ Disabled Modules:")
        print("-" * 30)
        for module in sorted(disabled_modules, key=lambda x: x['name']):
            print(f"  {module['name']} (v{module['version']})")
        print()
    
    # Unknown status modules
    if broken_modules:
        print("⚠️  Unknown Status Modules:")
        print("-" * 30)
        for module in sorted(broken_modules, key=lambda x: x['name']):
            print(f"  {module['name']} (v{module['version']}) - Status: {module['status']}")
        print()
    
    # Show key system modules status
    key_modules = ['core', 'framework', 'asterisk', 'pjsip', 'chan_pjsip', 'voicemail', 'ivr', 'queues']
    key_found = [m for m in enabled_modules if any(key in m['name'].lower() for key in key_modules)]
    
    if key_found:
        print("🔑 Key System Modules (Enabled):")
        print("-" * 35)
        for module in sorted(key_found, key=lambda x: x['name']):
            print(f"  ✓ {module['name']} (v{module['version']})")
        print()
    
    print("✅ Module status check complete!")

if __name__ == "__main__":
    main()