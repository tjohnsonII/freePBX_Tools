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
CALL_SIMULATOR_SCRIPT = "/usr/local/123net/freepbx-tools/bin/call_simulator.py"
CALLFLOW_VALIDATOR_SCRIPT = "/usr/local/123net/freepbx-tools/bin/callflow_validator.py"
SIMULATE_CALLS_SCRIPT = "/usr/local/123net/freepbx-tools/bin/simulate_calls.sh"
NETWORK_DIAGNOSTICS_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_network_diagnostics.py"
LOG_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_log_analyzer.py"
CDR_ANALYZER_SCRIPT = "/usr/local/123net/freepbx-tools/bin/freepbx_cdr_analyzer.py"


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
    print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 Call Simulation & Validation Menu{' ' * 39}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} Test real call behavior against predicted call flows{' ' * 24}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    print()
    
    while True:
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 Call Simulation Options{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 1){Colors.WHITE} Test specific DID with call simulation (makes actual test call){' ' * 6}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 2){Colors.WHITE} Validate call flow configuration for DID (checks database only){' ' * 6}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 3){Colors.WHITE} Test extension call (internal extension-to-extension){' ' * 17}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 4){Colors.WHITE} Test voicemail call (voicemail access and functionality){' ' * 14}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 5){Colors.WHITE} Validate ring group configuration (checks members & settings){' ' * 9}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 6){Colors.WHITE} Run comprehensive call validation (all checks across system){' ' * 9}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 7){Colors.WHITE} Monitor active call simulations (real-time status){' ' * 20}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 8){Colors.WHITE} Return to main menu{' ' * 51}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()
        
        choice = input(f"{Colors.YELLOW}Choose simulation option (1-8): {Colors.RESET}").strip()
        
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
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-8.{Colors.RESET}")


def run_did_call_test(did_rows):
    """Test a specific DID with call simulation."""
    if not os.path.isfile(CALL_SIMULATOR_SCRIPT):
        print(f"{Colors.RED}❌ Call simulator not found. Please run deployment first.{Colors.RESET}")
        return
    
    if not did_rows:
        print(f"{Colors.RED}❌ No DID data available. Please refresh the snapshot first.{Colors.RESET}")
        return
    
    print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 DID Call Simulation Test{' ' * 49}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} This will create a real call file to test the DID routing.{' ' * 18}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    print()
    
    # Show available DIDs
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.WHITE}Available DIDs:{Colors.RESET}")
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    
    for i, (_, did, label, _, _) in enumerate(did_rows[:20], 1):
        print(f"{Colors.GREEN}{i:>2}.{Colors.RESET} {Colors.CYAN}{did:<15}{Colors.WHITE} {label}{Colors.RESET}")
    
    if len(did_rows) > 20:
        print(f"{Colors.YELLOW}... and {len(did_rows) - 20} more DIDs{Colors.RESET}")
    
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")
    print()
    
    try:
        choice = int(input(f"{Colors.YELLOW}Enter DID number to test (or 0 to cancel): {Colors.RESET}").strip())
        if choice == 0:
            return
        if choice < 1 or choice > len(did_rows):
            print(f"{Colors.RED}❌ Invalid selection.{Colors.RESET}")
            return
        
        _, did, label, _, _ = did_rows[choice - 1]
        destination = input(f"{Colors.YELLOW}Enter destination number (where to ring the call, e.g., your cell): {Colors.RESET}").strip()
        if not destination:
            print(f"{Colors.RED}❌ Destination number required.{Colors.RESET}")
            return
        
        print(f"\n{Colors.GREEN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.YELLOW}{Colors.BOLD} 🚀 Testing DID {did} ({label[:40]}){' ' * (31 - len(label[:40]))}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}   Incoming call from: {Colors.CYAN}{Colors.BOLD}{did:<49}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}   Ringing to: {Colors.MAGENTA}{Colors.BOLD}{destination:<57}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.YELLOW}   This will create a real call in the Asterisk system...{' ' * 17}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}╚{'═' * 78}╝{Colors.RESET}")
        print()
        
        confirm = input(f"{Colors.YELLOW}Continue? (y/N): {Colors.RESET}").strip().lower()
        if confirm != 'y':
            print(f"{Colors.RED}❌ Test cancelled.{Colors.RESET}")
            return
        
        # Run the call simulation
        # Note: --caller-id is the source (DID), destination is where it rings
        cmd = ["python3", CALL_SIMULATOR_SCRIPT, "--did", str(did), "--destination", destination, "--debug"]
        print(f"{Colors.CYAN}Executing: {' '.join(cmd)}{Colors.RESET}\n")
        
        rc, out, err = run(cmd)
        if rc == 0:
            print(f"\n{Colors.GREEN}✅ Call simulation completed successfully!{Colors.RESET}")
            print(out)
        else:
            print(f"\n{Colors.RED}❌ Call simulation failed:{Colors.RESET}")
            print(err or out)
            
    except ValueError:
        print(f"{Colors.RED}❌ Invalid input. Please enter a number.{Colors.RESET}")
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}❌ Test cancelled by user.{Colors.RESET}")


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
    
    while True:
        print("\n=== ASCII Art Call Flow Generator ===")
        print("Choose an option:")
        print()
        print("1. Generate ASCII flow for specific DID(s)")
        print("2. Show comprehensive data collection summary")
        print("3. Show detailed configuration data")
        print("4. Export all data to JSON file")
        print("5. Generate flows for ALL DIDs")
        print("6. Return to main menu")
        print()
        
        choice = input("Enter choice (1-6): ").strip()
        
        if choice == "6":
            # Return to main menu
            print("Returning to main menu...")
            break
        
        elif choice == "1":
            # Original DID-specific flow generation
            if not did_rows:
                print("No DID data available. Please refresh the snapshot first.")
                continue
            
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
                continue
            
            # Parse selection
            if selection.lower() in ("all", "*"):
                selected_indices = list(range(1, min(len(did_rows) + 1, 11)))  # Limit to first 10 for ASCII
                print("Note: Limited to first 10 DIDs for ASCII output")
            else:
                selected_indices = parse_selection(selection, len(did_rows))
            
            if not selected_indices:
                print("No valid selection.")
                continue
            
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
            print("Invalid choice. Please enter 1-6.")
        
        # After completing any action (except return to main menu), loop back
        if choice != "6":
            input("\nPress Enter to continue...")



def show_error_map_quick_reference():
    """Display interactive error map and quick reference tables"""
    while True:
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}")
        print(f"  📚 FreePBX Error Map & Quick Reference")
        print(f"{'='*80}{Colors.RESET}\n")
        
        print(f"{Colors.YELLOW}Choose a reference:{Colors.RESET}")
        print(f"  {Colors.CYAN}1){Colors.RESET} SIP/Q.850 Code Lookup")
        print(f"  {Colors.CYAN}2){Colors.RESET} Common Issues Quick Reference")
        print(f"  {Colors.CYAN}3){Colors.RESET} Diagnostic Symptoms Guide")
        print(f"  {Colors.CYAN}4){Colors.RESET} Response Playbooks Summary")
        print(f"  {Colors.CYAN}5){Colors.RESET} Return to main menu")
        print()
        
        choice = input(f"{Colors.YELLOW}Enter choice (1-5): {Colors.RESET}").strip()
        
        if choice == "5":
            break
        elif choice == "1":
            show_sip_code_reference()
        elif choice == "2":
            show_common_issues_matrix()
        elif choice == "3":
            show_diagnostic_symptoms()
        elif choice == "4":
            show_playbooks_summary()
        else:
            print(f"{Colors.RED}Invalid choice. Please enter 1-5.{Colors.RESET}")
        
        input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.RESET}")


def show_sip_code_reference():
    """Display SIP/Q.850/Asterisk code mapping table"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*98}╗")
    print(f"║{' SIP / Q.850 / ASTERISK CAUSE CODE MAPPING':^98}║")
    print(f"╠{'═'*98}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'SIP':<6} │ {'Q.850':<6} │ {'Description':<25} │ {'What It Usually Means':<50}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*98}╣{Colors.RESET}")
    
    codes = [
        ("404", "1", "Not Found", "Extension not found or wrong dialed number"),
        ("408", "18", "Request Timeout", "No response – NAT, firewall, or transport issue"),
        ("480", "19", "Unavailable", "Rings then drops - user never answered"),
        ("486", "17", "Busy Here", "Phone in use or call limit reached"),
        ("487", "16", "Terminated", "Normal clearing from caller side"),
        ("503", "34", "Service Unavailable", "Trunk congestion / carrier unavailable"),
        ("500", "41", "Server Error", "Upstream gateway or media path failure"),
        ("401", "21", "Unauthorized", "Carrier rejecting call (auth issue)"),
        ("403", "21", "Forbidden", "Call rejected by policy"),
        ("603", "21", "Decline", "Call explicitly rejected"),
    ]
    
    for sip, q850, desc, meaning in codes:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{sip:<6}{Colors.RESET} │ {Colors.GREEN}{q850:<6}{Colors.RESET} │ {Colors.WHITE}{desc:<25}{Colors.RESET} │ {Colors.CYAN}{meaning:<50}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*98}╝{Colors.RESET}")
    
    # Interactive lookup
    print(f"\n{Colors.WHITE}💡 Enter a SIP code to see details (or press Enter to skip): {Colors.RESET}", end="")
    code = input().strip()
    if code:
        from freepbx_log_analyzer import lookup_cause_code, format_cause_code
        info = lookup_cause_code(code)
        if info:
            print(f"\n{Colors.GREEN}✓ SIP {info['sip']}:{Colors.RESET}")
            print(f"  Q.850 Cause: {Colors.YELLOW}{info['q850']}{Colors.RESET}")
            print(f"  Description: {Colors.CYAN}{info['description']}{Colors.RESET}")
            print(f"  Asterisk: {Colors.MAGENTA}{info['asterisk_cause']}{Colors.RESET}")
            print(f"  Meaning: {Colors.WHITE}{info['meaning']}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}Code not found in mapping table{Colors.RESET}")


def show_common_issues_matrix():
    """Display common issues quick reference matrix"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*118}╗")
    print(f"║{' COMMON ISSUES QUICK REFERENCE MATRIX':^118}║")
    print(f"╠{'═'*118}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'Category':<25} │ {'Log Signature':<40} │ {'Impact':<45}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*118}╣{Colors.RESET}")
    
    issues = [
        ("Database Failure", "Failed to connect to database", "FreePBX cannot read config; calls may fail"),
        ("Trunk Offline", "Registration.*failed", "External calling over trunk will fail"),
        ("Auth Storm/Attack", "failed to authenticate", "Brute-force attacks or blocked endpoints"),
        ("Queue Abandon Spike", "Multiple ABANDON events", "Customer hang-ups, SLA breach"),
        ("Codec Negotiation", "Unable to negotiate codec", "Calls fail with fast busy"),
        ("RTP/Media Failure", "RTP Timeout", "One-way or no audio; call teardown"),
        ("Voicemail Storage", "Failed to create voicemail", "New voicemail drops fail to record"),
        ("Channel Ceiling", "channels count near limit", "New calls may be rejected"),
    ]
    
    for category, signature, impact in issues:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{category:<25}{Colors.RESET} │ {Colors.WHITE}{signature:<40}{Colors.RESET} │ {Colors.RED}{impact:<45}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*118}╝{Colors.RESET}")


def show_diagnostic_symptoms():
    """Display diagnostic symptoms quick guide"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*98}╗")
    print(f"║{' DIAGNOSTIC SYMPTOMS GUIDE':^98}║")
    print(f"╠{'═'*98}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║ {Colors.WHITE}{'Symptom':<35} │ {'Common Cause':<25} │ {'What It Means':<30}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═'*98}╣{Colors.RESET}")
    
    symptoms = [
        ("Immediate 'busy' tone", "486 / Q.850 17", "Phone in use or limit reached"),
        ("Rings then drops", "480 / Q.850 19", "User never answered"),
        ("Fails instantly", "404 / Q.850 1", "Wrong number / not found"),
        ("'Call failed' right away", "503 / Q.850 34", "Trunk congestion"),
        ("Long silence before drop", "408 / Q.850 18", "NAT/firewall/transport issue"),
        ("Works internally not outbound", "401/403 / Q.850 21", "Carrier rejecting call"),
        ("Audio dies mid-call", "500 / Q.850 41", "Gateway/media path failure"),
        ("Random inbound drops", "487 / Q.850 16", "Caller hung up normally"),
    ]
    
    for symptom, cause, meaning in symptoms:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.YELLOW}{symptom:<35}{Colors.RESET} │ {Colors.GREEN}{cause:<25}{Colors.RESET} │ {Colors.CYAN}{meaning:<30}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*98}╝{Colors.RESET}")


def show_playbooks_summary():
    """Display response playbooks summary"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' RESPONSE PLAYBOOKS SUMMARY':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    playbooks = [
        ("1. Database Connectivity Failure", [
            "Run: grep -i \"database.*fail|mysql.*error\" /var/log/asterisk/full | tail -20",
            "Check automated log analyzer for structured details",
            "Escalate with log snippet and concurrent GUI errors"
        ]),
        ("2. Trunk Offline / Registration Loss", [
            "Run: grep -E \"Registration.*failed|qualify.*Unreachable\" /var/log/asterisk/full",
            "Identify affected trunks and timestamps",
            "Notify carrier/network team for recovery"
        ]),
        ("3. Authentication Storm / SIP Attack", [
            "Run: grep -i \"failed.*auth|SECURITY\" /var/log/asterisk/full | tail -50",
            "If >20 failures, collect IP list for blocklisting",
            "Coordinate with security ops to block upstream"
        ]),
        ("4. Queue Abandon Spike", [
            "Run: tail -100 /var/log/asterisk/queue_log | grep -c ABANDON",
            "Use queue analyzer for current metrics",
            "Alert supervisor with wait times and staffing needs"
        ]),
    ]
    
    for title, steps in playbooks:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.GREEN}{Colors.BOLD}{title}{Colors.RESET}")
        for i, step in enumerate(steps, 1):
            print(f"{Colors.CYAN}║{Colors.RESET}   {Colors.YELLOW}{i}.{Colors.RESET} {Colors.WHITE}{step[:70]}{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═'*78}╣{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}")


def run_full_diagnostic():
    """Run comprehensive Asterisk diagnostic with formatted table output"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}")
    print(f"  🔧 Full Asterisk & FreePBX Diagnostic")
    print(f"{'='*80}{Colors.RESET}\n")
    
    print(f"{Colors.YELLOW}Collecting system information...{Colors.RESET}\n")
    
    # System Information Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' SYSTEM INFORMATION':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    # Hostname
    rc, hostname, _ = run(["hostname"])
    hostname = hostname.strip() or "Unknown"
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Hostname:{Colors.RESET} {Colors.GREEN}{hostname:<64}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Uptime
    rc, uptime_out, _ = run(["uptime", "-p"])
    uptime_str = uptime_out.strip() or "Unknown"
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Uptime:{Colors.RESET} {Colors.YELLOW}{uptime_str:<66}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Memory
    rc, mem_out, _ = run(["free", "-h"])
    mem_lines = mem_out.strip().split('\n')
    if len(mem_lines) > 1:
        mem_info = mem_lines[1].split()
        if len(mem_info) >= 3:
            total_mem = mem_info[1]
            used_mem = mem_info[2]
            mem_display = f"Used: {used_mem} / Total: {total_mem}"
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Memory:{Colors.RESET} {Colors.CYAN}{mem_display:<67}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Disk usage
    rc, disk_out, _ = run(["df", "-h", "/"])
    disk_lines = disk_out.strip().split('\n')
    if len(disk_lines) > 1:
        disk_info = disk_lines[1].split()
        if len(disk_info) >= 5:
            disk_display = f"Used: {disk_info[2]} / Total: {disk_info[1]} ({disk_info[4]})"
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Disk (/):{Colors.RESET} {Colors.CYAN}{disk_display:<65}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Asterisk Information Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' ASTERISK STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    # Asterisk version
    rc, version_out, _ = run(["asterisk", "-rx", "core show version"])
    if rc == 0:
        version_lines = version_out.strip().split('\n')
        if version_lines:
            version = version_lines[0].replace("Asterisk ", "").strip()[:60]
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Version:{Colors.RESET} {Colors.GREEN}{version:<66}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # Active channels
    rc, channels_out, _ = run(["asterisk", "-rx", "core show channels count"])
    active_calls = "0"
    active_channels = "0"
    for line in channels_out.split('\n'):
        if 'active call' in line.lower():
            parts = line.split()
            if parts and parts[0].isdigit():
                active_calls = parts[0]
        elif 'active channel' in line.lower():
            parts = line.split()
            if parts and parts[0].isdigit():
                active_channels = parts[0]
    
    call_color = Colors.GREEN if active_calls == "0" else Colors.YELLOW
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Active Calls:{Colors.RESET} {call_color}{active_calls:<63}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Active Channels:{Colors.RESET} {call_color}{active_channels:<59}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    # PJSIP Endpoints
    rc, endpoints_out, _ = run(["asterisk", "-rx", "pjsip show endpoints"])
    endpoint_count = 0
    online_count = 0
    for line in endpoints_out.split('\n'):
        if line.strip() and not line.startswith('Endpoint') and not line.startswith('===') and not line.startswith('Objects'):
            endpoint_count += 1
            if 'Avail' in line or 'online' in line.lower():
                online_count += 1
    
    print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}PJSIP Endpoints:{Colors.RESET} {Colors.CYAN}Total: {endpoint_count}  │  Online: {Colors.GREEN}{online_count}{Colors.RESET}{' '*40}{Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Services Status Table
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' SERVICES STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    services = [
        ("asterisk", "Asterisk PBX"),
        ("httpd", "Apache Web Server"),
        ("mariadb", "MariaDB Database"),
        ("php-fpm", "PHP-FPM"),
        ("crond", "Cron Daemon")
    ]
    
    for service_name, display_name in services:
        rc, _, _ = run(["systemctl", "is-active", service_name])
        status = "RUNNING" if rc == 0 else "STOPPED"
        status_color = Colors.GREEN if rc == 0 else Colors.RED
        status_icon = "●" if rc == 0 else "○"
        
        print(f"{Colors.CYAN}║{Colors.RESET} {status_color}{status_icon}{Colors.RESET} {Colors.WHITE}{display_name:<35}{Colors.RESET} {status_color}{status:<36}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Database Status
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' DATABASE STATUS':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    # Check database connectivity
    rc, db_out, _ = run(["mysql", "-NBe", "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='asterisk';"])
    if rc == 0:
        table_count = db_out.strip()
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Asterisk DB Status:{Colors.RESET} {Colors.GREEN}Connected{Colors.RESET}{' '*52}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Tables in asterisk DB:{Colors.RESET} {Colors.CYAN}{table_count:<54}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}Asterisk DB Status:{Colors.RESET} {Colors.RED}Connection Failed{Colors.RESET}{' '*45}{Colors.CYAN}║{Colors.RESET}")
    
    # Recent CDRs
    rc, cdr_out, _ = run(["mysql", "-NBe", "SELECT COUNT(*) FROM asteriskcdrdb.cdr WHERE calldate > DATE_SUB(NOW(), INTERVAL 24 HOUR);"])
    if rc == 0:
        recent_calls = cdr_out.strip()
        print(f"{Colors.CYAN}║{Colors.RESET} {Colors.WHITE}CDRs (Last 24h):{Colors.RESET} {Colors.YELLOW}{recent_calls:<58}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    # Module Status
    print(f"{Colors.CYAN}{Colors.BOLD}╔{'═'*78}╗")
    print(f"║{' ASTERISK MODULES (Key Modules)':^78}║")
    print(f"╠{'═'*78}╣{Colors.RESET}")
    
    key_modules = [
        "chan_pjsip.so",
        "res_pjsip.so",
        "chan_dahdi.so",
        "app_voicemail.so",
        "app_queue.so",
        "cdr_mysql.so"
    ]
    
    rc, modules_out, _ = run(["asterisk", "-rx", "module show"])
    loaded_modules = set()
    for line in modules_out.split('\n'):
        for mod in key_modules:
            if mod in line:
                loaded_modules.add(mod)
    
    for mod in key_modules:
        if mod in loaded_modules:
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.GREEN}✓{Colors.RESET} {Colors.WHITE}{mod:<70}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
        else:
            print(f"{Colors.CYAN}║{Colors.RESET} {Colors.RED}✗{Colors.RESET} {Colors.WHITE}{mod:<70}{Colors.RESET} {Colors.CYAN}║{Colors.RESET}")
    
    print(f"{Colors.CYAN}╚{'═'*78}╝{Colors.RESET}\n")
    
    print(f"{Colors.GREEN}{Colors.BOLD}✓ Diagnostic complete!{Colors.RESET}\n")


def run_full_diagnostic_legacy():
    """Run the original shell script diagnostic (legacy method)"""
    diag = "/usr/local/bin/asterisk-full-diagnostic.sh"
    if not os.path.isfile(diag):
        print("Diagnostic script not found at", diag)
    else:
        print("\nRunning full diagnostic (this may take ~10-30s)...\n")
        rc, out, err = run([diag])
        # The script prints its own output


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


def run_enhanced_log_analysis_menu():
    """Interactive enhanced log analysis menu with dmesg, journalctl, and regex search."""
    if not os.path.isfile(LOG_ANALYZER_SCRIPT):
        print(f"{Colors.RED}❌ Log analyzer tool not found.{Colors.RESET}")
        return
    
    while True:
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔍 Enhanced Log Analysis{' ' * 52}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Standard log analysis (Asterisk full log){' ' * 31}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Comprehensive analysis (Asterisk + system + patterns){' ' * 21}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Kernel log analysis (dmesg){' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} System journal analysis (journalctl){' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Search Asterisk logs with regex{' ' * 41}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Search common Asterisk issue patterns{' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} Evaluate error codes (SIP/Q.850 mapping){' ' * 32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Look up specific SIP code{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED}  9){Colors.WHITE} Return to main menu{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()
        
        choice = input(f"{Colors.YELLOW}Choose analysis option (1-9): {Colors.RESET}").strip()
        
        if choice == "1":
            hours = input(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
            run(["python3", LOG_ANALYZER_SCRIPT, "--hours", hours])
        elif choice == "2":
            hours = input(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
            run(["python3", LOG_ANALYZER_SCRIPT, "--comprehensive", "--hours", hours])
        elif choice == "3":
            run(["python3", LOG_ANALYZER_SCRIPT, "--dmesg"])
        elif choice == "4":
            hours = input(f"{Colors.YELLOW}Analyze last N hours (default: 1): {Colors.RESET}").strip() or "1"
            run(["python3", LOG_ANALYZER_SCRIPT, "--journal", "--hours", hours])
        elif choice == "5":
            pattern = input(f"{Colors.YELLOW}Enter regex pattern to search: {Colors.RESET}").strip()
            if pattern:
                log_file = input(f"{Colors.YELLOW}Log file (default: /var/log/asterisk/full): {Colors.RESET}").strip()
                log_file = log_file or "/var/log/asterisk/full"
                run(["python3", LOG_ANALYZER_SCRIPT, "--grep", pattern, "--log-file", log_file])
        elif choice == "6":
            run(["python3", LOG_ANALYZER_SCRIPT, "--search-patterns"])
        elif choice == "7":
            run(["python3", LOG_ANALYZER_SCRIPT, "--codes-only"])
        elif choice == "8":
            code = input(f"{Colors.YELLOW}Enter SIP code to lookup: {Colors.RESET}").strip()
            if code:
                run(["python3", LOG_ANALYZER_SCRIPT, "--lookup", code])
        elif choice == "9":
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-9.{Colors.RESET}")
        
        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        input()


def run_cdr_analysis_menu():
    """Interactive CDR/CEL call log analysis menu."""
    if not os.path.isfile(CDR_ANALYZER_SCRIPT):
        print(f"{Colors.RED}❌ CDR analyzer tool not found.{Colors.RESET}")
        return
    
    while True:
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 CDR/CEL Call Log Analysis{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Comprehensive call analysis{' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Call statistics summary{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Top callers{' ' * 62}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Top destinations{' ' * 57}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Call distribution by hour{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Disposition breakdown{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} Failed/busy calls analysis{' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Trunk usage analysis{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} Call duration distribution{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Export calls to JSON{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 11){Colors.WHITE} Return to main menu{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()
        
        choice = input(f"{Colors.YELLOW}Choose analysis option (1-11): {Colors.RESET}").strip()
        
        hours = None
        if choice in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']:
            hours = input(f"{Colors.YELLOW}Analyze last N hours (default: 24): {Colors.RESET}").strip() or "24"
        
        if choice == "1":
            run(["python3", CDR_ANALYZER_SCRIPT, "--comprehensive", "--hours", hours])
        elif choice == "2":
            run(["python3", CDR_ANALYZER_SCRIPT, "--statistics", "--hours", hours])
        elif choice == "3":
            run(["python3", CDR_ANALYZER_SCRIPT, "--top-callers", "--hours", hours])
        elif choice == "4":
            run(["python3", CDR_ANALYZER_SCRIPT, "--top-destinations", "--hours", hours])
        elif choice == "5":
            run(["python3", CDR_ANALYZER_SCRIPT, "--by-hour", "--hours", hours])
        elif choice == "6":
            run(["python3", CDR_ANALYZER_SCRIPT, "--dispositions", "--hours", hours])
        elif choice == "7":
            run(["python3", CDR_ANALYZER_SCRIPT, "--failed", "--hours", hours])
        elif choice == "8":
            run(["python3", CDR_ANALYZER_SCRIPT, "--trunk-usage", "--hours", hours])
        elif choice == "9":
            run(["python3", CDR_ANALYZER_SCRIPT, "--duration-dist", "--hours", hours])
        elif choice == "10":
            filename = input(f"{Colors.YELLOW}Output filename (default: auto-generated): {Colors.RESET}").strip()
            if filename:
                run(["python3", CDR_ANALYZER_SCRIPT, "--export-json", filename, "--hours", hours])
            else:
                run(["python3", CDR_ANALYZER_SCRIPT, "--export-json", "/tmp/cdr_export.json", "--hours", hours])
        elif choice == "11":
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-11.{Colors.RESET}")
        
        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        input()


def run_network_diagnostics_menu():
    """Interactive network diagnostics menu."""
    if not os.path.isfile(NETWORK_DIAGNOSTICS_SCRIPT):
        print(f"{Colors.RED}❌ Network diagnostics tool not found.{Colors.RESET}")
        return
    
    while True:
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🌐 Network Diagnostics & Packet Capture{' ' * 37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  1){Colors.WHITE} Show network interfaces (ip addr / ifconfig){' ' * 28}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  2){Colors.WHITE} Show routing table (ip route / route){' ' * 35}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  3){Colors.WHITE} Show ARP table (address resolution){' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  4){Colors.WHITE} Show network statistics (netstat / ss){' ' * 33}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  5){Colors.WHITE} Ping test (connectivity check){' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  6){Colors.WHITE} Traceroute (path analysis){' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  7){Colors.WHITE} DNS lookup (dig / nslookup){' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  8){Colors.WHITE} Capture packets with tcpdump{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN}  9){Colors.WHITE} Launch sngrep (SIP packet analyzer){' ' * 37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 10){Colors.WHITE} Analyze SIP traffic (port 5060){' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 11){Colors.WHITE} Monitor RTP traffic (audio streams){' ' * 38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 12){Colors.WHITE} Show Asterisk SIP peers{' ' * 49}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 13){Colors.WHITE} Show active Asterisk channels{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.GREEN} 14){Colors.WHITE} Run comprehensive network diagnostic{' ' * 38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.RED} 15){Colors.WHITE} Return to main menu{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        print()
        
        choice = input(f"{Colors.YELLOW}Choose diagnostic option (1-15): {Colors.RESET}").strip()
        
        if choice == "1":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--interfaces"])
        elif choice == "2":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--routing"])
        elif choice == "3":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--arp"])
        elif choice == "4":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--netstat"])
        elif choice == "5":
            host = input(f"{Colors.YELLOW}Enter host to ping (default: 8.8.8.8): {Colors.RESET}").strip() or "8.8.8.8"
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--ping", host])
        elif choice == "6":
            host = input(f"{Colors.YELLOW}Enter host for traceroute: {Colors.RESET}").strip()
            if host:
                run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--traceroute", host])
        elif choice == "7":
            domain = input(f"{Colors.YELLOW}Enter domain for DNS lookup: {Colors.RESET}").strip()
            if domain:
                run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--dns", domain])
        elif choice == "8":
            duration = input(f"{Colors.YELLOW}Capture duration in seconds (default: 60): {Colors.RESET}").strip() or "60"
            port = input(f"{Colors.YELLOW}Filter by port (optional, press Enter to skip): {Colors.RESET}").strip()
            host = input(f"{Colors.YELLOW}Filter by host (optional, press Enter to skip): {Colors.RESET}").strip()
            cmd = ["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--tcpdump", "--duration", duration]
            if port:
                cmd.extend(["--port", port])
            if host:
                cmd.extend(["--host", host])
            run(cmd)
        elif choice == "9":
            print(f"{Colors.CYAN}Launching sngrep... (Press 'q' to quit){Colors.RESET}\n")
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sngrep"])
        elif choice == "10":
            duration = input(f"{Colors.YELLOW}Capture duration in seconds (default: 30): {Colors.RESET}").strip() or "30"
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--sip-traffic", "--duration", duration])
        elif choice == "11":
            duration = input(f"{Colors.YELLOW}Monitor duration in seconds (default: 30): {Colors.RESET}").strip() or "30"
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--rtp-traffic", "--duration", duration])
        elif choice == "12":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-peers"])
        elif choice == "13":
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--asterisk-channels"])
        elif choice == "14":
            print(f"{Colors.CYAN}Running comprehensive network diagnostic...{Colors.RESET}\n")
            run(["python3", NETWORK_DIAGNOSTICS_SCRIPT, "--comprehensive"])
        elif choice == "15":
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-15.{Colors.RESET}")
        
        print(f"\n{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}")
        input()


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
        print(menu_line("14", "📚 Error Map & Quick Reference"))
        print(menu_line("15", "🌐 Network Diagnostics & Packet Capture"))
        print(menu_line("16", "🔍 Enhanced Log Analysis (dmesg/journal/regex)"))
        print(menu_line("17", "📞 CDR/CEL Call Log Analysis"))
        print(menu_line("18", "Quit"))
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
            run_full_diagnostic()
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

        elif choice == "13":
            run_log_analysis()

        elif choice == "14":
            show_error_map_quick_reference()

        elif choice == "15":
            run_network_diagnostics_menu()

        elif choice == "16":
            run_enhanced_log_analysis_menu()

        elif choice == "17":
            run_cdr_analysis_menu()

        elif choice == "18":
            print("Bye.")
            break
        else:
            print(Colors.RED + "Invalid choice." + Colors.RESET)
            print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
            input()

if __name__ == "__main__":
    main()
