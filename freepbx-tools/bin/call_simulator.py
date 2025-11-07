#!/usr/bin/env python3
"""
freePBX Call Simulator
Generate and execute Asterisk call files to test call flow routing
Monitors call outcomes and validates against expected behavior
"""

import os
import sys
import time
import subprocess
import tempfile
import argparse
from datetime import datetime, timedelta
import json
import socket
import re

class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

class FreePBXCallSimulator:
    def __init__(self, server_ip=None, ssh_user="123net"):
        self.server_ip = server_ip or "69.39.69.102"
        self.ssh_user = ssh_user
        self.spool_dir = "/var/spool/asterisk/outgoing"
        self.tmp_dir = "/tmp"
        self.asterisk_user = "asterisk"
        self.test_results = []
        self.debug = False  # Enable debug output when True
        self.is_local_execution = self._is_local_execution()
        
    def debug_print(self, message, level="INFO"):
        """Print debug messages with colorized level indicators"""
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
        """Check if we're running on the same server as the target"""
        try:
            # Get local IP addresses
            hostname = socket.gethostname()
            local_ips = set()
            local_ips.add(socket.gethostbyname(hostname))
            local_ips.add("127.0.0.1")
            local_ips.add("localhost")
            
            # Add all local interface IPs
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ips.add(s.getsockname()[0])
                s.close()
            except:
                pass
                
            return self.server_ip in local_ips
        except:
            return False
    
    def _run_command(self, command, timeout=10):
        """Run command locally or via SSH based on execution context"""
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
        
    def create_call_file(self, channel, caller_id, destination, context="from-internal", 
                        priority=1, wait_time=30, max_retries=2, application=None, 
                        data=None, archive=False):
        """
        Create an Asterisk call file with specified parameters
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
    
    def execute_call_file(self, call_content, call_id=None):
        """
        Execute a call file on the remote freePBX server
        Returns call execution results
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
                self.debug_print("File not found in spool after move", "ERROR")
                return {
                    'success': False,
                    'error': f"File not found in spool directory after move",
                    'call_id': call_id
                }
            
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
            
            print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}\n")
            
            return {
                'success': True,
                'processed': processed,
                'call_id': call_id,
                'logs': call_logs,
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
        Get recent Asterisk logs related to the call
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
        Simulate a call to a specific DID number
        Args:
            did: The DID number being called (this becomes the callerID shown)
            destination: Where the call should ring (e.g., cell phone) - if None, follows DID routing
            caller_id: Override caller ID if needed (defaults to DID)
            wait_time: How long to wait before considering call failed
        """
        if caller_id is None:
            caller_id = did
            
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 SIMULATING INCOMING CALL TO DID: {did:<31}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 68}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.WHITE}  Caller ID shown: {Colors.GREEN}{Colors.BOLD}{caller_id:<46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        if destination:
            print(f"{Colors.CYAN}║{Colors.WHITE}  Forcing ring to: {Colors.MAGENTA}{Colors.BOLD}{destination:<46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        else:
            print(f"{Colors.CYAN}║{Colors.WHITE}  Following configured DID routing{' ' * 32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        # Create call file
        # For DID simulation: use Local channel that enters through from-trunk context
        # This mimics an incoming call from the PSTN
        if destination:
            # Direct call to destination, bypassing DID routing
            channel = f"Local/{destination}@from-internal"
            dest_app = "Answer"
            dest_data = ""
        else:
            # Route through DID configuration
            channel = f"Local/{did}@from-pstn"
            dest_app = "Goto"
            dest_data = f"from-did-direct,{did},1"
            
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=did if not destination else destination,
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
        result = self.execute_call_file(call_content, call_id)
        
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
    
    def test_extension_call(self, extension, caller_id="7140"):
        """
        Test calling a specific extension
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📱 TESTING EXTENSION CALL: {extension:<38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        channel = f"local/{caller_id}@from-internal"
        call_content = self.create_call_file(
            channel=channel,
            caller_id=caller_id,
            destination=extension,
            wait_time=15,
            max_retries=1
        )
        
        call_id = f"ext_{extension}_{int(time.time())}"
        result = self.execute_call_file(call_content, call_id)
        
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
    
    def test_voicemail_call(self, mailbox, caller_id="7140"):
        """
        Test calling directly to voicemail
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📧 TESTING VOICEMAIL CALL: {mailbox:<38}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        channel = f"local/{caller_id}@from-internal"
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
        result = self.execute_call_file(call_content, call_id)
        
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
    
    def test_playback_application(self, sound_file="demo-congrats", caller_id="7140"):
        """
        Test playback application (like the zombies example)
        """
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🎵 TESTING PLAYBACK APPLICATION: {sound_file:<32}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        channel = f"local/{caller_id}@from-internal"
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
        result = self.execute_call_file(call_content, call_id)
        
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
        Run a comprehensive suite of call simulation tests
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
        
        # Generate summary report
        self.generate_test_summary()
    
    def generate_test_summary(self):
        """
        Generate a summary report of all test results
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

def main():
    parser = argparse.ArgumentParser(description="FreePBX Call Simulator")
    parser.add_argument("--server", default="69.39.69.102", help="FreePBX server IP")
    parser.add_argument("--user", default="123net", help="SSH username")
    parser.add_argument("--did", help="Test specific DID (incoming call)")
    parser.add_argument("--destination", help="Destination number to ring (e.g., cell phone)")
    parser.add_argument("--extension", help="Test specific extension")
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
    print(f"{Colors.CYAN}║{Colors.WHITE} Server: {Colors.GREEN}{Colors.BOLD}{args.server:<67}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} User: {Colors.CYAN}{Colors.BOLD}{args.user:<69}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    if args.caller_id:
        print(f"{Colors.CYAN}║{Colors.WHITE} Caller ID: {Colors.MAGENTA}{Colors.BOLD}{args.caller_id:<64}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    
    # Execute based on arguments
    if args.comprehensive:
        simulator.run_comprehensive_test_suite()
    elif args.did:
        simulator.simulate_did_call(args.did, destination=args.destination, caller_id=args.caller_id)
    elif args.extension:
        caller = args.caller_id or "7140"
        simulator.test_extension_call(args.extension, caller)
    elif args.voicemail:
        caller = args.caller_id or "7140"
        simulator.test_voicemail_call(args.voicemail, caller)
    elif args.playback:
        caller = args.caller_id or "7140"
        simulator.test_playback_application(args.playback, caller)
    else:
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

if __name__ == "__main__":
    main()