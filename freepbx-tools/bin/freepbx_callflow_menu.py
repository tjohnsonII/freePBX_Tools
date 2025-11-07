#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_callflow_menu.py
Menu-driven wrapper to:
  1) snapshot FreePBX data -> JSON (via freepbx_dump.py)
  2) render SVG call-flow(s) for selected or all DIDs (via freepbx_callflow_graph.py)
Python 3.6 safe. No external modules.
"""

import json, os, sys, subprocess, time, shutil, re

# ANSI Color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BG_BLUE = '\033[44m'
    BG_CYAN = '\033[46m'


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(text):
    """Return the printable length of a string that may contain ANSI codes."""
    if not text:
        return 0
    return len(ANSI_ESCAPE_RE.sub('', text))


def pad_ansi(text, width, align='left'):
    """Pad ANSI-colored text to a target width without breaking alignment."""
    if text is None:
        text = ''

    length = visible_len(text)
    if length >= width:
        return text

    pad = width - length
    if align == 'left':
        return text + ' ' * pad
    if align == 'right':
        return ' ' * pad + text
    if align == 'center':
        left = pad // 2
        right = pad - left
        return ' ' * left + text + ' ' * right
    raise ValueError(f"Unsupported alignment: {align}")

DUMP_SCRIPT   = "/usr/local/bin/freepbx_dump.py"
GRAPH_SCRIPT  = "/usr/local/bin/freepbx_callflow_graph.py"
OUT_DIR       = "/home/123net/callflows"
DUMP_PATH     = os.path.join(OUT_DIR, "freepbx_dump.json")
DB_USER       = "root"
DEFAULT_SOCK  = "/var/lib/mysql/mysql.sock"
TC_STATUS_SCRIPT = "/usr/local/bin/freepbx_tc_status.py"
MODULE_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_module_analyzer.py"
PAGING_FAX_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_paging_fax_analyzer.py"
COMPREHENSIVE_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_comprehensive_analyzer.py"
ASCII_CALLFLOW_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py"
CALL_SIMULATOR_SCRIPT = "/usr/local/123net/call-simulation/call_simulator.py"
CALLFLOW_VALIDATOR_SCRIPT = "/usr/local/123net/call-simulation/callflow_validator.py"
SIMULATE_CALLS_SCRIPT = "/usr/local/123net/call-simulation/simulate_calls.sh"


def run_tc_status(sock):
    """Invoke the time-condition status tool."""
    if not os.path.isfile(TC_STATUS_SCRIPT):
        print("Time Condition status tool not found at", TC_STATUS_SCRIPT)
        return
    rc, out, err = run(["python3", TC_STATUS_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()


def run_module_analyzer(sock):
    """Invoke the FreePBX module analyzer tool."""
    if not os.path.isfile(MODULE_ANALYZER_SCRIPT):
        print("Module analyzer tool not found at", MODULE_ANALYZER_SCRIPT)
        return
    rc, out, err = run(["python3", MODULE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()


def run_paging_fax_analyzer(sock):
    """Invoke the FreePBX paging/fax analyzer tool."""
    if not os.path.isfile(PAGING_FAX_ANALYZER_SCRIPT):
        print("Paging/Fax analyzer tool not found at", PAGING_FAX_ANALYZER_SCRIPT)
        return
    rc, out, err = run(["python3", PAGING_FAX_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()


def run_comprehensive_analyzer(sock):
    """Invoke the comprehensive FreePBX component analyzer."""
    if not os.path.isfile(COMPREHENSIVE_ANALYZER_SCRIPT):
        print("Comprehensive analyzer tool not found at", COMPREHENSIVE_ANALYZER_SCRIPT)
        return
    rc, out, err = run(["python3", COMPREHENSIVE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()


def run_call_simulation_menu(sock, did_rows):
    """Interactive call simulation and validation menu."""
    print("\n=== Call Simulation & Validation Menu ===")
    print("Test real call behavior against predicted call flows")
    print()
    
    while True:
        print("📞 Call Simulation Options:")
        print(" 1) Test specific DID with call simulation (makes actual test call)")
        print(" 2) Validate call flow configuration for DID (checks database only)")
        print(" 3) Test extension call (internal extension-to-extension)")
        print(" 4) Test voicemail call (voicemail access and functionality)")
        print(" 5) Validate ring group configuration (checks members & settings)")
        print(" 6) Run comprehensive call validation (all checks across system)")
        print(" 7) Monitor active call simulations (real-time status)")
        print(" 8) Return to main menu")
        print()
        
        choice = input("Choose simulation option (1-8): ").strip()
        
        if choice == "1":
            run_did_call_test(did_rows)
        elif choice == "2":
            run_callflow_validation(did_rows)
        elif choice == "3":
            run_extension_test()
        elif choice == "4":
            run_voicemail_test()
        elif choice == "5":
            run_playback_test()
        elif choice == "6":
            run_comprehensive_validation()
        elif choice == "7":
            run_call_monitoring()
        elif choice == "8":
            break
        else:
            print("Invalid choice. Please select 1-8.")


def run_did_call_test(did_rows):
    """Test a specific DID with call simulation."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return
    
    if not did_rows:
        print("❌ No DID data available. Please refresh the snapshot first.")
        return
    
    print("\n📞 DID Call Simulation Test")
    print("This will create a real call file to test the DID routing.")
    print()
    
    # Show available DIDs
    for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
        print(f"{i:>2}. {did:<15} {label}")
    
    if len(did_rows) > 20:
        print(f"... and {len(did_rows) - 20} more DIDs")
    
    print()
    try:
        choice = int(input("Enter DID number to test (or 0 to cancel): ").strip())
        if choice == 0:
            return
        if choice < 1 or choice > len(did_rows):
            print("❌ Invalid selection.")
            return
        
        _, did, label, _, _ = did_rows[choice - 1]
        caller_id = input(f"Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
        
        print(f"\n🚀 Testing DID {did} ({label}) with caller ID {caller_id}")
        print("This will create a real call in the Asterisk system...")
        
        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Test cancelled.")
            return
        
        # Run the call simulation
        cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--did", str(did), "--caller-id", caller_id, "--debug"]
        print(f"Executing: {' '.join(cmd)}")
        
        rc, out, err = run(cmd)
        if rc == 0:
            print("✅ Call simulation completed successfully!")
            print(out)
        else:
            print("❌ Call simulation failed:")
            print(err or out)
            
    except ValueError:
        print("❌ Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\n❌ Test cancelled by user.")


def run_callflow_validation(did_rows):
    """Validate call flow accuracy for a specific DID."""
    if not os.path.isfile(CALLFLOW_VALIDATOR_SCRIPT):
        print("❌ Call flow validator not found. Please run deployment first.")
        return
    
    if not did_rows:
        print("❌ No DID data available. Please refresh the snapshot first.")
        return
    
    print("\n🔍 Call Flow Validation Test")
    print("This compares predicted call flows with actual call behavior.")
    print()
    
    # Show available DIDs
    for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
        print(f"{i:>2}. {did:<15} {label}")
    
    if len(did_rows) > 20:
        print(f"... and {len(did_rows) - 20} more DIDs")
    
    print()
    try:
        choice = int(input("Enter DID number to validate (or 0 to cancel): ").strip())
        if choice == 0:
            return
        if choice < 1 or choice > len(did_rows):
            print("❌ Invalid selection.")
            return
        
        _, did, label, _, _ = did_rows[choice - 1]
        
        print(f"\n🔍 Validating call flow for DID {did} ({label})")
        print("This will:")
        print("1. Generate predicted call flow")
        print("2. Simulate actual call")
        print("3. Compare prediction vs reality")
        print("4. Provide accuracy score")
        
        confirm = input("\nContinue with validation? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Validation cancelled.")
            return
        
        # Run the validation
        cmd = ["python3", CALLFLOW_VALIDATOR_SCRIPT, str(did)]
        print(f"Executing: {' '.join(cmd)}")
        
        rc, out, err = run(cmd)
        if rc == 0:
            print("✅ Call flow validation completed!")
            print(out)
        else:
            print("❌ Call flow validation failed:")
            print(err or out)
            
    except ValueError:
        print("❌ Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\n❌ Validation cancelled by user.")


def run_extension_test():
    """Test calling a specific extension."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return
    
    print("\n📱 Extension Call Test")
    
    extension = input("Enter extension number to test: ").strip()
    if not extension:
        print("❌ Extension number required.")
        return
    
    caller_id = input("Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
    
    print(f"\n🚀 Testing extension {extension} with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--extension", extension, "--caller-id", caller_id, "--debug"]
    rc, out, err = run(cmd)
    
    if rc == 0:
        print("✅ Extension test completed!")
        print(out)
    else:
        print("❌ Extension test failed:")
        print(err or out)


def run_voicemail_test():
    """Test calling voicemail."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return
    
    print("\n📧 Voicemail Call Test")
    
    mailbox = input("Enter voicemail mailbox to test: ").strip()
    if not mailbox:
        print("❌ Mailbox number required.")
        return
    
    caller_id = input("Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
    
    print(f"\n🚀 Testing voicemail {mailbox} with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--voicemail", mailbox, "--caller-id", caller_id, "--debug"]
    rc, out, err = run(cmd)
    
    if rc == 0:
        print("✅ Voicemail test completed!")
        print(out)
    else:
        print("❌ Voicemail test failed:")
        print(err or out)


def run_playback_test():
    """Test playback application (like zombies example)."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return
    
    print("\n🎵 Playback Application Test")
    print("Common sound files: demo-congrats, demo-thanks, zombies, beep")
    
    sound_file = input("Enter sound file to play: ").strip()
    if not sound_file:
        print("❌ Sound file required.")
        return
    
    caller_id = input("Enter caller ID to use (default 7346427842): ").strip() or "7346427842"
    
    print(f"\n🚀 Testing playback of '{sound_file}' with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--playback", sound_file, "--caller-id", caller_id, "--debug"]
    rc, out, err = run(cmd)
    
    if rc == 0:
        print("✅ Playback test completed!")
        print(out)
    else:
        print("❌ Playback test failed:")
        print(err or out)


def run_comprehensive_validation():
    """Run comprehensive call validation testing."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print("❌ Call simulator not found. Please run deployment first.")
        return
    
    print("\n🧪 Comprehensive Call Validation")
    print("This will run a full test suite including:")
    print("- DID routing tests")
    print("- Extension tests")
    print("- Voicemail tests")
    print("- Application tests")
    print("- Performance measurement")
    print()
    
    print("⚠️  WARNING: This will create multiple real calls in your system!")
    
    confirm = input("Continue with comprehensive testing? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Testing cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--comprehensive", "--debug"]
    rc, out, err = run(cmd)
    
    if rc == 0:
        print("✅ Comprehensive validation completed!")
        print(out)
    else:
        print("❌ Comprehensive validation failed:")
        print(err or out)


def run_call_monitoring():
    """Monitor active call simulations."""
    if not os.path.isfile(SIMULATE_CALLS_SCRIPT):
        print("❌ Call monitoring script not found. Please run deployment first.")
        return
    
    print("\n📊 Call Simulation Monitor")
    print("This will show active call files and recent Asterisk activity.")
    print("Press Ctrl+C to stop monitoring.")
    print()
    
    try:
        cmd = [SIMULATE_CALLS_SCRIPT, "monitor"]
        # Use subprocess.call for interactive monitoring
        import subprocess
        subprocess.call(cmd)
    except KeyboardInterrupt:
        print("\n✅ Monitoring stopped.")
    except Exception as e:
        print(f"❌ Monitoring failed: {str(e)}")


def run_ascii_callflow(sock, did_rows):
    """Generate ASCII art call flow for selected DIDs."""
    if not os.path.isfile(ASCII_CALLFLOW_SCRIPT):
        print("ASCII callflow tool not found at", ASCII_CALLFLOW_SCRIPT)
        return
    
    print("\n=== ASCII Art Call Flow Generator ===")
    print("Choose an option:")
    print()
    print("1. Generate ASCII flow for specific DID(s)")
    print("2. Show comprehensive data collection summary")
    print("3. Show detailed configuration data")
    print("4. Export all data to JSON file")
    print("5. Generate flows for ALL DIDs")
    print()
    
    choice = input("Enter choice (1-5): ").strip()
    
    if choice == "1":
        # Original DID-specific flow generation
        if not did_rows:
            print("No DID data available. Please refresh the snapshot first.")
            return
        
        print("\nSelect DID(s) for ASCII flow chart generation:")
        print()
        
        # Show available DIDs
        for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
            print(f"{i:>2}. {did:<15} {label}")
        
        if len(did_rows) > 20:
            print(f"... and {len(did_rows) - 20} more DIDs")
        
        print()
        selection = input("Enter DID number(s) or 'all' (e.g., 1,3,5 or 1-5): ").strip()
        
        if not selection:
            return
        
        # Parse selection
        if selection.lower() in ("all", "*"):
            selected_indices = list(range(1, min(len(did_rows) + 1, 11)))  # Limit to first 10 for ASCII
            print("Note: Limited to first 10 DIDs for ASCII output")
        else:
            selected_indices = parse_selection(selection, len(did_rows))
        
        if not selected_indices:
            print("No valid selection.")
            return
        
        print(f"\n🎨 Generating ASCII call flows for {len(selected_indices)} DID(s)...")
        print("=" * 60)
        
        for i, idx in enumerate(selected_indices):
            if i >= 10:  # Limit ASCII output
                print(f"\n... {len(selected_indices) - 10} more DIDs not shown (use individual analysis for more)")
                break
                
            _, did, label, _, _ = did_rows[idx - 1]
            print(f"\n[{i+1}/{min(len(selected_indices), 10)}] Generating flow for DID: {did}")
            print("-" * 60)
            
            cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--did", str(did)]
            rc, out, err = run(cmd)
            
            if rc == 0:
                print(out)
            else:
                print(f"❌ Error generating flow for {did}: {err or out}")
            
            if i < min(len(selected_indices), 10) - 1:
                print("\n" + "=" * 60)
    
    elif choice == "2":
        # Show data collection summary
        print("\nRunning comprehensive data collection with summary...")
        cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--print-data"]
        rc, out, err = run(cmd)
        if rc == 0:
            print(out, end="")
        else:
            print(f"Error: {err or out}")
    
    elif choice == "3":
        # Show detailed configuration data
        print("\nRunning comprehensive data collection with detailed output...")
        cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--print-data", "--detailed"]
        rc, out, err = run(cmd)
        if rc == 0:
            print(out, end="")
        else:
            print(f"Error: {err or out}")
    
    elif choice == "4":
        # Export data to JSON
        timestamp = int(time.time())
        export_file = f"/tmp/freepbx_config_{timestamp}.json"
        print(f"\nExporting comprehensive FreePBX data to: {export_file}")
        cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--export", export_file]
        rc, out, err = run(cmd)
        if rc == 0:
            print(out, end="")
            print(f"\n✅ Data exported to: {export_file}")
        else:
            print(f"Error: {err or out}")
    
    elif choice == "5":
        # Generate flows for all DIDs
        print("\nGenerating ASCII flows for ALL DIDs...")
        cmd = ["python3", ASCII_CALLFLOW_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--generate-flow"]
        rc, out, err = run(cmd)
        if rc == 0:
            print(out, end="")
        else:
            print(f"Error: {err or out}")
    
    else:
        print("Invalid choice.")


# ---------------- helpers ----------------

def run(cmd, env=None):
    """subprocess.run wrapper (3.6-safe: universal_newlines instead of text=)."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    return p.returncode, (p.stdout or ""), (p.stderr or "")

def detect_mysql_socket():
    rc, out, _ = run(["bash", "-lc", "mysql -NBe 'SHOW VARIABLES LIKE \"socket\";' 2>/dev/null | awk '{print $2}'"])
    path = (out.strip().splitlines() or [""])[0]
    return path if path else DEFAULT_SOCK

def ensure_outdir():
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
    except Exception:
        pass

def load_dump():
    if not os.path.isfile(DUMP_PATH):
        return {}
    with open(DUMP_PATH, "r") as f:
        return json.load(f)

def refresh_dump(sock):
    ensure_outdir()
    print("\n[+] Refreshing FreePBX snapshot (this reads MySQL)...")
    cmd = ["python3", DUMP_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--out", DUMP_PATH]
    rc, out, err = run(cmd)
    if rc == 0:
        print("    ✓ Snapshot written to", DUMP_PATH)
        return True
    print("    ✖ Snapshot failed:\n" + (err or out))
    return False

def summarize(data):
    def count(key, sub=None):
        if key not in data: return 0
        if sub:
            return len(data[key].get(sub, []))
        return len(data[key])
    
    # Dramatic inventory display
    print("\n" + Colors.CYAN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "║" + (" � " + Colors.YELLOW + "SYSTEM INVENTORY" + Colors.CYAN).center(88) + "║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "Host:            " + Colors.RESET + Colors.GREEN + Colors.BOLD + data.get("meta", {}).get("hostname", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "freePBX version: " + Colors.RESET + Colors.YELLOW + Colors.BOLD + data.get("meta", {}).get("freepbx_version", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "MySQL version:   " + Colors.RESET + Colors.YELLOW + Colors.BOLD + data.get("meta", {}).get("mysql_version", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "Generated:       " + Colors.RESET + Colors.MAGENTA + data.get("meta", {}).get("generated_at_utc", "").ljust(58) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Inbound routes (DIDs):     " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("inbound")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "IVRs (menus):              " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ivrs", "menus")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "IVR options:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ivrs", "options")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Queues:                    " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("queues")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Ring groups:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("ringgroups")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Time conditions:           " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("timeconditions")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Time groups:               " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("timegroups")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Announcements:             " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("announcements")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Extensions:                " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(count("extensions")).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Trunks:                    " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("trunks", {}).get("trunks", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Outbound routes:           " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("outbound", {}).get("routes", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.WHITE + "Outbound patterns:         " + Colors.RESET + Colors.CYAN + Colors.BOLD + str(len(data.get("outbound", {}).get("patterns", []))).rjust(48) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.RESET)
    print("")

def list_dids(data, show_limit=50):
    dids = data.get("inbound", [])
    rows = []
    for i, r in enumerate(dids, 1):
        label = r.get("label") or ""
        cid   = r.get("cid") or ""
        dest  = r.get("destination") or ""
        rows.append((i, r.get("did",""), label, cid, dest))
    if not rows:
        print(Colors.RED + "❌ No inbound routes found." + Colors.RESET)
        return []
    
    print(Colors.CYAN + "╔" + "═" * 115 + "╗" + Colors.RESET)
    print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 📞 DID ROUTING TABLE ".center(115) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * 115 + "╣" + Colors.RESET)
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.WHITE + "Index │ DID           │ Label                         │ CID   │ Destination                    " + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * 115 + "╣" + Colors.RESET)
    
    for i, did, label, cid, dest in rows[:show_limit]:
        print(Colors.CYAN + "║ " + Colors.RESET + "{:>5} │ {:<13} │ {:<29} │ {:<5} │ {:<32}".format(
            i, Colors.GREEN + did + Colors.RESET, label[:29], cid[:5], dest[:32]) + Colors.CYAN + " ║" + Colors.RESET)
    
    print(Colors.CYAN + "╚" + "═" * 115 + "╝" + Colors.RESET)
    
    if len(rows) > show_limit:
        print(Colors.YELLOW + f"... {len(rows) - show_limit} more not shown. (Use selection to target them anyway.)" + Colors.RESET)
    return rows

def parse_selection(sel, max_index):
    sel = sel.strip()
    if sel in ("*", "all", "ALL"):
        return list(range(1, max_index+1))
    chosen = set()
    for part in sel.split(","):
        part = part.strip()
        if not part: continue
        if "-" in part:
            a,b = part.split("-",1)
            try:
                a, b = int(a), int(b)
                for x in range(min(a,b), max(a,b)+1):
                    if 1 <= x <= max_index: chosen.add(x)
            except ValueError:
                pass
        else:
            try:
                x = int(part)
                if 1 <= x <= max_index: chosen.add(x)
            except ValueError:
                pass
    return sorted(chosen)

def render_dids(did_rows, indexes, sock, skip_labels=None):
    ensure_outdir()
    ok = 0; bad = 0
    for idx in indexes:
        _, did, label, _, _ = did_rows[idx-1]
        if skip_labels and label and label.strip().lower() in skip_labels:
            print("• Skipping DID {} (label='{}')".format(did, label))
            continue
        out_file = os.path.join(OUT_DIR, "callflow_{}.svg".format(did))
        cmd = ["python3", GRAPH_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--did", str(did), "--out", out_file]
        rc, out, err = run(cmd)
        if rc == 0 and os.path.isfile(out_file):
            print("✓ DID {} -> {}".format(did, out_file))
            ok += 1
        else:
            print("✖ DID {} FAILED: {}".format(did, (err or out).strip()))
            bad += 1
    print("\nDone. Success: {}, Failed: {}".format(ok, bad))

def get_service_status(services):
    """Get status of system services"""
    status_list = []
    for service in services:
        # Try common variations for certain services
        variations = [service]
        if service == "asterisk":
            variations = ["asterisk", "asterisk16", "asterisk18", "asterisk20"]
        elif service == "php-fpm":
            variations = ["php-fpm", "php73-php-fpm", "php74-php-fpm", "php80-php-fpm", "rh-php73-php-fpm"]
        
        found = False
        for variant in variations:
            try:
                # Try systemctl first (EL7+)
                cmd = ["systemctl", "is-active", variant]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                      universal_newlines=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip() == "active":
                    status_list.append((service, "running", Colors.GREEN))
                    found = True
                    break
            except Exception:
                pass
        
        if not found:
            try:
                # Try service command (older systems)
                for variant in variations:
                    cmd = ["service", variant, "status"]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                          universal_newlines=True, timeout=2)
                    if result.returncode == 0:
                        status_list.append((service, "running", Colors.GREEN))
                        found = True
                        break
            except Exception:
                pass
        
        if not found:
            status_list.append((service, "stopped", Colors.RED))
    
    return status_list

def get_active_calls(sock):
    """Get count of active calls from Asterisk"""
    try:
        cmd = ["asterisk", "-rx", "core show channels count"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              universal_newlines=True, timeout=5)
        output = result.stdout
        # Parse output like "2 active channels" or "0 active calls"
        for line in output.split('\n'):
            if 'active call' in line.lower() or 'active channel' in line.lower():
                parts = line.split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
    except Exception:
        pass
    return None

def get_time_conditions_status(sock):
    """Get time conditions count using direct MySQL query - returns (total_count, forced_count, status_list)"""
    try:
        # Simple query - just like typing "mysql" then running SQL
        # No socket, no user flags - just plain mysql command like manual use
        sql = "SELECT COUNT(*) FROM timeconditions"
        cmd = ["mysql", "-NBe", sql, "asterisk"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)
        
        if result.returncode != 0 or not result.stdout.strip():
            err_msg = result.stderr.strip()[:50] if result.stderr else "Query failed"
            return (0, 0, ["DB Error: " + err_msg])
        
        total_count = int(result.stdout.strip())
        
        # Now get forced count
        sql2 = "SELECT COUNT(*) FROM timeconditions WHERE inuse_state IN (1,2)"
        cmd2 = ["mysql", "-NBe", sql2, "asterisk"]
        result2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True, timeout=5)
        forced_count = int(result2.stdout.strip()) if result2.returncode == 0 and result2.stdout.strip() else 0
        
        # Build status display
        status_display = []
        if total_count > 0:
            if forced_count > 0:
                status_display.append("{} Total | {} Override | {} Auto".format(total_count, forced_count, total_count - forced_count))
            else:
                status_display.append("{} Total | All running on schedule".format(total_count))
        else:
            status_display.append("No time conditions found")
        
        return (total_count, forced_count, status_display)
    except Exception as e:
        return (0, 0, ["Error: " + str(e)[:50]])

def get_recent_package_updates():
    """Get recent Asterisk/FreePBX package updates from system package manager"""
    import datetime
    updates = []
    
    try:
        # Try yum/dnf history first (RHEL/CentOS)
        cmd = ["yum", "history", "list", "asterisk*"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              universal_newlines=True, timeout=5)
        
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            # Parse yum history output
            for line in lines:
                if 'asterisk' in line.lower() and ('install' in line.lower() or 'update' in line.lower()):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        # Extract date and action
                        date_str = parts[1].strip() if len(parts) > 1 else ""
                        action = parts[2].strip() if len(parts) > 2 else ""
                        
                        # Parse date and calculate time ago
                        try:
                            # Date format: 2025-10-17 12:17
                            update_time = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            now = datetime.datetime.now()
                            delta = now - update_time
                            
                            if delta.days == 0:
                                time_ago = "today"
                            elif delta.days == 1:
                                time_ago = "yesterday"
                            elif delta.days < 7:
                                time_ago = "{}d ago".format(delta.days)
                            elif delta.days < 30:
                                time_ago = "{}w ago".format(delta.days // 7)
                            else:
                                time_ago = "{}mo ago".format(delta.days // 30)
                            
                            updates.append("Asterisk {} ({})".format(action.lower(), time_ago))
                            if len(updates) >= 5:
                                break
                        except Exception:
                            pass
        
        # If no yum history, try rpm query
        if not updates:
            cmd = ["rpm", "-qa", "--last", "asterisk*"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True, timeout=5)
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')[:5]  # Get first 5
                for line in lines:
                    if line:
                        # Format: package-name date
                        parts = line.split()
                        if parts:
                            pkg = parts[0]
                            # Extract version from package name
                            updates.append(pkg)
    
    except Exception:
        pass
    
    return updates if updates else ["No package history found"]

def get_endpoint_status(sock):
    """Get SIP endpoint registration status"""
    try:
        # Get list of extensions from database - simple mysql command
        sql = "SELECT extension, name FROM users ORDER BY CAST(extension AS UNSIGNED)"
        cmd = ["mysql", "-NBe", sql, "asterisk"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)
        
        if result.returncode != 0 or not result.stdout.strip():
            return {"registered": 0, "unregistered": 0, "total": 0, "details": []}
        
        extensions = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 1:
                    ext = parts[0]
                    name = parts[1] if len(parts) > 1 else ""
                    extensions.append((ext, name))
        
        # Check registration status via Asterisk
        registered = []
        unregistered = []
        
        cmd = ["asterisk", "-rx", "pjsip show endpoints"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=5)
        
        if result.returncode == 0 and result.stdout:
            # Parse pjsip output - format: Endpoint/CID/Auth/Device State
            pjsip_status = {}
            for line in result.stdout.split('\n'):
                parts = line.split()
                if parts and parts[0].isdigit() and len(parts) >= 4:
                    ext = parts[0]
                    # Device state in format like "Unavail" or "Avail"
                    state = parts[-1] if len(parts) > 0 else "Unknown"
                    pjsip_status[ext] = state
            
            # Match extensions with registration status
            for ext, name in extensions:  # Show ALL endpoints
                if ext in pjsip_status:
                    state = pjsip_status[ext]
                    if 'avail' in state.lower() or 'online' in state.lower():
                        registered.append((ext, name, state))
                    else:
                        unregistered.append((ext, name, state))
                else:
                    unregistered.append((ext, name, "Not Found"))
        
        return {
            "registered": len(registered),
            "unregistered": len(unregistered),
            "total": len(extensions),
            "details": registered + unregistered
        }
    
    except Exception:
        return {"registered": 0, "unregistered": 0, "total": 0, "details": []}

def display_system_dashboard(sock, data):
    """Display key system information in a professional tile-based dashboard layout"""
    import os
    import shutil
    
    # Detect terminal width dynamically
    try:
        term_width = shutil.get_terminal_size().columns
    except:
        term_width = 160  # Default fallback
    
    # Calculate optimal tile width based on terminal (3 tiles + borders + separators)
    # Formula: term_width = 3*TILE_WIDTH + 6 (borders) + 6 (separators)
    TILE_WIDTH = max(48, (term_width - 12) // 3)  # Minimum 48 chars per tile (increased from 36)
    BOX_TOTAL = (TILE_WIDTH * 3) + 12  # Total width for perfect alignment
    
    # Clear screen and display ASCII Art Logo
    print("\033[2J\033[H")  # Clear screen
    print(Colors.CYAN + Colors.BOLD)
    print("    ______              ____  ______  __  __      _____           __    ")
    print("   / ____/_______  ____/ __ \\/ __ ) \\/ / /      /_  __/___  ____/ /____")
    print("  / /_  / ___/ _ \\/ __  / / / / __  |\\  /_/      / / / __ \\/ __ / / ___/")
    print(" / __/ / /  /  __/ /_/ / /_/ / /_/ / / /__/     / / / /_/ / /_/ / (__  ) ")
    print("/_/   /_/   \\___/\\____/_____/_____/ /_/   /    /_/  \\____/\\____/_/____/  ")
    print(Colors.RESET)
    
    # Get meta info
    meta = data.get("meta", {}) if data else {}
    hostname = meta.get("hostname", "Unknown")
    freepbx_ver = meta.get("freepbx_version", "N/A")
    asterisk_ver = meta.get("asterisk_version", "N/A")
    
    # Dashboard Header with system info - full width, properly aligned
    header_text = f"📊 SYSTEM DASHBOARD  │  Host: {hostname[:25].ljust(25)}  │  FreePBX: {freepbx_ver[:15].ljust(15)}  │  Asterisk: {asterisk_ver[:30].ljust(30)}"
    # Pad to full terminal width
    header_padding = " " * max(0, BOX_TOTAL - len(header_text) - 2)
    header_line = (Colors.BG_CYAN + Colors.WHITE + Colors.BOLD + 
                   " " + header_text + header_padding + " " + Colors.RESET)
    print("\n" + header_line)
    print(Colors.CYAN + "─" * BOX_TOTAL + Colors.RESET)
    
    # Get all data first
    active_calls = get_active_calls(sock)
    tc_total, forced_count, tc_status_list = get_time_conditions_status(sock)
    endpoint_status = get_endpoint_status(sock)
    services = ["asterisk", "httpd", "mariadb", "fail2ban", "php-fpm", "crond"]
    service_status = get_service_status(services)
    
    # Calculate metrics
    ep_total = endpoint_status["total"]
    ep_registered = endpoint_status["registered"]
    ep_unreg = endpoint_status["unregistered"]
    ep_pct = int((ep_registered / ep_total) * 100) if ep_total > 0 else 0
    running_count = sum(1 for _, status, _ in service_status if status == "running")
    stopped_count = sum(1 for _, status, _ in service_status if status == "stopped")
    
    # Inventory counts
    dids_count = len(data.get("inbound", [])) if data else 0
    ext_count = len(data.get("extensions", [])) if data else 0
    rg_count = len(data.get("ringgroups", [])) if data else 0
    ivr_count = len(data.get("ivrs", {}).get("menus", [])) if data else 0
    queue_count = len(data.get("queues", [])) if data else 0
    trunks_count = len(data.get("trunks", {}).get("trunks", [])) if data else 0
    
    # ====================
    # ROW 1: 3 Tiles - Active Calls | Time Conditions | Endpoints
    # ====================
    print("\n" + Colors.CYAN + "╔" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╗" + Colors.RESET)
    
    # Tile headers
    h1 = "📞  ACTIVE CALLS"
    h2 = "⏰  TIME CONDITIONS"
    h3 = "📱  ENDPOINT REGISTRATIONS"
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.GREEN + h1.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + 
          " ║ " + Colors.BOLD + Colors.MAGENTA + h2.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.BLUE + h3.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╣" + Colors.RESET)
    
    # Color logic
    call_color = Colors.RED if active_calls and active_calls > 10 else Colors.GREEN if active_calls and active_calls > 0 else Colors.CYAN
    tc_color = Colors.YELLOW if forced_count > 0 else Colors.GREEN
    ep_color = Colors.GREEN if ep_pct > 80 else Colors.YELLOW if ep_pct > 50 else Colors.RED
    
    # Build simple, clean tiles - just numbers and labels
    # Row 1 - Big numbers centered
    call_num = str(active_calls if active_calls is not None else "N/A")
    tc_num = str(tc_total)
    ep_num = str(ep_total)
    
    r1_c1 = pad_ansi(f"{call_color}{Colors.BOLD}{call_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r1_c2 = pad_ansi(f"{tc_color}{Colors.BOLD}{tc_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r1_c3 = pad_ansi(f"{Colors.WHITE}{Colors.BOLD}{ep_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r1_c1 + Colors.CYAN + " ║ " + r1_c2 + Colors.CYAN + " ║ " + r1_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Row 2 - Status text
    call_status = "ACTIVE" if active_calls and active_calls > 0 else "IDLE"
    r2_c1 = pad_ansi(f"{call_color}{call_status}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r2_c2 = pad_ansi(f"{Colors.WHITE}Time Conditions{Colors.RESET}", TILE_WIDTH-2, align='center')
    r2_c3 = pad_ansi(f"{Colors.WHITE}Endpoints{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r2_c1 + Colors.CYAN + " ║ " + r2_c2 + Colors.CYAN + " ║ " + r2_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Separator
    sep = "─" * (TILE_WIDTH-2)
    print(Colors.CYAN + "║ " + sep + " ║ " + sep + " ║ " + sep + " ║" + Colors.RESET)
    
    # Row 3 - Details (centered under the title)
    forced_color = Colors.YELLOW if forced_count > 0 else Colors.GREEN
    r3_c1 = pad_ansi(f"Channels: {call_color}{Colors.BOLD}{call_num}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r3_c2 = pad_ansi(f"Forced: {forced_color}{Colors.BOLD}{forced_count}{Colors.RESET}  Auto: {Colors.GREEN}{Colors.BOLD}{tc_total - forced_count}{Colors.RESET}", TILE_WIDTH-2, align='center')
    r3_c3 = pad_ansi(f"Online: {ep_color}{Colors.BOLD}{ep_registered}{Colors.RESET} ({ep_pct}%)", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r3_c1 + Colors.CYAN + " ║ " + r3_c2 + Colors.CYAN + " ║ " + r3_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    # Row 4
    r4_c1 = pad_ansi("", TILE_WIDTH-2)
    r4_c2 = pad_ansi("", TILE_WIDTH-2)
    r4_c3 = pad_ansi(f"Offline: {Colors.RED}{Colors.BOLD}{ep_unreg}{Colors.RESET}", TILE_WIDTH-2, align='center')
    
    print(Colors.CYAN + "║ " + r4_c1 + Colors.CYAN + " ║ " + r4_c2 + Colors.CYAN + " ║ " + r4_c3 + Colors.CYAN + " ║" + Colors.RESET)
    
    print(Colors.CYAN + "╚" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╝" + Colors.RESET)
    
    # ====================
    # ROW 2: 3 Tiles - Services | Inventory | Key Paths
    # ====================
    print(Colors.CYAN + "╔" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╦" + "═" * TILE_WIDTH + "╗" + Colors.RESET)
    
    # Tile headers
    h1 = "⚙️  SYSTEM SERVICES"
    h2 = "📊  SYSTEM INVENTORY"
    h3 = "📁  KEY PATHS"
    print(Colors.CYAN + "║ " + Colors.BOLD + Colors.YELLOW + h1.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.CYAN + h2.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN +
          " ║ " + Colors.BOLD + Colors.GREEN + h3.center(TILE_WIDTH-2) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
    print(Colors.CYAN + "╠" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╬" + "═" * TILE_WIDTH + "╣" + Colors.RESET)
    
    # File path checks
    snapshot_exists = os.path.exists(DUMP_PATH)
    snapshot_size = os.path.getsize(DUMP_PATH) / (1024 * 1024) if snapshot_exists else 0
    
    paths_to_check = [
        ("/etc/asterisk/", "Config", 16),
        ("/var/log/asterisk/full", "Full Log", 22),
        ("/var/spool/asterisk/monitor/", "Recordings", 27),
        ("/var/lib/mysql/asterisk/", "DB Directory", 23),
        (sock, "MySQL Socket", len(sock))
    ]
    
    # Data rows (6 rows - matching service count)
    inventory_items = [
        ("DIDs", dids_count),
        ("Extensions", ext_count),
        ("Ring Groups", rg_count),
        ("IVRs", ivr_count),
        ("Queues", queue_count),
        ("Trunks", trunks_count)
    ]
    
    for i in range(6):
        # Service column - cleaner format
        if i < len(service_status):
            svc_name, svc_stat, svc_color = service_status[i]
            status_icon = "●" if svc_stat == "running" else "○"
            stat_text = svc_stat[:7].upper()
            svc_line = pad_ansi(f"{svc_color}{status_icon} {Colors.WHITE}{svc_name.ljust(18)}{svc_color}{Colors.BOLD}{stat_text.rjust(12)}{Colors.RESET}", TILE_WIDTH-2)
        else:
            svc_line = pad_ansi("", TILE_WIDTH-2)
        
        # Inventory column - better spacing (label left, count right with reasonable gap)
        if i < len(inventory_items):
            inv_label, inv_count = inventory_items[i]
            inv_line = pad_ansi(f"{Colors.WHITE}{inv_label.ljust(18)}{Colors.CYAN}{Colors.BOLD}{str(inv_count).rjust(10)}{Colors.RESET}", TILE_WIDTH-2)
        else:
            inv_line = pad_ansi("", TILE_WIDTH-2)
        
        # Paths column - abbreviated paths
        if i == 0:
            snap_icon = Colors.GREEN + "✓" if snapshot_exists else Colors.RED + "✗"
            path_line = pad_ansi(f"{snap_icon}{Colors.WHITE} Snapshot {Colors.CYAN}({snapshot_size:.1f} MB){Colors.RESET}", TILE_WIDTH-2)
        elif i - 1 < len(paths_to_check):
            path, label, path_len = paths_to_check[i - 1]
            exists = os.path.exists(path)
            icon = Colors.GREEN + "✓" if exists else Colors.RED + "✗"
            # Shorten paths intelligently
            if "asterisk/full" in path:
                path_display = "...asterisk/full"
            elif "mysql.sock" in path:
                path_display = "mysql.sock"
            elif "monitor" in path:
                path_display = "...monitor/"
            elif "/etc/asterisk" in path:
                path_display = "/etc/asterisk/"
            elif "mysql/asterisk" in path:
                path_display = "...mysql/asterisk/"
            else:
                path_display = path[-28:] if len(path) > 28 else path
            path_line = pad_ansi(f"{icon}{Colors.WHITE} {label.ljust(14)}{Colors.CYAN}{path_display}{Colors.RESET}", TILE_WIDTH-2)
        else:
            path_line = pad_ansi("", TILE_WIDTH-2)
        
        print(Colors.CYAN + "║ " + svc_line + Colors.CYAN + " ║ " + inv_line + Colors.CYAN + " ║ " + path_line + Colors.CYAN + " ║" + Colors.RESET)
    
    print(Colors.CYAN + "╚" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╩" + "═" * TILE_WIDTH + "╝" + Colors.RESET)
    
    # ====================
    # Status Summary Bar
    # ====================
    status_parts = []
    
    # System Health
    if running_count >= 5 and active_calls is not None and ep_pct > 70:
        health = Colors.GREEN + Colors.BOLD + "GOOD" + Colors.RESET
    elif running_count >= 4 and ep_pct > 50:
        health = Colors.YELLOW + Colors.BOLD + "WARNING" + Colors.RESET
    else:
        health = Colors.RED + Colors.BOLD + "CRITICAL" + Colors.RESET
    status_parts.append("✓ System Health: " + health)
    
    # Services
    svc_status = (Colors.GREEN + str(running_count) + " Running" + Colors.RESET + " | " +
                  Colors.RED + str(stopped_count) + " Stopped" + Colors.RESET)
    status_parts.append("⚙️  Services: " + svc_status)
    
    # Forced TCs
    if forced_count == 0:
        tc_display = Colors.GREEN + "None" + Colors.RESET
    elif forced_count < 3:
        tc_display = Colors.YELLOW + str(forced_count) + Colors.RESET
    else:
        tc_display = Colors.RED + Colors.BOLD + str(forced_count) + Colors.RESET
    status_parts.append("⏰ Forced TCs: " + tc_display)
    
    # Endpoint Health
    if ep_pct > 80:
        ep_display = Colors.GREEN + str(ep_pct) + "%" + Colors.RESET
    elif ep_pct > 50:
        ep_display = Colors.YELLOW + str(ep_pct) + "%" + Colors.RESET
    else:
        ep_display = Colors.RED + Colors.BOLD + str(ep_pct) + "%" + Colors.RESET
    status_parts.append("📱 Endpoint Health: " + ep_display)
    
    print("\n  " + "  │  ".join(status_parts))
    print("")


def run_log_analysis():
    """Run automated log analysis to detect issues"""
    analyzer_script = "/usr/local/123net/freepbx-tools/bin/freepbx_log_analyzer.py"
    
    if not os.path.isfile(analyzer_script):
        print(Colors.YELLOW + "\n⚠️  Log analyzer not found. Running inline analysis..." + Colors.RESET)
        run_inline_log_analysis()
        return
    
    print(f"\n{Colors.CYAN}🔍 Running automated log analysis...{Colors.RESET}")
    print("=" * 60)
    
    rc, out, err = run(["python3", analyzer_script])
    
    if rc == 0:
        print(out)
    else:
        print(f"{Colors.RED}Error running analysis:{Colors.RESET}")
        print(err or out)
    
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()


def run_inline_log_analysis():
    """Inline log analysis when standalone script not available"""
    from collections import defaultdict
    import re
    
    full_log = "/var/log/asterisk/full"
    
    print(f"\n{Colors.CYAN}📊 Analyzing Asterisk logs (last 1000 lines)...{Colors.RESET}\n")
    
    # Check errors
    cmd = f"tail -1000 {full_log} | grep -E 'ERROR|CRITICAL'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    
    if result.stdout.strip():
        errors = result.stdout.strip().split('\n')
        error_count = len([e for e in errors if e])
        
        if error_count > 0:
            print(f"{Colors.RED}🔴 Found {error_count} error(s) in last 1000 log lines:{Colors.RESET}")
            
            # Group by error type
            error_types = defaultdict(int)
            for line in errors[:20]:  # Show first 20
                if line:
                    # Extract error message
                    match = re.search(r'(ERROR|CRITICAL).*?:\s*(.+?)$', line)
                    if match:
                        error_msg = match.group(2)[:80]
                        error_types[error_msg] += 1
            
            for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {count:>4}x {msg}")
        else:
            print(f"{Colors.GREEN}✅ No errors found{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}✅ No errors found in recent logs{Colors.RESET}")
    
    # Check trunk status
    print(f"\n{Colors.CYAN}📡 Checking trunk status...{Colors.RESET}")
    cmd = f"tail -500 {full_log} | grep -E 'trunk.*Unreachable|Registration.*failed'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    
    if result.stdout.strip():
        trunk_issues = result.stdout.strip().split('\n')
        print(f"{Colors.YELLOW}⚠️  Trunk issues detected ({len(trunk_issues)} events):{Colors.RESET}")
        for issue in trunk_issues[-5:]:
            print(f"  {issue[:120]}")
    else:
        print(f"{Colors.GREEN}✅ No trunk issues detected{Colors.RESET}")
    
    # Check authentication failures
    print(f"\n{Colors.CYAN}🔒 Checking security events...{Colors.RESET}")
    cmd = f"tail -500 {full_log} | grep -i 'failed.*auth\\|SECURITY'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    
    if result.stdout.strip():
        security_events = result.stdout.strip().split('\n')
        
        # Extract IPs
        ips = defaultdict(int)
        for line in security_events:
            ip_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', line)
            if ip_match:
                ips[ip_match.group(0)] += 1
        
        if ips:
            print(f"{Colors.YELLOW}⚠️  Authentication failures detected:{Colors.RESET}")
            for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {ip}: {count} attempts")
        else:
            print(f"{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}━{Colors.RESET}" * 60)
    print(f"{Colors.GREEN}✅ Log analysis complete{Colors.RESET}")


# ---------------- menu ----------------

def main():
    # Check if running as root (required for MySQL access)
    try:
        euid = os.geteuid()  # type: ignore
        if euid != 0:
            print(Colors.YELLOW + "\n⚠️  This tool requires root access to query the FreePBX database." + Colors.RESET)
            print(Colors.CYAN + "Please run: " + Colors.BOLD + "sudo freepbx-callflows" + Colors.RESET)
            print(Colors.CYAN + "Or switch to root first: " + Colors.BOLD + "su root" + Colors.RESET + "\n")
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have geteuid, skip check
        pass
    
    if not os.path.isfile(DUMP_SCRIPT):
        print("ERROR: {} not found.".format(DUMP_SCRIPT)); sys.exit(1)
    if not os.path.isfile(GRAPH_SCRIPT):
        print("ERROR: {} not found.".format(GRAPH_SCRIPT)); sys.exit(1)

    sock = detect_mysql_socket()
    data = load_dump()
    if not data:
        # first run: force snapshot so menu has content
        if not refresh_dump(sock):
            sys.exit(1)
        data = load_dump()

    while True:
        # Display system dashboard at top
        display_system_dashboard(sock, data)
        
        # Get terminal width for menu
        try:
            menu_width = shutil.get_terminal_size().columns - 4  # Leave margin
        except:
            menu_width = 78  # Default fallback
        
        # Menu with full width alignment
        print("\n" + Colors.CYAN + "╔" + "═" * menu_width + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 📞 freePBX Call-Flow Menu ".center(menu_width) + Colors.RESET + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * menu_width + "╣" + Colors.RESET)
        
        # Helper function to format menu line with proper alignment
        def menu_line(num, text):
            # Build the visible content (without color codes)
            visible_content = f" {num:>2}) {text}"
            # Calculate padding needed (menu_width - 2 for borders - visible length)
            padding_needed = menu_width - len(visible_content) - 2
            padding = " " * max(0, padding_needed)
            
            # Build line with colors: border + bold number + reset + text + padding + border
            num_part = f" {num:>2})"
            return (Colors.CYAN + "║" + Colors.BOLD + num_part + Colors.RESET + 
                   " " + text + padding + Colors.CYAN + " ║" + Colors.RESET)
        
        print(menu_line("1", "Refresh DB snapshot"))
        print(menu_line("2", "Show inventory (counts) + list DIDs"))
        print(menu_line("3", "Generate call-flow for selected DID(s)"))
        print(menu_line("4", "Generate call-flows for ALL DIDs"))
        print(menu_line("5", "Generate call-flows for ALL DIDs (skip labels: OPEN)"))
        print(menu_line("6", "Show Time-Condition status (+ last *code use)"))
        print(menu_line("7", "Run FreePBX module analysis"))
        print(menu_line("8", "Run paging, overhead & fax analysis"))
        print(menu_line("9", "Run comprehensive component analysis"))
        print(menu_line("10", "Generate ASCII art call-flows"))
        print(menu_line("11", "📞 Call Simulation & Validation"))
        print(menu_line("12", "Run full Asterisk diagnostic"))
        print(menu_line("13", "🔍 Automated log analysis (detect issues)"))
        print(menu_line("14", "Quit"))
        print(Colors.CYAN + "╚" + "═" * menu_width + "╝" + Colors.RESET)
        choice = input("\n" + Colors.YELLOW + "Choose: " + Colors.RESET).strip()

        if choice == "1":
            if refresh_dump(sock):
                data = load_dump()
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "2":
            summarize(data)
            list_dids(data)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "3":
            did_rows = list_dids(data)
            if not did_rows: 
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                input()
                continue
            sel = input("\nEnter indexes (e.g. 1,3,5-8) or * for all: ")
            idxs = parse_selection(sel, len(did_rows))
            if not idxs:
                print("No valid selection.")
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                input()
                continue
            render_dids(did_rows, idxs, sock)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "4":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)  # ensures we have rows
            if not did_rows: 
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                input()
                continue
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "5":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)
            if not did_rows: 
                print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
                input()
                continue
            # lowercase match set; you can add more labels here if you want to exclude them
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock,
                        skip_labels=set(["open"]))
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "6":
            run_tc_status(sock)

        elif choice == "7":
            run_module_analyzer(sock)

        elif choice == "8":
            run_paging_fax_analyzer(sock)

        elif choice == "9":
            run_comprehensive_analyzer(sock)

        elif choice == "10":
            did_rows = list_dids(data)
            if did_rows:
                run_ascii_callflow(sock, did_rows)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "11":
            did_rows = list_dids(data)
            run_call_simulation_menu(sock, did_rows)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "12":
            diag = "/usr/local/bin/asterisk-full-diagnostic.sh"
            if not os.path.isfile(diag):
                print("Diagnostic script not found at", diag)
            else:
                print("\nRunning full diagnostic (this may take ~10-30s)...\n")
                rc, out, err = run([diag])
                # The script prints its own output; nothing else to do.
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "13":
            run_log_analysis()

        elif choice == "14":
            print("Bye.")
            break
        else:
            print(Colors.RED + "Invalid choice." + Colors.RESET)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

if __name__ == "__main__":
    main()
