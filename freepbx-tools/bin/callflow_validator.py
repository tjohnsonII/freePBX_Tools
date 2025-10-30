#!/usr/bin/env python3
"""
Call Flow Validation through Live Simulation
Compare predicted call flows with actual Asterisk behavior
"""

import sys
import subprocess
import time
import json
import re
from datetime import datetime

class CallFlowValidator:
    def __init__(self, server_ip="69.39.69.102", ssh_user="123net"):
        self.server_ip = server_ip
        self.ssh_user = ssh_user
        self.callflow_tool = "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py"
        
    def get_predicted_flow(self, did):
        """Get predicted call flow from our ASCII tool"""
        try:
            # Check if we're running on the same server - if so, run locally
            import socket
            local_hostname = socket.gethostname()
            local_ip = socket.gethostbyname(local_hostname)
            
            if self.server_ip in ['localhost', '127.0.0.1', local_ip] or local_hostname.startswith('pbx'):
                # Run locally instead of SSH
                cmd = ["python3", self.callflow_tool, "--did", did]
            else:
                # Run via SSH for remote servers
                cmd = ["ssh", f"{self.ssh_user}@{self.server_ip}", 
                       f"python3 {self.callflow_tool} --did {did}"]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=30)
            
            if result.returncode == 0:
                return self._parse_callflow_output(result.stdout)
            else:
                return {'error': f"Tool failed: {result.stderr}"}
                
        except Exception as e:
            return {'error': f"Exception: {str(e)}"}
    
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
        print(f"🚀 Simulating call to {did} and monitoring behavior...")
        
        # Clear Asterisk logs before test
        self._clear_asterisk_logs()
        
        # Create and execute call file
        call_result = self._execute_test_call(did, caller_id)
        
        if not call_result['success']:
            return {'error': f"Call simulation failed: {call_result['error']}"}
        
        # Wait for call processing
        time.sleep(5)
        
        # Analyze Asterisk logs
        log_analysis = self._analyze_asterisk_logs(call_result['call_id'])
        
        return {
            'call_successful': call_result['success'],
            'call_processed': call_result.get('processed', False),
            'log_analysis': log_analysis,
            'call_id': call_result['call_id'],
            'timestamp': datetime.now().isoformat()
        }
    
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
        
        # Create call file content
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
        
        try:
            # Create call file on server
            cmd = f'cat > {temp_file} << "EOF"\n{call_content}EOF'
            result = subprocess.run([
                "ssh", f"{self.ssh_user}@{self.server_ip}", cmd
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
            
            if result.returncode != 0:
                return {'success': False, 'error': f"Failed to create call file: {result.stderr}"}
            
            # Set ownership
            subprocess.run([
                "ssh", f"{self.ssh_user}@{self.server_ip}", 
                f"chown asterisk:asterisk {temp_file}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            
            # Move to spool directory
            move_result = subprocess.run([
                "ssh", f"{self.ssh_user}@{self.server_ip}", 
                f"mv {temp_file} {spool_file}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            
            if move_result.returncode != 0:
                return {'success': False, 'error': f"Failed to spool call: {move_result.stderr}"}
            
            # Check if processed
            time.sleep(2)
            check_result = subprocess.run([
                "ssh", f"{self.ssh_user}@{self.server_ip}", 
                f"test -f {spool_file} && echo 'EXISTS' || echo 'PROCESSED'"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
            
            processed = "PROCESSED" in check_result.stdout
            
            return {
                'success': True,
                'call_id': call_id,
                'processed': processed
            }
            
        except Exception as e:
            return {'success': False, 'error': f"Exception: {str(e)}"}
    
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
        print(f"\n🔍 VALIDATING CALL FLOW FOR DID: {did}")
        print("=" * 60)
        
        # Step 1: Get predicted flow
        print("📊 Step 1: Getting predicted call flow...")
        predicted = self.get_predicted_flow(did)
        
        if 'error' in predicted:
            print(f"   ❌ Failed to get prediction: {predicted['error']}")
            return {'success': False, 'error': predicted['error']}
        
        print(f"   ✅ Predicted components: {', '.join(str(c) for c in predicted.get('components', []))}")
        print(f"   📞 Predicted extensions: {', '.join(str(e) for e in predicted.get('extensions', []))}")
        
        # Step 2: Simulate actual call
        print("\n🚀 Step 2: Simulating actual call...")
        actual = self.simulate_call_and_monitor(did)
        
        if 'error' in actual:
            print(f"   ❌ Simulation failed: {actual['error']}")
            return {'success': False, 'error': actual['error']}
        
        print(f"   ✅ Call processed: {actual['call_processed']}")
        
        # Safely access log analysis data
        log_analysis = actual.get('log_analysis', {})
        if not isinstance(log_analysis, dict) or 'error' in log_analysis:
            error_msg = log_analysis.get('error', str(log_analysis)) if isinstance(log_analysis, dict) else str(log_analysis)
            print(f"   ⚠️  Log analysis error: {error_msg}")
        else:
            components = log_analysis.get('components_hit', [])
            destinations = log_analysis.get('destinations_reached', [])
            
            # Ensure components and destinations are lists of strings
            components = [str(c) for c in components] if components else []
            destinations = [str(d) for d in destinations] if destinations else []
            
            print(f"   🔍 Components hit: {', '.join(components) if components else 'None'}")
            print(f"   📍 Destinations reached: {', '.join(destinations) if destinations else 'None'}")
        
        # Step 3: Compare and validate
        print("\n⚖️  Step 3: Comparing prediction vs reality...")
        validation_result = self._compare_flows(predicted, actual)
        
        print(f"   📊 Validation Score: {validation_result['score']:.1f}%")
        print(f"   ✅ Matches: {len(validation_result['matches'])}")
        print(f"   ❌ Mismatches: {len(validation_result['mismatches'])}")
        
        if validation_result['matches']:
            print(f"\n✅ MATCHES:")
            for match in validation_result['matches']:
                print(f"      {match}")
        
        if validation_result['mismatches']:
            print(f"\n❌ MISMATCHES:")
            for mismatch in validation_result['mismatches']:
                print(f"      {mismatch}")
        
        # Safely check for errors in log analysis
        log_analysis = actual.get('log_analysis', {})
        if isinstance(log_analysis, dict) and 'error' not in log_analysis and log_analysis.get('errors'):
            print(f"\n⚠️  ERRORS DETECTED:")
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
    if len(sys.argv) < 2:
        print("Usage: python3 callflow_validator.py <DID> [server_ip] [ssh_user]")
        print("Example: python3 callflow_validator.py 2485815200")
        sys.exit(1)
    
    did = sys.argv[1]
    server_ip = sys.argv[2] if len(sys.argv) > 2 else "69.39.69.102"
    ssh_user = sys.argv[3] if len(sys.argv) > 3 else "123net"
    
    validator = CallFlowValidator(server_ip, ssh_user)
    
    print("🎯 FREEPBX CALL FLOW VALIDATOR")
    print("=" * 40)
    print(f"DID: {did}")
    print(f"Server: {server_ip}")
    print(f"User: {ssh_user}")
    
    try:
        result = validator.validate_call_flow(did)
        
        if result['success']:
            # Save results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = f"validation_{did}_{timestamp}.json"
            
            with open(results_file, 'w') as f:
                json.dump(result, f, indent=2)
            
            print(f"\n💾 Results saved to: {results_file}")
            
            # Final assessment
            score = result['validation']['score']
            if score >= 90:
                print(f"\n🏆 EXCELLENT VALIDATION (Score: {score:.1f}%)")
                print("   Call flow prediction is highly accurate!")
            elif score >= 75:
                print(f"\n✅ GOOD VALIDATION (Score: {score:.1f}%)")
                print("   Call flow prediction is mostly accurate")
            elif score >= 50:
                print(f"\n⚠️  FAIR VALIDATION (Score: {score:.1f}%)")
                print("   Some discrepancies found - review needed")
            else:
                print(f"\n❌ POOR VALIDATION (Score: {score:.1f}%)")
                print("   Significant discrepancies - tool needs adjustment")
        else:
            print(f"\n❌ Validation failed: {result['error']}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()