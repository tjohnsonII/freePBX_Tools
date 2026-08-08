

#!/usr/bin/env python3
"""
freePBX Call Simulator
----------------------
Generate and execute Asterisk call files to test call flow routing.
Monitors call outcomes and validates against expected behavior.

VARIABLE MAP (Key Instance Variables)
server_ip        : Target FreePBX/Asterisk server IP address
ssh_user         : SSH username for remote server access
spool_dir        : Path to Asterisk outgoing call file spool directory
tmp_dir          : Temporary directory for staging call files
asterisk_user    : System user that owns Asterisk processes/files
test_results     : List of dictionaries storing results of each test
debug            : Boolean flag to enable/disable debug output
is_local_execution: True if running on the same host as server_ip

Key Method Arguments:
channel           : Asterisk channel string (e.g., Local/1234@from-internal)
caller_id         : Caller ID to display for the simulated call
destination       : Extension or number to call (or ring)
context           : Asterisk dialplan context (default: from-internal)
priority          : Dialplan priority (default: 1)
wait_time         : Seconds to wait before call fails
max_retries       : Number of call retries
application       : Optional Asterisk application (e.g., Voicemail, Playback)
data              : Data for the application (e.g., mailbox, sound file)
archive           : Whether to archive the call file after execution
call_id           : Unique identifier for each simulated call


See function docstrings for additional details on arguments and return values.

        FUNCTION MAP (Major Methods)
        ---------------------------
        FreePBXCallSimulator:
                * __init__                  : Initialize simulator with server, user, and config
                * debug_print               : Print colorized debug/info output if enabled
                * _is_local_execution       : Detect if running on local or remote server
                * _run_command              : Run shell command locally or via SSH
                * create_call_file          : Generate an Asterisk call file with given parameters
                * execute_call_file         : Upload, set permissions, and trigger call file execution
                * _get_recent_call_logs     : Fetch recent Asterisk log entries for a call
                * simulate_did_call         : Simulate an incoming call to a DID (optionally force destination)
                * test_extension_call       : Simulate a call to a specific extension
                * test_voicemail_call       : Simulate a call directly to a voicemail box
                * test_playback_application : Simulate a call that plays a sound file (Playback app)
                * run_comprehensive_test_suite: Run a full suite of DID, extension, voicemail, playback, ring group, and queue tests
                * generate_test_summary     : Print and save a summary report of all test results

        main
                * CLI entry point, parses arguments and dispatches to test methods
"""
# (Removed duplicate function map lines; see docstring above)
# Standard library imports
import os      # File and directory operations
import sys     # System-specific parameters and functions
import time    # Time-related functions
import subprocess  # Run shell commands
import tempfile    # Temporary file/directory creation
import argparse    # Command-line argument parsing
from datetime import datetime, timedelta  # Date/time handling
import json     # JSON encoding/decoding
import socket   # Network interface and IP handling
import re       # Regular expressions


# Terminal color codes for pretty output
class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'      # Info
    GREEN = '\033[92m'     # Success
    YELLOW = '\033[93m'    # Warning
    RED = '\033[91m'       # Error
    BLUE = '\033[94m'      # Response
    MAGENTA = '\033[95m'   # Command
    WHITE = '\033[97m'     # Default
    BOLD = '\033[1m'       # Bold
    RESET = '\033[0m'      # Reset


# Main simulator class for generating and executing test calls
class FreePBXCallSimulator:
    def __init__(self, server_ip=None, ssh_user="123net"):
        """
        Initialize the call simulator.
        Args:
            server_ip (str): Target FreePBX/Asterisk server IP. If not given,
                defaults to THIS box's own IP — a tool deployed to a given
                PBX must test that PBX by default, not silently target
                whichever server it happened to be developed against.
            ssh_user (str): SSH username for remote execution.
        """
        self.server_ip = server_ip or self._detect_local_ip()
        self.ssh_user = ssh_user                      # SSH user
        self.spool_dir = "/var/spool/asterisk/outgoing"  # Asterisk call file spool
        self.tmp_dir = "/tmp"                        # Temp directory for file staging
        self.asterisk_user = "asterisk"              # Asterisk system user
        self.test_results = []                        # Store test results
        self.debug = False                            # Enable debug output when True
        self.is_local_execution = self._is_local_execution()  # Detect local/remote

    def _detect_local_ip(self):
        """Best-effort detection of this box's own primary IP, used as the
        default test target when none is explicitly given."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            try:
                return socket.gethostbyname(socket.gethostname())
            except OSError:
                return "127.0.0.1"


    def debug_print(self, message, level="INFO"):
        """
        Print debug messages with colorized level indicators.
        Args:
            message (str): The message to print.
            level (str): Log level (INFO, SUCCESS, WARNING, ERROR, COMMAND, RESPONSE).
        """
        if not self.debug:
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level_colors = {
            "INFO": Colors.CYAN,
            "SUCCESS": Colors.GREEN,
            "WARNING": Colors.YELLOW,
            "ERROR": Colors.RED,
            "COMMAND": Colors.MAGENTA,
            "RESPONSE": Colors.BLUE
        }
        color = level_colors.get(level, Colors.WHITE)
        level_icon = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "COMMAND": "🔧",
            "RESPONSE": "📥"
        }.get(level, "•")
        print(f"{Colors.WHITE}[{timestamp}]{Colors.RESET} {color}{Colors.BOLD}{level_icon} {level}:{Colors.RESET} {color}{message}{Colors.RESET}")
        

    def _is_local_execution(self):
        """
        Check if we're running on the same server as the target.
        Returns True if the script is running on the same host as the target server_ip.
        Checks every IP on every local interface (via `hostname -I`), not just
        hostname resolution or the single interface used for outbound
        routing — a multi-homed box (e.g. separate management/VoIP NICs)
        needs every interface checked, or this silently falls through to
        SSHing to itself and prompting for a password mid-test.
        """
        try:
            local_ips = {"127.0.0.1", "localhost"}
            try:
                local_ips.add(socket.gethostbyname(socket.gethostname()))
            except OSError:
                pass
            try:
                out = subprocess.run(["hostname", "-I"], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, universal_newlines=True, timeout=5)
                if out.returncode == 0:
                    local_ips.update(out.stdout.split())
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ips.add(s.getsockname()[0])
                s.close()
            except OSError:
                pass
            return self.server_ip in local_ips
        except OSError:
            return False
    

    def _run_command(self, command, timeout=10):
        """
        Run a shell command locally or via SSH based on execution context.
        Args:
            command (str): The shell command to execute.
            timeout (int): Timeout in seconds.
        Returns:
            subprocess.CompletedProcess: The result object.
        """
        execution_mode = "LOCAL" if self.is_local_execution else "SSH"
        self.debug_print(f"{execution_mode} Command: {command}", "COMMAND")
        start_time = time.time()
        try:
            if self.is_local_execution:
                # Running locally, execute directly
                result = subprocess.run(
                    command, shell=True, 
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                    universal_newlines=True, timeout=timeout
                )
            else:
                # Running remotely, use SSH
                self.debug_print(f"SSH Connection: {self.ssh_user}@{self.server_ip}", "INFO")
                result = subprocess.run([
                    "ssh", f"{self.ssh_user}@{self.server_ip}", command
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                   universal_newlines=True, timeout=timeout)
            elapsed = time.time() - start_time
            if result.returncode == 0:
                self.debug_print(f"Command succeeded in {elapsed:.2f}s", "SUCCESS")
                if result.stdout.strip():
                    self.debug_print(f"STDOUT: {result.stdout.strip()[:200]}", "RESPONSE")
            else:
                self.debug_print(f"Command failed with return code {result.returncode} after {elapsed:.2f}s", "ERROR")
                if result.stderr.strip():
                    self.debug_print(f"STDERR: {result.stderr.strip()[:200]}", "ERROR")
            
            return result
            
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            self.debug_print(f"Command timed out after {elapsed:.2f}s", "ERROR")
            raise
        except Exception as e:
            elapsed = time.time() - start_time
            self.debug_print(f"Command exception after {elapsed:.2f}s: {str(e)}", "ERROR")
            raise

    def _query_ring_group_numbers(self):
        """Discover configured ring group numbers on the target PBX so the
        comprehensive suite exercises what's actually configured there,
        rather than a hardcoded list. Uses the same local/SSH execution
        path as everything else in this class."""
        try:
            result = self._run_command(
                'mysql -BN --user=root asterisk -e "SELECT grpnum FROM ringgroups;" 2>/dev/null',
                timeout=10
            )
        except Exception:
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]

    def _query_queue_extensions(self):
        """Discover configured queue extensions on the target PBX."""
        try:
            result = self._run_command(
                'mysql -BN --user=root asterisk -e "SELECT extension FROM queues_config;" 2>/dev/null',
                timeout=10
            )
        except Exception:
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]

    def _query_cdr(self, sql):
        """Run a query against asteriskcdrdb via the same local/SSH execution
        path as everything else in this class."""
        try:
            result = self._run_command(
                f'mysql -BN --user=root asteriskcdrdb -e "{sql}" 2>/dev/null',
                timeout=10
            )
        except Exception:
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [ln.split('\t') for ln in result.stdout.strip().splitlines() if ln.strip()]

    def _find_cdr_for_call(self, channel, since_dt, max_wait=20, poll_interval=3):
        """Poll CDR for the record this test call produced. The spool-file
        checks in execute_call_file() only confirm Asterisk *consumed* the
        .call file, not that a call was actually placed and logged — CDR is
        the authoritative signal a technician actually cares about. Polls
        rather than checking once because Asterisk doesn't write the CDR
        row until the call hangs up, which for an unanswered ring group/
        queue/extension can be the full configured ring time away.
        Returns the matching row as a dict, or None if nothing showed up
        within max_wait seconds."""
        cols = ["calldate", "src", "dst", "disposition", "duration", "billsec", "uniqueid", "linkedid"]
        since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")
        sql = (f"SELECT {','.join(cols)} FROM cdr "
               f"WHERE channel LIKE '{channel}%' AND calldate >= '{since_str}' "
               f"ORDER BY calldate ASC LIMIT 1;")
        deadline = time.time() + max_wait
        while True:
            rows = self._query_cdr(sql)
            if rows:
                return dict(zip(cols, rows[0]))
            if time.time() >= deadline:
                return None
            time.sleep(poll_interval)

    def create_call_file(self, channel, caller_id, destination, context="from-internal",
                        priority=1, wait_time=30, max_retries=2, application=None, 
                        data=None, archive=False):
        """
        Create an Asterisk call file with specified parameters.
        Args:
            channel (str): Channel string (e.g., Local/1234@from-internal)
            caller_id (str): Caller ID to display
            destination (str): Extension or number to call
            context (str): Dialplan context
            priority (int): Dialplan priority
            wait_time (int): Wait time before call fails
            max_retries (int): Number of retries
            application (str): Optional Asterisk application
            data (str): Data for application
            archive (bool): Whether to archive the call file
        Returns:
            str: The call file content
        """
        
        self.debug_print(f"Creating call file for {channel} -> {destination}", "INFO")
        self.debug_print(f"Caller ID: {caller_id}, Context: {context}", "INFO")
        
        call_file_content = []
        
        # Required fields
        call_file_content.append(f"Channel: {channel}")
        call_file_content.append(f"CallerID: {caller_id}")
        call_file_content.append(f"WaitTime: {wait_time}")
        call_file_content.append(f"MaxRetries: {max_retries}")
        
        # Destination - either extension or application
        if application and data:
            self.debug_print(f"Using Application: {application}, Data: {data}", "INFO")
            call_file_content.append(f"Application: {application}")
            call_file_content.append(f"Data: {data}")
        else:
            self.debug_print(f"Using Extension: {destination}, Priority: {priority}", "INFO")
            call_file_content.append(f"Context: {context}")
            call_file_content.append(f"Extension: {destination}")
            call_file_content.append(f"Priority: {priority}")
        
        # Optional fields
        if archive:
            call_file_content.append("Archive: yes")
        else:
            call_file_content.append("Archive: no")
            
        # Add timestamp for tracking
        call_file_content.append(f"# Generated: {datetime.now().isoformat()}")
        call_file_content.append(f"# Test case: {channel} -> {destination}")
        
        content = "\n".join(call_file_content) + "\n"
        self.debug_print(f"Call file created ({len(content)} bytes)", "SUCCESS")
        
        return content
    
    def execute_call_file(self, call_content, call_id=None, channel=None, cdr_wait=20):
        """
        Execute a call file on the remote FreePBX server.
        Handles file creation, permission setting, moving to spool, and log retrieval.
        Args:
            call_content (str): The call file content.
            call_id (str): Optional unique call identifier.
            channel (str): The origination channel this call file uses (e.g.
                "Local/1002@from-internal") — when given, used to poll CDR
                for the record this specific call produces, which is the
                real signal that the call was actually placed and logged,
                not just that Asterisk consumed the .call file.
            cdr_wait (int): Max seconds to poll CDR for a match. Should be at
                least the call file's own WaitTime plus a few seconds of
                margin for Asterisk to write the CDR row after hangup.
        Returns:
            dict: Call execution results and logs.
        """
        
        if not call_id:
            call_id = f"test_{int(time.time())}"
        
        temp_file = f"/tmp/call_{call_id}"
        target_file = f"{self.spool_dir}/call_{call_id}.call"
        
        print(f"{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🚀 EXECUTING CALL SIMULATION {Colors.RESET}{Colors.CYAN}                               ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 68}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.WHITE}  Call ID: {Colors.GREEN}{Colors.BOLD}{call_id:<56}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        self.debug_print(f"Temporary file: {temp_file}", "INFO")
        self.debug_print(f"Target spool file: {target_file}", "INFO")
        
        try:
            # Create call file on remote server
            self.debug_print("Creating call file on server...", "INFO")
            cmd = f'cat > {temp_file} << "EOF"\n{call_content}EOF'
            result = self._run_command(cmd, timeout=30)
            
            if result.returncode != 0:
                self.debug_print(f"Failed to create call file", "ERROR")
                return {
                    'success': False,
                    'error': f"Failed to create call file: {result.stderr}",
                    'call_id': call_id
                }
            
            # Set proper ownership and permissions for asterisk user
            self.debug_print(f"Setting ownership to {self.asterisk_user}...", "INFO")
            chown_cmd = f"chown {self.asterisk_user}:{self.asterisk_user} {temp_file}"
            chown_result = self._run_command(chown_cmd, timeout=10)
            
            if chown_result.returncode != 0:
                print(f"   {Colors.YELLOW}⚠️  Warning: Could not set ownership: {chown_result.stderr}{Colors.RESET}")
                self.debug_print("Ownership change failed (may not have permissions)", "WARNING")
            
            # Set proper permissions (readable by asterisk)
            self.debug_print("Setting file permissions (644)...", "INFO")
            chmod_cmd = f"chmod 644 {temp_file}"
            chmod_result = self._run_command(chmod_cmd, timeout=10)
            
            if chmod_result.returncode != 0:
                print(f"   {Colors.YELLOW}⚠️  Warning: Could not set permissions: {chmod_result.stderr}{Colors.RESET}")
                self.debug_print("Permission change failed", "WARNING")
            
            # Verify file exists and has correct ownership before moving
            self.debug_print("Verifying file before move...", "INFO")
            verify_cmd = f"ls -l {temp_file}"
            verify_result = self._run_command(verify_cmd, timeout=10)
            
            if verify_result.returncode == 0:
                print(f"   {Colors.GREEN}📋 File created: {verify_result.stdout.strip()}{Colors.RESET}")
                self.debug_print(f"File verified: {verify_result.stdout.strip()}", "SUCCESS")
            
            # Move to spool directory (this triggers the call)
            # Using mv ensures file is moved (not copied) as required by Asterisk
            self.debug_print("Moving call file to spool directory (this triggers call)...", "INFO")
            call_started_at = datetime.now()
            move_cmd = f"mv {temp_file} {target_file}"
            move_result = self._run_command(move_cmd, timeout=10)
            
            if move_result.returncode != 0:
                self.debug_print("Failed to move file to spool directory", "ERROR")
                return {
                    'success': False,
                    'error': f"Failed to move call file: {move_result.stderr}",
                    'call_id': call_id
                }
            
            # Verify the file was moved successfully to spool directory
            self.debug_print("Verifying file in spool directory...", "INFO")
            verify_spool_cmd = f"ls -l {target_file}"
            verify_spool_result = self._run_command(verify_spool_cmd, timeout=10)
            
            if verify_spool_result.returncode == 0:
                print(f"   {Colors.GREEN}📁 Call file moved to spool directory{Colors.RESET}")
                print(f"   {Colors.CYAN}📋 Spool file: {verify_spool_result.stdout.strip()}{Colors.RESET}")
                self.debug_print("Call file successfully placed in spool - Asterisk will process it", "SUCCESS")
            else:
                # Asterisk's spool watcher can pick up and consume a .call file
                # within milliseconds of it landing — the file already being
                # gone this fast is a GOOD sign (Asterisk grabbed it
                # immediately), not a failure. The "processed" check below
                # (after a short wait) is what actually confirms this.
                print(f"   {Colors.GREEN}📁 Call file already claimed by Asterisk (processed instantly){Colors.RESET}")
                self.debug_print("Spool file already gone — Asterisk likely processed it immediately", "INFO")
            
            # Verify temp file was removed (successful move)
            self.debug_print("Verifying temp file was removed...", "INFO")
            temp_check_cmd = f"ls {temp_file} 2>/dev/null || echo 'TEMP_REMOVED'"
            temp_check_result = self._run_command(temp_check_cmd, timeout=10)
            
            if "TEMP_REMOVED" in temp_check_result.stdout:
                print(f"   {Colors.GREEN}✅ Temporary file properly removed{Colors.RESET}")
                self.debug_print("Temp file successfully removed", "SUCCESS")
            else:
                print(f"   {Colors.YELLOW}⚠️  Warning: Temporary file still exists{Colors.RESET}")
                self.debug_print("Temp file still exists (unexpected)", "WARNING")
            
            # Wait a moment for Asterisk to process
            self.debug_print("Waiting for Asterisk to process call file...", "INFO")
            print(f"   {Colors.BLUE}⏳ Waiting for Asterisk to process (2s)...{Colors.RESET}")
            time.sleep(2)
            
            # Check if file was processed (should be gone from spool)
            self.debug_print("Checking if Asterisk processed the file...", "INFO")
            check_cmd = f"ls {target_file} 2>/dev/null || echo 'FILE_PROCESSED'"
            check_result = self._run_command(check_cmd, timeout=10)
            
            processed = "FILE_PROCESSED" in check_result.stdout
            
            if processed:
                print(f"   {Colors.GREEN}✅ Call file processed by Asterisk{Colors.RESET}")
                self.debug_print("File successfully processed by Asterisk", "SUCCESS")
            else:
                print(f"   {Colors.YELLOW}⚠️  Call file still in spool (may be processing){Colors.RESET}")
                self.debug_print("File still in spool (processing may be delayed)", "WARNING")
            
            # Get call logs for this time period
            self.debug_print("Fetching recent call logs...", "INFO")
            call_logs = self._get_recent_call_logs(call_id)

            if call_logs:
                print(f"   {Colors.CYAN}📜 Retrieved {len(call_logs)} log entries{Colors.RESET}")
                self.debug_print(f"Found {len(call_logs)} log entries", "SUCCESS")

            # Confirm the call actually shows up in CDR — the spool-file
            # checks above only prove Asterisk consumed the .call file, not
            # that a call was actually placed and recorded. CDR is the
            # authoritative signal.
            cdr_record = None
            if channel:
                self.debug_print(f"Polling CDR for this call (up to {cdr_wait}s)...", "INFO")
                print(f"   {Colors.BLUE}⏳ Checking CDR for this call's record (up to {cdr_wait}s)...{Colors.RESET}")
                cdr_record = self._find_cdr_for_call(channel, call_started_at, max_wait=cdr_wait)
                if cdr_record:
                    disp = cdr_record.get('disposition', '?')
                    disp_color = Colors.GREEN if disp == 'ANSWERED' else Colors.YELLOW
                    print(f"   {Colors.GREEN}✅ Found in CDR:{Colors.RESET} {cdr_record.get('calldate')}  "
                          f"{cdr_record.get('src')} -> {cdr_record.get('dst')}  "
                          f"{disp_color}{disp}{Colors.RESET}  "
                          f"duration={cdr_record.get('duration')}s billsec={cdr_record.get('billsec')}s")
                    self.debug_print(f"CDR record found: {cdr_record}", "SUCCESS")
                    linkedid = cdr_record.get('linkedid')
                    if linkedid and self.is_local_execution:
                        leg_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "freepbx_call_leg_analyzer.py")
                        if os.path.isfile(leg_script):
                            print(f"   {Colors.CYAN}📜 Full CEL/call-leg story:{Colors.RESET} "
                                  f"python3 {leg_script} --linkedid {linkedid}")
                else:
                    print(f"   {Colors.RED}❌ No matching CDR record found after {cdr_wait}s — "
                          f"the call may not have actually been placed/logged.{Colors.RESET}")
                    self.debug_print("No CDR record found within poll window", "WARNING")

            print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}\n")

            return {
                'success': True,
                'processed': processed,
                'call_id': call_id,
                'logs': call_logs,
                'cdr_confirmed': bool(cdr_record) if channel else None,
                'cdr_record': cdr_record,
                'timestamp': datetime.now().isoformat()
            }
            
        except subprocess.TimeoutExpired:
            self.debug_print("SSH timeout during call execution", "ERROR")
            print(f"{Colors.RED}❌ SSH timeout during call execution{Colors.RESET}")
            return {
                'success': False,
                'error': "SSH timeout during call execution",
                'call_id': call_id
            }
        except Exception as e:
            self.debug_print(f"Exception during call execution: {str(e)}", "ERROR")
            print(f"{Colors.RED}❌ Exception: {str(e)}{Colors.RESET}")
            return {
                'success': False,
                'error': f"Exception during call execution: {str(e)}",
                'call_id': call_id
            }
    
    def _get_recent_call_logs(self, call_id, minutes=2):
        """
        Get recent Asterisk logs related to the call.
        Args:
            call_id (str): The call identifier.
            minutes (int): How far back to look in logs.
        Returns:
            list: Recent log lines.
        """
        try:
            # Get logs from the last few minutes
            log_cmd = f"tail -100 /var/log/asterisk/full | grep -E '(NOTICE|WARNING|ERROR)' | tail -20"
            result = self._run_command(log_cmd, timeout=15)
            
            if result.returncode == 0:
                return result.stdout.strip().split('\n')
            else:
                return ["No recent logs available"]
                
        except Exception as e:
            return [f"Error getting logs: {str(e)}"]
    
    def simulate_did_call(self, did, destination=None, caller_id=None, wait_time=10):
        """
        Simulate a call to a specific DID number.
        Args:
            did (str): The DID number being called (becomes callerID shown).
            destination (str): Where the call should ring (e.g., cell phone). If None, follows DID routing.
            caller_id (str): Override caller ID if needed (defaults to DID).
            wait_time (int): How long to wait before considering call failed.
        Returns:
            dict: Result of the call simulation.
        """
        # Create call file. The correct way to simulate "a real call arriving at
        # this DID" is to enter Asterisk's dialplan at the exact point a real
        # inbound PSTN call would land after trunk/DID matching: context
        # "from-did-direct" with the DID itself as the extension. FreePBX
        # resolves from there to whatever's actually configured (queue, IVR,
        # ring group, follow-me, etc.) — see freepbx_ops.py's decode(), which
        # already treats from-did-direct+extension this same way. This is what
        # makes the simulated call behave identically to a manually-dialed test
        # call (same routing, same log trail), which is the entire point of
        # this tool for troubleshooting.
        #
        # A previous version of this method built entirely different
        # "dest_app"/"dest_data" values for a from-pstn/Goto approach but never
        # actually passed them to create_call_file() — both branches silently
        # fell through to create_call_file()'s from-internal default instead,
        # so DID tests never exercised real DID routing at all.
        if destination:
            # Force the call through to a specific destination instead of the
            # DID's own configured routing. This still needs to go through
            # from-internal's outbound-route pattern matching to reach an
            # external number, which — like a real phone placing a call —
            # requires a caller ID FreePBX's outbound route permissions
            # actually recognize. Spoofing the DID itself as the caller ID
            # (the old default) silently fails that check with no error, which
            # is exactly what happened during testing: a manual call from a
            # real extension rang through fine, but this forced-destination
            # path never did. Default to a real, permitted extension's CID.
            if caller_id is None:
                caller_id = "8884400123"
            channel = f"Local/{destination}@from-internal"
            context = "from-internal"
            call_destination = destination
        else:
            if caller_id is None:
                caller_id = did
            channel = f"Local/{did}@from-did-direct"
            context = "from-did-direct"
            call_destination = did

        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 SIMULATING INCOMING CALL TO DID: {did:<31}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 68}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.WHITE}  Caller ID shown: {Colors.GREEN}{Colors.BOLD}{caller_id:<46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        if destination:
            print(f"{Colors.CYAN}║{Colors.WHITE}  Forcing ring to: {Colors.MAGENTA}{Colors.BOLD}{destination:<46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        else:
            print(f"{Colors.CYAN}║{Colors.WHITE}  Following configured DID routing (from-did-direct){' ' * 14}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")

        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=call_destination,
            context=context,
            wait_time=wait_time,
            max_retries=0
        )
        
        print(f"\n{Colors.BLUE}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.BLUE}║{Colors.WHITE}{Colors.BOLD} 📄 CALL FILE CONTENT{' ' * 45}{Colors.RESET}{Colors.BLUE} ║{Colors.RESET}")
        print(f"{Colors.BLUE}╠{'═' * 68}╣{Colors.RESET}")
        for line in call_content.strip().split('\n'):
            print(f"{Colors.BLUE}║{Colors.CYAN} {line:<66}{Colors.RESET}{Colors.BLUE} ║{Colors.RESET}")
        print(f"{Colors.BLUE}╚{'═' * 68}╝{Colors.RESET}")
        
        # Execute the call
        call_id = f"did_{did}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=wait_time + 8)
        
        # Analyze results
        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 CALL RESULTS{' ' * 51}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")
        
        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Call file executed successfully{' ' * 32}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            status_text = 'Yes' if result['processed'] else 'No'
            status_color = Colors.GREEN if result['processed'] else Colors.YELLOW
            print(f"{Colors.MAGENTA}║{Colors.WHITE}   📁 File processed: {status_color}{Colors.BOLD}{status_text:<45}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            
            if result['logs']:
                print(f"{Colors.MAGENTA}║{Colors.CYAN}   📝 Recent log entries:{' ' * 41}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
                for log in result['logs'][-5:]:  # Show last 5 entries
                    if log.strip():
                        log_display = log[:60] + "..." if len(log) > 60 else log
                        print(f"{Colors.MAGENTA}║{Colors.WHITE}      {log_display:<60}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:55] if len(result['error']) > 55 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Call execution failed: {error_msg:<35}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        
        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")
        
        # Store result for summary
        self.test_results.append({
            'did': did,
            'destination': destination,
            'caller_id': caller_id,
            'success': result['success'],
            'processed': result.get('processed', False),
            'timestamp': result.get('timestamp', ''),
            'error': result.get('error', '')
        })
        
        return result
    
    def test_extension_call(self, extension, caller_id="8884400123"):
        """
        Test calling a specific extension.
        Args:
            extension (str): Extension to call.
            caller_id (str): Caller ID to use.
        Returns:
            dict: Result of the extension call test.
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📱 TESTING EXTENSION CALL: {extension:<38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        # Origination target must be the extension under test, never caller_id —
        # caller_id can be an arbitrary 10-digit number, and from-internal will
        # route anything matching an outbound pattern as a REAL PSTN call.
        channel = f"Local/{extension}@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=extension,
            wait_time=15,
            max_retries=0
        )

        call_id = f"ext_{extension}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=23)
        
        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 EXTENSION TEST RESULTS{' ' * 39}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")
        
        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Extension call initiated{' ' * 37}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            print(f"{Colors.MAGENTA}║{Colors.CYAN}   📞 Target: Extension {extension:<43}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:40] if len(result['error']) > 40 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Extension call failed: {error_msg:<35}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        
        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")

        return result

    def test_ring_group_call(self, grpnum, caller_id="8884400123"):
        """
        Test calling a specific ring group. Ring groups are dialable via
        their own group number in from-internal, exactly like an extension,
        so this exercises the group's actual configured ring strategy
        (ringall/hunt/memoryhunt/etc.) and its members/failover.
        Args:
            grpnum (str): Ring group number to call.
            caller_id (str): Caller ID to use.
        Returns:
            dict: Result of the ring group call test.
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔔 TESTING RING GROUP CALL: {grpnum:<37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")

        channel = f"Local/{grpnum}@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=grpnum,
            wait_time=15,
            max_retries=0
        )

        call_id = f"rg_{grpnum}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=23)

        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 RING GROUP TEST RESULTS{' ' * 38}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")

        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Ring group call initiated{' ' * 36}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            print(f"{Colors.MAGENTA}║{Colors.CYAN}   🔔 Target: Ring Group {grpnum:<42}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:40] if len(result['error']) > 40 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Ring group call failed: {error_msg:<34}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")

        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")

        return result

    def test_queue_call(self, extension, caller_id="8884400123"):
        """
        Test calling a specific queue. Queues are dialable via their own
        extension number in from-internal, exactly like a regular extension,
        so this exercises the queue's actual configured strategy, members,
        and timeout/failover behavior.
        Args:
            extension (str): Queue extension number to call.
            caller_id (str): Caller ID to use.
        Returns:
            dict: Result of the queue call test.
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 TESTING QUEUE CALL: {extension:<42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")

        channel = f"Local/{extension}@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=extension,
            wait_time=15,
            max_retries=0
        )

        call_id = f"queue_{extension}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=23)

        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 QUEUE TEST RESULTS{' ' * 43}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")

        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Queue call initiated{' ' * 41}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            print(f"{Colors.MAGENTA}║{Colors.CYAN}   📞 Target: Queue {extension:<47}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:40] if len(result['error']) > 40 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Queue call failed: {error_msg:<39}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")

        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")

        return result

    def test_voicemail_call(self, mailbox, caller_id="8884400123"):
        """
        Test calling directly to voicemail.
        Args:
            mailbox (str): Mailbox to call.
            caller_id (str): Caller ID to use.
        Returns:
            dict: Result of the voicemail call test.
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📧 TESTING VOICEMAIL CALL: {mailbox:<38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        # Origination target must be the mailbox's own extension, never caller_id —
        # caller_id can be an arbitrary 10-digit number, and from-internal will
        # route anything matching an outbound pattern as a REAL PSTN call.
        channel = f"Local/{mailbox}@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination="",
            application="Voicemail",
            data=f"{mailbox}@default",
            wait_time=20,
            max_retries=0
        )
        
        call_id = f"vm_{mailbox}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=28)
        
        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 VOICEMAIL TEST RESULTS{' ' * 39}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")
        
        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Voicemail call initiated{' ' * 37}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            print(f"{Colors.MAGENTA}║{Colors.CYAN}   📧 Target: Mailbox {mailbox:<44}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:38] if len(result['error']) > 38 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Voicemail call failed: {error_msg:<36}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        
        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")
        
        return result
    
    def test_playback_application(self, sound_file="demo-congrats", caller_id="8884400123"):
        """
        Test playback application (e.g., play a sound file).
        Args:
            sound_file (str): Name of the sound file to play.
            caller_id (str): Caller ID to use.
        Returns:
            dict: Result of the playback test.
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🎵 TESTING PLAYBACK APPLICATION: {sound_file:<32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        # Origination target must never be caller_id — caller_id can be an
        # arbitrary 10-digit number, and from-internal will route anything
        # matching an outbound pattern as a REAL PSTN call. This method takes
        # no extension of its own, so loop back through the lab's designated
        # test extension (963) rather than dialing anything external.
        channel = "Local/963@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination="",
            application="Playback",
            data=sound_file,
            wait_time=10,
            max_retries=0
        )
        
        call_id = f"play_{sound_file}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id, channel=channel, cdr_wait=18)
        
        print(f"\n{Colors.MAGENTA}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.MAGENTA}║{Colors.YELLOW}{Colors.BOLD} 📊 PLAYBACK TEST RESULTS{' ' * 40}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        print(f"{Colors.MAGENTA}╠{'═' * 68}╣{Colors.RESET}")
        
        if result['success']:
            print(f"{Colors.MAGENTA}║{Colors.GREEN}   ✅ Playback call initiated{' ' * 38}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
            print(f"{Colors.MAGENTA}║{Colors.CYAN}   🎵 Sound: {sound_file:<52}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        else:
            error_msg = result['error'][:40] if len(result['error']) > 40 else result['error']
            print(f"{Colors.MAGENTA}║{Colors.RED}   ❌ Playback call failed: {error_msg:<37}{Colors.RESET}{Colors.MAGENTA} ║{Colors.RESET}")
        
        print(f"{Colors.MAGENTA}╚{'═' * 68}╝{Colors.RESET}")
        
        return result
    
    def run_comprehensive_test_suite(self, test_dids=None):
        """
        Run a comprehensive suite of call simulation tests.
        Runs DID, extension, voicemail, application, ring group, and queue
        tests, then prints a summary. Ring groups and queues are discovered
        from the target PBX's own database rather than hardcoded, so this
        exercises whatever's actually configured there.
        Args:
            test_dids (list): List of DIDs to test. Uses defaults if None.
        """
        print(f"\n{Colors.YELLOW}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.BOLD}{Colors.WHITE} 🚀 COMPREHENSIVE CALL SIMULATION TEST SUITE{' ' * 34}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╚{'═' * 78}╝{Colors.RESET}")
        
        if not test_dids:
            test_dids = [
                "2485815200",  # Complex time condition + IVR
                "3134489750",  # Voicemail box
                "9062320010",  # Direct extension
                "7343843005",  # Time condition
                "3134489706"   # Extension with name
            ]
        
        # Test 1: DID routing tests
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 📞 TEST 1: DID ROUTING SIMULATION{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        
        for did in test_dids:
            self.simulate_did_call(did)
            time.sleep(3)  # Wait between tests
        
        # Test 2: Extension tests
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 📱 TEST 2: EXTENSION SIMULATION{' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        
        test_extensions = ["4220", "4221", "4222"]
        for ext in test_extensions:
            self.test_extension_call(ext)
            time.sleep(3)
        
        # Test 3: Voicemail tests
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 📧 TEST 3: VOICEMAIL SIMULATION{' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        
        test_mailboxes = ["4220", "4221"]
        for mailbox in test_mailboxes:
            self.test_voicemail_call(mailbox)
            time.sleep(3)
        
        # Test 4: Application tests
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 🎵 TEST 4: APPLICATION SIMULATION{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
        
        test_sounds = ["demo-congrats", "demo-thanks", "zombies"]
        for sound in test_sounds:
            self.test_playback_application(sound)
            time.sleep(3)

        # Test 5: Ring group tests — whatever's actually configured on this PBX
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 🔔 TEST 5: RING GROUP SIMULATION{' ' * 45}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")

        ring_groups = self._query_ring_group_numbers()
        if ring_groups:
            for grpnum in ring_groups:
                self.test_ring_group_call(grpnum, caller_id="test")
                time.sleep(3)
        else:
            print(f"{Colors.YELLOW}   No ring groups found on this system — skipping.{Colors.RESET}")

        # Test 6: Queue tests — whatever's actually configured on this PBX
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BOLD}{Colors.YELLOW} 📞 TEST 6: QUEUE SIMULATION{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")

        queue_extensions = self._query_queue_extensions()
        if queue_extensions:
            for ext in queue_extensions:
                self.test_queue_call(ext, caller_id="test")
                time.sleep(3)
        else:
            print(f"{Colors.YELLOW}   No queues found on this system — skipping.{Colors.RESET}")

        # Generate summary report
        self.generate_test_summary()
    
    def generate_test_summary(self):
        """
        Generate a summary report of all test results.
        Prints statistics and saves results to a JSON file.
        """
        print(f"\n{Colors.GREEN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.BOLD}{Colors.WHITE} 📊 CALL SIMULATION TEST SUMMARY{' ' * 45}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}╠{'═' * 78}╣{Colors.RESET}")
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result['success'])
        processed_tests = sum(1 for result in self.test_results if result.get('processed', False))
        
        success_rate = (successful_tests/total_tests*100) if total_tests > 0 else 0
        processing_rate = (processed_tests/total_tests*100) if total_tests > 0 else 0
        
        print(f"{Colors.GREEN}║{Colors.CYAN} 📈 Test Statistics:{' ' * 56}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}    Total Tests: {Colors.BOLD}{Colors.YELLOW}{total_tests:<57}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}    Successful: {Colors.BOLD}{Colors.GREEN}{successful_tests:<58}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}    Processed: {Colors.BOLD}{Colors.CYAN}{processed_tests:<59}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}    Success Rate: {Colors.BOLD}{Colors.GREEN}{success_rate:.1f}%{' ' * 53}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        print(f"{Colors.GREEN}║{Colors.WHITE}    Processing Rate: {Colors.BOLD}{Colors.CYAN}{processing_rate:.1f}%{' ' * 50}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        
        # Show failed tests
        failed_tests = [result for result in self.test_results if not result['success']]
        if failed_tests:
            print(f"{Colors.GREEN}╠{'═' * 78}╣{Colors.RESET}")
            print(f"{Colors.GREEN}║{Colors.RED} ❌ Failed Tests:{' ' * 60}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
            for test in failed_tests:
                error_short = test['error'][:50] if len(test['error']) > 50 else test['error']
                print(f"{Colors.GREEN}║{Colors.YELLOW}    {test['did']} {Colors.WHITE}- {Colors.RED}{error_short:<50}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        
        # Show successful tests
        successful_tests_list = [result for result in self.test_results if result['success']]
        if successful_tests_list:
            print(f"{Colors.GREEN}╠{'═' * 78}╣{Colors.RESET}")
            print(f"{Colors.GREEN}║{Colors.GREEN} ✅ Successful Tests:{' ' * 56}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
            for test in successful_tests_list:
                status = "Processed" if test.get('processed', False) else "Queued"
                status_color = Colors.GREEN if test.get('processed', False) else Colors.YELLOW
                print(f"{Colors.GREEN}║{Colors.CYAN}    {test['did']} {Colors.WHITE}- {status_color}{status:<55}{Colors.RESET}{Colors.GREEN} ║{Colors.RESET}")
        
        print(f"{Colors.GREEN}╚{'═' * 78}╝{Colors.RESET}")
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"call_simulation_results_{timestamp}.json"
        
        try:
            with open(results_file, 'w') as f:
                json.dump({
                    'summary': {
                        'total_tests': total_tests,
                        'successful_tests': successful_tests,
                        'processed_tests': processed_tests,
                        'success_rate': success_rate,
                        'processing_rate': processing_rate
                    },
                    'test_results': self.test_results,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            
            print(f"\n{Colors.BLUE}💾 Results saved to: {Colors.BOLD}{results_file}{Colors.RESET}")
        except Exception as e:
            print(f"\n{Colors.YELLOW}⚠️  Could not save results: {str(e)}{Colors.RESET}")


def _exit_status(result):
    """Process exit code for a single live-call test: 0 only if the call
    file mechanics succeeded AND (when a CDR check was attempted) the call
    was actually confirmed in CDR. cdr_confirmed is None when no channel
    was passed for polling — treated as pass-through rather than a hard
    requirement, so callers that don't opt into CDR checking aren't
    affected. This is what makes option 16's self-test (which just checks
    this process's exit code) an actual verification instead of only
    proving the .call file was accepted."""
    if not result or not result.get('success'):
        return 1
    if result.get('cdr_confirmed') is False:
        return 1
    return 0


def main():
    """
    Main entry point for the FreePBX Call Simulator CLI.
    Parses command-line arguments and dispatches to the appropriate test method.
    """
    parser = argparse.ArgumentParser(description="FreePBX Call Simulator")
    parser.add_argument("--server", default=None, help="FreePBX server IP (default: this box's own IP)")
    parser.add_argument("--user", default="123net", help="SSH username")
    parser.add_argument("--did", help="Test specific DID (incoming call)")
    parser.add_argument("--destination", help="Destination number to ring (e.g., cell phone)")
    parser.add_argument("--extension", help="Test specific extension")
    parser.add_argument("--ring-group", help="Test specific ring group (by group number)")
    parser.add_argument("--queue", help="Test specific queue (by extension number)")
    parser.add_argument("--voicemail", help="Test specific voicemail box")
    parser.add_argument("--playback", help="Test playback application with sound file")
    parser.add_argument("--caller-id", help="Override caller ID (defaults to DID for DID tests)")
    parser.add_argument("--comprehensive", action="store_true", help="Run comprehensive test suite")
    parser.add_argument("--debug", action="store_true", help="Enable detailed debug output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (same as --debug)")
    args = parser.parse_args()
    # Enable debug mode if requested
    debug_mode = args.debug or args.verbose
    # Initialize simulator
    simulator = FreePBXCallSimulator(args.server, args.user)
    simulator.debug = debug_mode  # Set debug flag on simulator instance
    print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 FREEPBX CALL SIMULATOR{' ' * 51}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} Server: {Colors.GREEN}{Colors.BOLD}{simulator.server_ip:<67}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} User: {Colors.CYAN}{Colors.BOLD}{args.user:<69}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    if args.caller_id:
        print(f"{Colors.CYAN}║{Colors.WHITE} Caller ID: {Colors.MAGENTA}{Colors.BOLD}{args.caller_id:<64}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    # Execute based on arguments
    if args.comprehensive:
        simulator.run_comprehensive_test_suite()
    elif args.did:
        result = simulator.simulate_did_call(args.did, destination=args.destination, caller_id=args.caller_id)
        sys.exit(_exit_status(result))
    elif args.extension:
        caller = args.caller_id or "8884400123"
        result = simulator.test_extension_call(args.extension, caller)
        sys.exit(_exit_status(result))
    elif args.ring_group:
        caller = args.caller_id or "8884400123"
        result = simulator.test_ring_group_call(args.ring_group, caller)
        sys.exit(_exit_status(result))
    elif args.queue:
        caller = args.caller_id or "8884400123"
        result = simulator.test_queue_call(args.queue, caller)
        sys.exit(_exit_status(result))
    elif args.voicemail:
        caller = args.caller_id or "8884400123"
        result = simulator.test_voicemail_call(args.voicemail, caller)
        sys.exit(_exit_status(result))
    elif args.playback:
        caller = args.caller_id or "8884400123"
        result = simulator.test_playback_application(args.playback, caller)
        sys.exit(_exit_status(result))
    else:
        # Print usage examples if no valid arguments provided
        print(f"\n{Colors.YELLOW}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.BOLD}{Colors.WHITE} 🎯 USAGE EXAMPLES{' ' * 59}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Test DID with routing to cell phone:{' ' * 38}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 call_simulator.py --did 2482283480 --destination 7346427842{' ' * 6}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Test DID following its configured routing:{' ' * 33}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 call_simulator.py --did 2482283480{' ' * 33}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Test extension:{' ' * 61}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 call_simulator.py --extension 4220{' ' * 32}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Test voicemail:{' ' * 60}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 call_simulator.py --voicemail 4220{' ' * 32}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Run comprehensive suite:{' ' * 52}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 call_simulator.py --comprehensive{' ' * 33}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╚{'═' * 78}╝{Colors.RESET}")

# Standard Python entry point
if __name__ == "__main__":
    main()