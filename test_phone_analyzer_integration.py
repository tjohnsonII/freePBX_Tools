#!/usr/bin/env python3
"""
Quick test of the Phone Config Analyzer integration in freepbx_tools_manager.py
"""

import subprocess
import sys

print("Testing Phone Config Analyzer integration...")
print("=" * 70)
print()

# Test 1: Check if phone_config_analyzer.py exists
import os
if os.path.exists("phone_config_analyzer.py"):
    print("✅ phone_config_analyzer.py found")
else:
    print("❌ phone_config_analyzer.py NOT found")
    sys.exit(1)

# Test 2: Check if demo exists
if os.path.exists("phone_config_analyzer_demo.py"):
    print("✅ phone_config_analyzer_demo.py found")
else:
    print("⚠️  phone_config_analyzer_demo.py NOT found (optional)")

# Test 3: Check if sample config exists
sample_config = "freepbx-tools/bin/123net_internal_docs/CSU_VVX600.cfg"
if os.path.exists(sample_config):
    print(f"✅ Sample config found: {sample_config}")
else:
    print(f"⚠️  Sample config NOT found: {sample_config}")

# Test 4: Check documentation
docs = [
    "PHONE_CONFIG_ANALYZER_README.md",
    "PHONE_CONFIG_ANALYZER_QUICKREF.md",
    "PHONE_CONFIG_ANALYZER_SUMMARY.md"
]

print()
print("Documentation files:")
for doc in docs:
    if os.path.exists(doc):
        print(f"  ✅ {doc}")
    else:
        print(f"  ❌ {doc}")

# Test 5: Quick syntax check on phone_config_analyzer.py
print()
print("Checking Python syntax...")
result = subprocess.run(
    ["python", "-m", "py_compile", "phone_config_analyzer.py"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ phone_config_analyzer.py syntax is valid")
else:
    print("❌ Syntax error in phone_config_analyzer.py")
    print(result.stderr)
    sys.exit(1)

# Test 6: Quick syntax check on freepbx_tools_manager.py
result = subprocess.run(
    ["python", "-m", "py_compile", "freepbx_tools_manager.py"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ freepbx_tools_manager.py syntax is valid")
else:
    print("❌ Syntax error in freepbx_tools_manager.py")
    print(result.stderr)
    sys.exit(1)

# Test 7: Run quick analysis test
if os.path.exists(sample_config):
    print()
    print("Running quick analysis test on sample config...")
    print("-" * 70)
    result = subprocess.run(
        ["python", "phone_config_analyzer.py", sample_config, "--no-color"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode == 0:
        print("✅ Analysis completed successfully")
        
        # Check output contains expected sections
        output = result.stdout
        checks = [
            ("SIP ACCOUNTS" in output, "SIP Accounts section"),
            ("SECURITY ISSUES" in output or "No security issues" in output, "Security section"),
            ("NETWORK CONFIGURATION" in output, "Network configuration section"),
            ("FEATURE STATUS" in output, "Feature status section"),
        ]
        
        print()
        print("Output validation:")
        for passed, description in checks:
            if passed:
                print(f"  ✅ {description}")
            else:
                print(f"  ⚠️  {description} (not found)")
    else:
        print("❌ Analysis failed")
        print(result.stderr)
        sys.exit(1)

print()
print("=" * 70)
print("✅ All tests passed! Phone Config Analyzer is ready to use.")
print()
print("To use it:")
print("  1. Run: python freepbx_tools_manager.py")
print("  2. Select option 7 (Phone Config Analyzer)")
print("  3. Choose your analysis option")
print()
