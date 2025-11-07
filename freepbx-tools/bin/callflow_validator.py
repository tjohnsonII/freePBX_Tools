#!/usr/bin/env python3
"""
freePBX Call Flow Validation through Live Simulation
Compare predicted call flows with actual Asterisk behavior
"""

import sys
import subprocess
import time
import json
import re
import socket
import argparse
import logging
from datetime import datetime

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

# Configure logging
def setup_logging(debug=False):
    """Setup logging configuration"""
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Create logger
    logger = logging.getLogger('callflow_validator')
    logger.setLevel(log_level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler for debugging
    try:
        file_handler = logging.FileHandler('/tmp/callflow_validator.log')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass  # File logging is optional
    
    return logger

# Global logger (will be initialized in main)
logger = None

class CallFlowValidator:
    def __init__(self, server_ip="69.39.69.102", ssh_user="123net", debug=False):
        self.server_ip = server_ip
        self.ssh_user = ssh_user
        self.debug = debug
        self.callflow_tool = "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py"
        
        # Get logger
        global logger
        self.logger = logger or logging.getLogger('callflow_validator')
        
        self.logger.info(f"Initializing CallFlowValidator")
        self.logger.info(f"  Server IP: {self.server_ip}")
        self.logger.info(f"  SSH User: {self.ssh_user}")
        self.logger.info(f"  Debug Mode: {self.debug}")
        
    def get_predicted_flow(self, did):
        """Get predicted call flow from our ASCII tool"""
        self.logger.info(f"Getting predicted call flow for DID: {did}")
        
        try:
            # Check if we're running on the same server - if so, run locally
            local_hostname = socket.gethostname()
            local_ip = socket.gethostbyname(local_hostname)
            
            self.logger.debug(f"Localhost detection:")
            self.logger.debug(f"  Local hostname: {local_hostname}")
            self.logger.debug(f"  Local IP: {local_ip}")
            self.logger.debug(f"  Target server IP: {self.server_ip}")
            
            # Check if we should run locally
            is_local = (
                self.server_ip in ['localhost', '127.0.0.1', local_ip] or 
                local_hostname.startswith('pbx') or
                self.server_ip in local_ip  # Additional check
            )
            
            self.logger.info(f"Running locally: {is_local}")
            
            if is_local:
                # Run locally instead of SSH
                cmd = ["python3", self.callflow_tool, "--did", did]
                self.logger.debug(f"Local command: {' '.join(cmd)}")
            else:
                # Run via SSH for remote servers
                cmd = ["ssh", f"{self.ssh_user}@{self.server_ip}", 
                       f"python3 {self.callflow_tool} --did {did}"]
                self.logger.debug(f"SSH command: {' '.join(cmd)}")
            
            self.logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=30)
            
            self.logger.debug(f"Command return code: {result.returncode}")
            if result.stdout:
                self.logger.debug(f"Command stdout: {result.stdout[:200]}...")
            if result.stderr:
                self.logger.debug(f"Command stderr: {result.stderr}")
            
            if result.returncode == 0:
                parsed_result = self._parse_callflow_output(result.stdout)
                self.logger.info(f"Successfully parsed call flow data")
                return parsed_result
            else:
                error_msg = f"Tool failed: {result.stderr}"
                self.logger.error(error_msg)
                return {'error': error_msg}
                
        except Exception as e:
            error_msg = f"Exception in get_predicted_flow: {str(e)}"
            self.logger.error(error_msg)
            return {'error': error_msg}
    
    def _parse_callflow_output(self, output):
        """Parse call flow tool output into structured data"""
        flow_data = {
            'components': [],
            'destinations': [],
            'has_ivr': False,
            'has_time_condition': False,
            'has_ring_group': False,
            'has_voicemail': False,
            'extensions': []
        }
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            
            # Detect components
            if '🎵' in line or 'IVR' in line:
                flow_data['has_ivr'] = True
                flow_data['components'].append('IVR')
                
            if '⏰' in line or 'Time Condition' in line:
                flow_data['has_time_condition'] = True
                flow_data['components'].append('TimeCondition')
                
            if '🔔' in line or 'Ring Group' in line:
                flow_data['has_ring_group'] = True
                flow_data['components'].append('RingGroup')
                
            if '📧' in line or 'Voicemail' in line:
                flow_data['has_voicemail'] = True
                flow_data['components'].append('Voicemail')
                
            if '📞' in line or 'Extension' in line:
                # Extract extension number
                ext_match = re.search(r'Extension (\d+)', line)
                if ext_match:
                    flow_data['extensions'].append(ext_match.group(1))
        
        return flow_data
    
    def simulate_call_and_monitor(self, did, caller_id="7140"):
        """Simulate call and monitor actual Asterisk behavior"""
        self.logger.info(f"Starting call simulation for DID {did} with caller ID {caller_id}")
        print(f"🚀 Simulating call to {did} and monitoring behavior...")
        
        # Clear Asterisk logs before test
        self.logger.debug("Clearing Asterisk logs")
        self._clear_asterisk_logs()
        
        # Create and execute call file
        self.logger.debug("Executing test call")
        call_result = self._execute_test_call(did, caller_id)
        
        if not call_result['success']:
            error_msg = f"Call simulation failed: {call_result['error']}"
            self.logger.error(error_msg)
            return {'error': error_msg}
        
        self.logger.info(f"Call file created successfully: {call_result.get('call_id')}")
        
        # Wait for call processing
        self.logger.debug("Waiting 5 seconds for call processing")
        time.sleep(5)
        
        # Analyze Asterisk logs
        self.logger.debug("Analyzing Asterisk logs")
        log_analysis = self._analyze_asterisk_logs(call_result['call_id'])
        
        result = {
            'call_successful': call_result['success'],
            'call_processed': call_result.get('processed', False),
            'log_analysis': log_analysis,
            'call_id': call_result['call_id'],
            'timestamp': datetime.now().isoformat()
        }
        
        self.logger.info(f"Call simulation completed: {result['call_successful']}")
        return result
    
    def _clear_asterisk_logs(self):
        """Clear or mark current position in Asterisk logs"""
        try:
            # Get current log size for baseline
            cmd = ["ssh", f"{self.ssh_user}@{self.server_ip}", 
                   "wc -l /var/log/asterisk/full 2>/dev/null || echo '0'"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            
            if result.returncode == 0:
                self.log_baseline = int(result.stdout.strip().split()[0])
            else:
                self.log_baseline = 0
                
        except Exception:
            self.log_baseline = 0
    
    def _execute_test_call(self, did, caller_id):
        """Execute a test call using call file"""
        call_id = f"validation_{did}_{int(time.time())}"
        temp_file = f"/tmp/call_{call_id}"
        spool_file = f"/var/spool/asterisk/outgoing/call_{call_id}.call"
        
        self.logger.info(f"Executing test call for DID {did}")
        self.logger.debug(f"Call ID: {call_id}")
        self.logger.debug(f"Temp file: {temp_file}")
        self.logger.debug(f"Spool file: {spool_file}")
        
        # Create call file content (using FIXED channel syntax)
        call_content = f"""Channel: local/{caller_id}@from-internal
CallerID: {caller_id}
Context: from-internal
Extension: {did}
Priority: 1
WaitTime: 15
MaxRetries: 1
Archive: no
# Validation test for DID {did}
"""
        
        self.logger.debug(f"Call file content:\n{call_content}")
        
        try:
            # Check if we should run locally
            local_hostname = socket.gethostname()
            local_ip = socket.gethostbyname(local_hostname)
            
            is_local = (
                self.server_ip in ['localhost', '127.0.0.1', local_ip] or 
                local_hostname.startswith('pbx') or
                self.server_ip == local_ip
            )
            
            self.logger.info(f"Call file execution - running locally: {is_local}")
            
            if is_local:
                # Run locally
                self.logger.debug("Creating call file locally")
                
                # Write call file locally
                with open(temp_file, 'w') as f:
                    f.write(call_content)
                
                # Set ownership
                subprocess.run(['chown', 'asterisk:asterisk', temp_file], 
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                
                # Move to spool directory
                move_result = subprocess.run(['mv', temp_file, spool_file], 
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                
                if move_result.returncode != 0:
                    error_msg = f"Failed to spool call: {move_result.stderr.decode()}"
                    self.logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                
            else:
                # Use SSH for remote execution
                self.logger.debug("Creating call file via SSH")
                
                # Create call file on server
                cmd = f'cat > {temp_file} << "EOF"\n{call_content}EOF'
                self.logger.debug(f"SSH command: ssh {self.ssh_user}@{self.server_ip} {cmd}")
                
                result = subprocess.run([
                    "ssh", f"{self.ssh_user}@{self.server_ip}", cmd
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
                
                self.logger.debug(f"SSH create result: {result.returncode}")
                if result.stderr:
                    self.logger.debug(f"SSH create stderr: {result.stderr}")
                
                if result.returncode != 0:
                    error_msg = f"Failed to create call file: {result.stderr}"
                    self.logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                
                # Set ownership
                self.logger.debug("Setting file ownership via SSH")
                subprocess.run([
                    "ssh", f"{self.ssh_user}@{self.server_ip}", 
                    f"chown asterisk:asterisk {temp_file}"
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
                
                # Move to spool directory
                self.logger.debug("Moving to spool directory via SSH")
                move_result = subprocess.run([
                    "ssh", f"{self.ssh_user}@{self.server_ip}", 
                    f"mv {temp_file} {spool_file}"
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
                
                if move_result.returncode != 0:
                    error_msg = f"Failed to spool call: {move_result.stderr}"
                    self.logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
            
            self.logger.info("Call file created and spooled successfully")
            
            # Check if processed
            self.logger.debug("Waiting 2 seconds then checking if call was processed")
            time.sleep(2)
            
            if is_local:
                # Check locally
                import os
                processed = not os.path.exists(spool_file)
            else:
                # Check via SSH
                check_result = subprocess.run([
                    "ssh", f"{self.ssh_user}@{self.server_ip}", 
                    f"test -f {spool_file} && echo 'EXISTS' || echo 'PROCESSED'"
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
                
                processed = "PROCESSED" in check_result.stdout
            
            self.logger.info(f"Call processed: {processed}")
            
            return {
                'success': True,
                'call_id': call_id,
                'processed': processed
            }
            
        except Exception as e:
            error_msg = f"Exception in _execute_test_call: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _analyze_asterisk_logs(self, call_id):
        """Analyze Asterisk logs for call behavior"""
        try:
            # Get logs since baseline
            cmd = ["ssh", f"{self.ssh_user}@{self.server_ip}", 
                   f"tail -n +{self.log_baseline + 1} /var/log/asterisk/full | grep -E '(NOTICE|WARNING|ERROR|VERBOSE)' | tail -50"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
            
            if result.returncode != 0:
                return {'error': 'Could not retrieve logs'}
            
            log_lines = result.stdout.strip().split('\n')
            
            analysis = {
                'components_hit': [],
                'destinations_reached': [],
                'errors': [],
                'routing_path': []
            }
            
            for line in log_lines:
                if not line.strip():
                    continue
                    
                # Detect IVR interaction
                if re.search(r'(ivr|IVR)', line, re.IGNORECASE):
                    analysis['components_hit'].append('IVR')
                    analysis['routing_path'].append(f"IVR: {line.split()[-1] if line.split() else 'unknown'}")
                
                # Detect time condition evaluation
                if re.search(r'(timecondition|time.*condition)', line, re.IGNORECASE):
                    analysis['components_hit'].append('TimeCondition')
                    analysis['routing_path'].append(f"TimeCondition: {line.split()[-1] if line.split() else 'unknown'}")
                
                # Detect ring group
                if re.search(r'(ringgroup|ring.*group)', line, re.IGNORECASE):
                    analysis['components_hit'].append('RingGroup')
                    analysis['routing_path'].append(f"RingGroup: {line.split()[-1] if line.split() else 'unknown'}")
                
                # Detect voicemail
                if re.search(r'(voicemail|vm)', line, re.IGNORECASE):
                    analysis['components_hit'].append('Voicemail')
                    analysis['routing_path'].append(f"Voicemail: {line.split()[-1] if line.split() else 'unknown'}")
                
                # Detect extension calls
                ext_match = re.search(r'(\d{4,5})', line)
                if ext_match and 'DIAL' in line.upper():
                    analysis['destinations_reached'].append(f"Extension: {ext_match.group(1)}")
                    analysis['routing_path'].append(f"Extension: {ext_match.group(1)}")
                
                # Detect errors
                if re.search(r'(ERROR|FAILED|BUSY|CONGESTION)', line, re.IGNORECASE):
                    analysis['errors'].append(line.strip())
            
            # Remove duplicates with explicit string conversion
            analysis['components_hit'] = list(set(str(item) for item in analysis['components_hit']))
            analysis['destinations_reached'] = list(set(str(item) for item in analysis['destinations_reached']))
            
            return analysis
            
        except Exception as e:
            return {'error': f"Log analysis failed: {str(e)}"}
    
    def validate_call_flow(self, did):
        """Complete validation of call flow prediction vs reality"""
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔍 VALIDATING CALL FLOW FOR DID: {did} {Colors.RESET}{Colors.CYAN}                      ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        
        # Step 1: Get predicted flow
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.BLUE}{Colors.BOLD} 📊 Step 1: Getting predicted call flow {Colors.RESET}{Colors.CYAN}                    ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        predicted = self.get_predicted_flow(did)
        
        if 'error' in predicted:
            print(f"   {Colors.RED}❌ Failed to get prediction: {predicted['error']}{Colors.RESET}")
            return {'success': False, 'error': predicted['error']}
        
        print(f"   {Colors.GREEN}✅ Predicted components: {Colors.CYAN}{', '.join(str(c) for c in predicted.get('components', []))}{Colors.RESET}")
        print(f"   {Colors.GREEN}📞 Predicted extensions: {Colors.CYAN}{', '.join(str(e) for e in predicted.get('extensions', []))}{Colors.RESET}")
        
        # Step 2: Simulate actual call
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🚀 Step 2: Simulating actual call {Colors.RESET}{Colors.CYAN}                           ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        actual = self.simulate_call_and_monitor(did)
        
        if 'error' in actual:
            print(f"   {Colors.RED}❌ Simulation failed: {actual['error']}{Colors.RESET}")
            return {'success': False, 'error': actual['error']}
        
        print(f"   {Colors.GREEN}✅ Call processed: {Colors.BOLD}{actual['call_processed']}{Colors.RESET}")
        
        # Safely access log analysis data
        log_analysis = actual.get('log_analysis', {})
        if not isinstance(log_analysis, dict) or 'error' in log_analysis:
            error_msg = log_analysis.get('error', str(log_analysis)) if isinstance(log_analysis, dict) else str(log_analysis)
            print(f"   {Colors.YELLOW}⚠️  Log analysis error: {error_msg}{Colors.RESET}")
        else:
            components = log_analysis.get('components_hit', [])
            destinations = log_analysis.get('destinations_reached', [])
            
            # Ensure components and destinations are lists of strings
            components = [str(c) for c in components] if components else []
            destinations = [str(d) for d in destinations] if destinations else []
            
            print(f"   {Colors.BLUE}🔍 Components hit: {Colors.CYAN}{', '.join(components) if components else 'None'}{Colors.RESET}")
            print(f"   {Colors.MAGENTA}📍 Destinations reached: {Colors.CYAN}{', '.join(destinations) if destinations else 'None'}{Colors.RESET}")
        
        # Step 3: Compare and validate
        print(f"\n{Colors.CYAN}╔{'═' * 68}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.MAGENTA}{Colors.BOLD} ⚖️  Step 3: Comparing prediction vs reality {Colors.RESET}{Colors.CYAN}               ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 68}╝{Colors.RESET}")
        validation_result = self._compare_flows(predicted, actual)
        
        score = validation_result['score']
        score_color = Colors.GREEN if score >= 80 else (Colors.YELLOW if score >= 60 else Colors.RED)
        
        print(f"   {Colors.BLUE}📊 Validation Score: {score_color}{Colors.BOLD}{score:.1f}%{Colors.RESET}")
        print(f"   {Colors.GREEN}✅ Matches: {Colors.BOLD}{len(validation_result['matches'])}{Colors.RESET}")
        print(f"   {Colors.RED}❌ Mismatches: {Colors.BOLD}{len(validation_result['mismatches'])}{Colors.RESET}")
        
        if validation_result['matches']:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ MATCHES:{Colors.RESET}")
            for match in validation_result['matches']:
                print(f"   {Colors.GREEN}  ✓{Colors.RESET} {Colors.WHITE}{match}{Colors.RESET}")
        
        if validation_result['mismatches']:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ MISMATCHES:{Colors.RESET}")
            for mismatch in validation_result['mismatches']:
                print(f"   {Colors.RED}  ✗{Colors.RESET} {Colors.WHITE}{mismatch}{Colors.RESET}")
        
        # Safely check for errors in log analysis
        log_analysis = actual.get('log_analysis', {})
        if isinstance(log_analysis, dict) and 'error' not in log_analysis and log_analysis.get('errors'):
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  ERRORS DETECTED:{Colors.RESET}")
            errors = log_analysis.get('errors', [])
            for error in errors[:3]:  # Show first 3
                print(f"      {error}")
        
        return {
            'success': True,
            'did': did,
            'predicted': predicted,
            'actual': actual,
            'validation': validation_result,
            'timestamp': datetime.now().isoformat()
        }
    
    def _compare_flows(self, predicted, actual):
        """Compare predicted vs actual call flows"""
        matches = []
        mismatches = []
        
        # Safely get log analysis data
        log_analysis = actual.get('log_analysis', {})
        if 'error' in log_analysis or not isinstance(log_analysis, dict):
            # If log analysis failed, we can't compare
            return {
                'score': 0.0,
                'matches': [],
                'mismatches': ['Log analysis failed - cannot validate'],
                'predicted_components': [str(item) for item in predicted.get('components', [])],
                'actual_components': [],
                'predicted_extensions': [str(item) for item in predicted.get('extensions', [])],
                'actual_extensions': []
            }
        
        # Compare components
        predicted_components = set(predicted.get('components', []))
        actual_components = set(log_analysis.get('components_hit', []))
        
        common_components = predicted_components & actual_components
        for component in common_components:
            matches.append(f"Component: {component}")
        
        missing_actual = predicted_components - actual_components
        for component in missing_actual:
            mismatches.append(f"Predicted {component} but not found in logs")
        
        unexpected_actual = actual_components - predicted_components
        for component in unexpected_actual:
            mismatches.append(f"Found {component} in logs but not predicted")
        
        # Compare extensions
        predicted_extensions = set(predicted.get('extensions', []))
        actual_destinations = log_analysis.get('destinations_reached', [])
        
        actual_extensions = set()
        for dest in actual_destinations:
            if dest.startswith('Extension:'):
                actual_extensions.add(dest.split(':')[1].strip())
        
        common_extensions = predicted_extensions & actual_extensions
        for ext in common_extensions:
            matches.append(f"Extension: {ext}")
        
        missing_ext = predicted_extensions - actual_extensions
        for ext in missing_ext:
            mismatches.append(f"Predicted extension {ext} but not reached")
        
        # Calculate score
        total_predictions = len(predicted_components) + len(predicted_extensions)
        if total_predictions > 0:
            score = (len(matches) / total_predictions) * 100
        else:
            score = 0.0
        
        return {
            'score': score,
            'matches': matches,
            'mismatches': mismatches,
            'predicted_components': [str(item) for item in predicted_components],
            'actual_components': [str(item) for item in actual_components],
            'predicted_extensions': [str(item) for item in predicted_extensions],
            'actual_extensions': [str(item) for item in actual_extensions]
        }

def main():
    parser = argparse.ArgumentParser(description='FreePBX Call Flow Validator')
    parser.add_argument('did', help='DID number to validate')
    parser.add_argument('--server', default='69.39.69.102', help='Server IP (default: 69.39.69.102)')
    parser.add_argument('--user', default='123net', help='SSH user (default: 123net)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    # Handle both new and old argument formats
    if len(sys.argv) >= 2 and not sys.argv[1].startswith('-') and '--' not in ' '.join(sys.argv):
        # Old format: script.py DID [server] [user] (no -- flags present)
        did = sys.argv[1]
        server_ip = sys.argv[2] if len(sys.argv) > 2 else "69.39.69.102"
        ssh_user = sys.argv[3] if len(sys.argv) > 3 else "123net"
        debug = False
    else:
        # New format with argparse
        if len(sys.argv) < 2:
            print("Usage: python3 callflow_validator.py <DID> [--server IP] [--user USER] [--debug]")
            print("Example: python3 callflow_validator.py 2485815200 --debug")
            sys.exit(1)
        
        args = parser.parse_args()
        did = args.did
        server_ip = args.server
        ssh_user = args.user
        debug = args.debug
    
    # Initialize logging
    global logger
    logger = setup_logging(debug)
    
    logger.info("Starting FreePBX Call Flow Validator")
    logger.info(f"Arguments: DID={did}, Server={server_ip}, User={ssh_user}, Debug={debug}")
    
    validator = CallFlowValidator(server_ip, ssh_user, debug)
    
    print("🎯 FREEPBX CALL FLOW VALIDATOR")
    print("=" * 40)
    print(f"DID: {did}")
    print(f"Server: {server_ip}")
    print(f"User: {ssh_user}")
    if debug:
        print(f"Debug: ENABLED (logs to /tmp/callflow_validator.log)")
    
    try:
        result = validator.validate_call_flow(did)
        
        if result['success']:
            # Save results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = f"validation_{did}_{timestamp}.json"
            
            with open(results_file, 'w') as f:
                json.dump(result, f, indent=2)
            
            logger.info(f"Results saved to: {results_file}")
            print(f"\n💾 Results saved to: {results_file}")
            
            # Final assessment
            score = result['validation']['score']
            if score >= 90:
                print(f"\n🏆 EXCELLENT VALIDATION (Score: {score:.1f}%)")
                print("   Call flow prediction is highly accurate!")
                logger.info(f"Excellent validation score: {score:.1f}%")
            elif score >= 75:
                print(f"\n✅ GOOD VALIDATION (Score: {score:.1f}%)")
                print("   Call flow prediction is mostly accurate")
                logger.info(f"Good validation score: {score:.1f}%")
            elif score >= 50:
                print(f"\n⚠️  FAIR VALIDATION (Score: {score:.1f}%)")
                print("   Some discrepancies found - review needed")
                logger.warning(f"Fair validation score: {score:.1f}%")
            else:
                print(f"\n❌ POOR VALIDATION (Score: {score:.1f}%)")
                print("   Significant discrepancies - tool needs adjustment")
                logger.error(f"Poor validation score: {score:.1f}%")
        else:
            error_msg = f"Validation failed: {result['error']}"
            logger.error(error_msg)
            print(f"\n❌ {error_msg}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
        print("\n⚠️  Validation interrupted by user")
        sys.exit(0)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(f"\n❌ {error_msg}")
        sys.exit(1)

if __name__ == "__main__":
    main()