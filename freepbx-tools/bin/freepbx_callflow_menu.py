#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_callflow_menu.py
Menu-driven wrapper to:
  1) snapshot FreePBX data -> JSON (via freepbx_dump.py)
  2) render SVG call-flow(s) for selected or all DIDs (via freepbx_callflow_graph.py)
Python 3.6 safe. No external modules.
"""

import json, os, sys, subprocess, time

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
    print("\n=== Time Conditions: current override + last *code use ===\n")
    rc, out, err = run(["python3", TC_STATUS_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


def run_module_analyzer(sock):
    """Invoke the FreePBX module analyzer tool."""
    if not os.path.isfile(MODULE_ANALYZER_SCRIPT):
        print("Module analyzer tool not found at", MODULE_ANALYZER_SCRIPT)
        return
    print("\n=== FreePBX Module Analysis ===\n")
    rc, out, err = run(["python3", MODULE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


def run_paging_fax_analyzer(sock):
    """Invoke the FreePBX paging/fax analyzer tool."""
    if not os.path.isfile(PAGING_FAX_ANALYZER_SCRIPT):
        print("Paging/Fax analyzer tool not found at", PAGING_FAX_ANALYZER_SCRIPT)
        return
    print("\n=== Paging, Overhead & Fax Analysis ===\n")
    rc, out, err = run(["python3", PAGING_FAX_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


def run_comprehensive_analyzer(sock):
    """Invoke the comprehensive FreePBX component analyzer."""
    if not os.path.isfile(COMPREHENSIVE_ANALYZER_SCRIPT):
        print("Comprehensive analyzer tool not found at", COMPREHENSIVE_ANALYZER_SCRIPT)
        return
    print("\n=== Comprehensive Component Analysis ===\n")
    rc, out, err = run(["python3", COMPREHENSIVE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


def run_call_simulation_menu(sock, did_rows):
    """Interactive call simulation and validation menu."""
    print("\n=== Call Simulation & Validation Menu ===")
    print("Test real call behavior against predicted call flows")
    print()
    
    while True:
        print("📞 Call Simulation Options:")
        print(" 1) Test specific DID with call simulation")
        print(" 2) Validate call flow accuracy for DID")
        print(" 3) Test extension call")
        print(" 4) Test voicemail call")
        print(" 5) Test playback application")
        print(" 6) Run comprehensive call validation")
        print(" 7) Monitor active call simulations")
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
        caller_id = input(f"Enter caller ID to use (default 7140): ").strip() or "7140"
        
        print(f"\n🚀 Testing DID {did} ({label}) with caller ID {caller_id}")
        print("This will create a real call in the Asterisk system...")
        
        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Test cancelled.")
            return
        
        # Run the call simulation
        cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--did", str(did), "--caller-id", caller_id]
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
    
    caller_id = input("Enter caller ID to use (default 7140): ").strip() or "7140"
    
    print(f"\n🚀 Testing extension {extension} with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--extension", extension, "--caller-id", caller_id]
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
    
    caller_id = input("Enter caller ID to use (default 7140): ").strip() or "7140"
    
    print(f"\n🚀 Testing voicemail {mailbox} with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--voicemail", mailbox, "--caller-id", caller_id]
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
    
    caller_id = input("Enter caller ID to use (default 7140): ").strip() or "7140"
    
    print(f"\n🚀 Testing playback of '{sound_file}' with caller ID {caller_id}")
    
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test cancelled.")
        return
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--playback", sound_file, "--caller-id", caller_id]
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
    
    cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--comprehensive"]
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
    print("\n[+] Refreshing FreePBX snapshot (this reads MySQL)…")
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
    print("\n=== Inventory ===")
    print(" Host:            {}".format(data.get("meta", {}).get("hostname", "")))
    print(" FreePBX version: {}".format(data.get("meta", {}).get("freepbx_version", "")))
    print(" MySQL version:   {}".format(data.get("meta", {}).get("mysql_version", "")))
    print(" Generated:       {}".format(data.get("meta", {}).get("generated_at_utc", "")))
    print("")
    print(" Inbound routes (DIDs):     {:>4}".format(count("inbound")))
    print(" IVRs (menus):              {:>4}".format(count("ivrs", "menus")))
    print(" IVR options:               {:>4}".format(count("ivrs", "options")))
    print(" Queues:                    {:>4}".format(count("queues")))
    print(" Ring groups:               {:>4}".format(count("ringgroups")))
    print(" Time conditions:           {:>4}".format(count("timeconditions")))
    print(" Time groups:               {:>4}".format(count("timegroups")))
    print(" Announcements:             {:>4}".format(count("announcements")))
    print(" Extensions:                {:>4}".format(count("extensions")))
    print(" Trunks:                    {:>4}".format(len(data.get("trunks", {}).get("trunks", []))))
    print(" Outbound routes:           {:>4}".format(len(data.get("outbound", {}).get("routes", []))))
    print(" Outbound patterns:         {:>4}".format(len(data.get("outbound", {}).get("patterns", []))))
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
        print("No inbound routes found.")
        return []
    print("Index | DID           | Label                         | CID   | Destination")
    print("------+---------------+-------------------------------+-------+-------------------------------")
    for i, did, label, cid, dest in rows[:show_limit]:
        print("{:>5} | {:<13} | {:<29} | {:<5} | {}".format(i, did, label[:29], cid[:5], dest[:40]))
    if len(rows) > show_limit:
        print("… {} more not shown. (Use selection to target them anyway.)".format(len(rows) - show_limit))
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

# ---------------- menu ----------------

def main():
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
        print("========== FreePBX Call-Flow Menu ==========")
        print(" 1) Refresh DB snapshot")
        print(" 2) Show inventory (counts) + list DIDs")
        print(" 3) Generate call-flow for selected DID(s)")
        print(" 4) Generate call-flows for ALL DIDs")
        print(" 5) Generate call-flows for ALL DIDs (skip labels: OPEN)")
        print(" 6) Show Time-Condition status (+ last *code use)")
        print(" 7) Run FreePBX module analysis")
        print(" 8) Run paging, overhead & fax analysis")
        print(" 9) Run comprehensive component analysis")
        print("10) Generate ASCII art call-flows")
        print("11) 📞 Call Simulation & Validation")
        print("12) Run full Asterisk diagnostic")
        print("13) Quit")
        choice = input("\nChoose: ").strip()

        if choice == "1":
            if refresh_dump(sock):
                data = load_dump()

        elif choice == "2":
            summarize(data)
            list_dids(data)

        elif choice == "3":
            did_rows = list_dids(data)
            if not did_rows: continue
            sel = input("\nEnter indexes (e.g. 1,3,5-8) or * for all: ")
            idxs = parse_selection(sel, len(did_rows))
            if not idxs:
                print("No valid selection.")
                continue
            render_dids(did_rows, idxs, sock)

        elif choice == "4":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)  # ensures we have rows
            if not did_rows: continue
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock)

        elif choice == "5":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)
            if not did_rows: continue
            # lowercase match set; you can add more labels here if you want to exclude them
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock,
                        skip_labels=set(["open"]))

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

        elif choice == "11":
            did_rows = list_dids(data)
            run_call_simulation_menu(sock, did_rows)

        elif choice == "12":
            diag = "/usr/local/bin/asterisk-full-diagnostic.sh"
            if not os.path.isfile(diag):
                print("Diagnostic script not found at", diag)
            else:
                print("\nRunning full diagnostic (this may take ~10–30s)…\n")
                rc, out, err = run([diag])
                # The script prints its own output; nothing else to do.

        elif choice == "13":
            print("Bye.")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
