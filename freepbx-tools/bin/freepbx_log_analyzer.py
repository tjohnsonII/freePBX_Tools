#!/usr/bin/env python3
"""
FreePBX Log Analyzer - Automated issue detection
Analyzes Asterisk logs to detect errors, trunk issues, queue performance, and security events
Enhanced with SIP/Q.850 cause code mapping and error playbook references
"""

import os
import sys
import subprocess
import re
from datetime import datetime, timedelta
from collections import defaultdict

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'

# SIP/Q.850/Asterisk Cause Code Mapping
CAUSE_CODE_MAP = {
    # SIP Code: (Q.850, Description, Asterisk Cause, Meaning)
    '100': (1, 'Trying', 'CALL_UNALLOCATED', 'Call attempt in progress'),
    '180': (19, 'Ringing', 'NO_ANSWER', 'Phone ringing, not answered yet'),
    '181': (181, 'Call Forwarded', 'CALL_IS_BEING_FORWARDED', 'Call being forwarded'),
    '182': (182, 'Queued', 'QUEUED', 'Call placed in queue'),
    '200': (16, 'OK', 'NORMAL_CLEARING', 'Call completed successfully'),
    '400': (97, 'Bad Request', 'INVALID_MESSAGE', 'Malformed SIP message'),
    '401': (21, 'Unauthorized', 'CALL_REJECTED', 'Authentication required'),
    '403': (21, 'Forbidden', 'CALL_REJECTED', 'Call rejected by policy'),
    '404': (1, 'Not Found', 'UNALLOCATED_NUMBER', 'Number does not exist'),
    '408': (18, 'Request Timeout', 'NO_USER_RESPONSE', 'No response - NAT/firewall issue'),
    '480': (19, 'Unavailable', 'NO_ANSWER', 'User not registered or not answering'),
    '486': (17, 'Busy Here', 'USER_BUSY', 'Phone in use or call limit reached'),
    '487': (16, 'Terminated', 'NORMAL_CLEARING', 'Call cancelled by caller'),
    '488': (79, 'Not Acceptable', 'SERVICE_NOT_IMPLEMENTED', 'Codec or media negotiation failed'),
    '500': (41, 'Server Error', 'TEMPORARY_FAILURE', 'Upstream gateway failure'),
    '503': (34, 'Unavailable', 'CIRCUIT_CONGESTION', 'Trunk congestion / carrier down'),
    '603': (21, 'Decline', 'CALL_REJECTED', 'Call explicitly rejected'),
}

def lookup_cause_code(code):
    """Lookup SIP/Q.850 cause code and return explanation"""
    code_str = str(code).strip()
    if code_str in CAUSE_CODE_MAP:
        q850, desc, ast_cause, meaning = CAUSE_CODE_MAP[code_str]
        return {
            'sip': code_str,
            'q850': q850,
            'description': desc,
            'asterisk_cause': ast_cause,
            'meaning': meaning
        }
    return None

def format_cause_code(code_info):
    """Format cause code information for display"""
    if not code_info:
        return ""
    return (f"SIP {code_info['sip']} / Q.850 {code_info['q850']} "
            f"({code_info['description']}) → {code_info['meaning']}")

class LogAnalyzer:
    def __init__(self):
        self.full_log = "/var/log/asterisk/full"
        self.queue_log = "/var/log/asterisk/queue_log"
        self.cdr_log = "/var/log/asterisk/cdr-csv/Master.csv"
        self.issues = []
        
    def analyze_last_n_hours(self, hours=1):
        """Analyze logs from last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"{Colors.CYAN}🔍 Analyzing logs since {cutoff_str}{Colors.RESET}")
        print("=" * 70)
        
        self.check_errors(hours)
        self.evaluate_error_codes()  # NEW: Actively map error codes
        self.check_trunk_status()
        self.check_queue_performance()
        self.check_security_events()
        self.check_database_issues()
        
        return self.issues
    
    def evaluate_error_codes(self):
        """Evaluate logs and apply SIP/Q.850 error code mapping"""
        if not os.path.exists(self.full_log):
            return
        
        print(f"\n{Colors.CYAN}{Colors.BOLD}📋 Error Code Evaluation (with mapping):{Colors.RESET}")
        
        # Search for SIP response codes and hangup causes
        cmd = f"tail -2000 {self.full_log} | grep -E 'SIP/2\\.0|hangupcause|Cause:|Response:'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              universal_newlines=True, timeout=10)
        
        if not result.stdout.strip():
            print(f"  {Colors.GREEN}No error codes found in recent logs{Colors.RESET}")
            return
        
        lines = result.stdout.strip().split('\n')
        
        # Extract and count SIP codes
        sip_codes = {}  # type: dict[str, dict]
        hangup_causes = {}  # type: dict[str, dict]
        
        for line in lines:
            # Look for SIP response codes
            sip_match = re.search(r'SIP/2\.0\s+(\d{3})\s+(.+?)(?:\r|\n|$)', line)
            if sip_match:
                code = sip_match.group(1)
                if code not in sip_codes:
                    sip_codes[code] = {'count': 0, 'samples': []}
                sip_codes[code]['count'] += 1
                if len(sip_codes[code]['samples']) < 3:
                    sip_codes[code]['samples'].append(line[:100])
            
            # Look for hangup causes
            cause_match = re.search(r'(?:hangupcause[=:]\s*(\d+)|Cause:\s*(\d+))', line, re.IGNORECASE)
            if cause_match:
                cause = cause_match.group(1) or cause_match.group(2)
                if cause not in hangup_causes:
                    hangup_causes[cause] = {'count': 0, 'samples': []}
                hangup_causes[cause]['count'] += 1
                if len(hangup_causes[cause]['samples']) < 2:
                    hangup_causes[cause]['samples'].append(line[:80])
        
        # Display SIP codes with mapping
        if sip_codes:
            print(f"\n{Colors.YELLOW}  SIP Response Codes Found:{Colors.RESET}")
            print(f"  {'─'*70}")
            
            for code in sorted(sip_codes.keys(), key=lambda x: sip_codes[x]['count'], reverse=True)[:10]:
                count = sip_codes[code]['count']
                cause_info = lookup_cause_code(code)
                
                if cause_info:
                    print(f"  {Colors.WHITE}SIP {code}{Colors.RESET} × {Colors.YELLOW}{count}{Colors.RESET} occurrences")
                    print(f"    └─ {Colors.CYAN}Q.850 Cause: {cause_info['q850']} ({cause_info['description']}){Colors.RESET}")
                    print(f"    └─ {Colors.GREEN}Meaning: {cause_info['meaning']}{Colors.RESET}")
                    print(f"    └─ {Colors.MAGENTA}Asterisk: {cause_info['asterisk_cause']}{Colors.RESET}")
                    
                    # Add to issues if significant
                    if count > 10 and code not in ['200', '100', '180', '183']:
                        severity = "HIGH" if code in ['503', '500', '408'] else "MEDIUM"
                        self.issues.append({
                            "severity": severity,
                            "category": "SIP Errors",
                            "message": f"SIP {code} ({cause_info['description']}): {count} occurrences",
                            "details": [cause_info['meaning']],
                            "playbook": f"📖 Common cause: {cause_info['meaning']}"
                        })
                else:
                    print(f"  {Colors.WHITE}SIP {code}{Colors.RESET} × {Colors.YELLOW}{count}{Colors.RESET} occurrences")
                    print(f"    └─ {Colors.YELLOW}(No mapping available){Colors.RESET}")
                
                # Show sample
                if sip_codes[code]['samples']:
                    print(f"    └─ Sample: {Colors.WHITE}{sip_codes[code]['samples'][0][:60]}...{Colors.RESET}")
                print()
        
        # Display hangup causes with Q.850 mapping
        if hangup_causes:
            print(f"\n{Colors.YELLOW}  Hangup Causes Found:{Colors.RESET}")
            print(f"  {'─'*70}")
            
            # Q.850 to description mapping (reverse lookup)
            q850_descriptions = {
                '1': 'Unallocated number',
                '16': 'Normal call clearing',
                '17': 'User busy',
                '18': 'No user responding',
                '19': 'No answer',
                '21': 'Call rejected',
                '34': 'Circuit/channel unavailable',
                '41': 'Temporary failure',
                '97': 'Invalid message',
            }
            
            for cause in sorted(hangup_causes.keys(), key=lambda x: hangup_causes[x]['count'], reverse=True)[:8]:
                count = hangup_causes[cause]['count']
                desc = q850_descriptions.get(cause, 'Unknown cause')
                
                print(f"  {Colors.WHITE}Q.850 Cause {cause}{Colors.RESET} × {Colors.YELLOW}{count}{Colors.RESET} occurrences")
                print(f"    └─ {Colors.CYAN}{desc}{Colors.RESET}")
                
                if hangup_causes[cause]['samples']:
                    print(f"    └─ Sample: {Colors.WHITE}{hangup_causes[cause]['samples'][0][:60]}...{Colors.RESET}")
                print()
        
        if not sip_codes and not hangup_causes:
            print(f"  {Colors.GREEN}✓ No error codes found in recent logs{Colors.RESET}")

    
    def check_errors(self, hours):
        """Count errors and warnings with cause code analysis"""
        if not os.path.exists(self.full_log):
            print(f"{Colors.YELLOW}⚠️  Log file not found: {self.full_log}{Colors.RESET}")
            return
        
        cmd = f"tail -1000 {self.full_log} | grep -E 'ERROR|CRITICAL|hangupcause'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        errors = result.stdout.strip().split('\n') if result.stdout.strip() else []
        error_count = len([e for e in errors if 'ERROR' in e or 'CRITICAL' in e])
        
        # Extract hangup causes and SIP codes
        hangup_causes = defaultdict(int)
        sip_codes = defaultdict(int)
        
        for line in errors:
            # Look for SIP response codes
            sip_match = re.search(r'SIP/2\.0\s+(\d{3})', line)
            if sip_match:
                sip_codes[sip_match.group(1)] += 1
            
            # Look for hangup causes
            cause_match = re.search(r'hangupcause[=:]\s*(\d+)', line, re.IGNORECASE)
            if cause_match:
                hangup_causes[cause_match.group(1)] += 1
        
        if error_count > 0:
            self.issues.append({
                "severity": "HIGH",
                "category": "Errors",
                "message": f"Found {error_count} errors in last 1000 lines",
                "details": errors[-10:],
                "playbook": "📖 See: Database Connectivity / Codec Negotiation sections"
            })
            
            # Count by type
            error_types = defaultdict(int)
            for line in errors:
                if 'ERROR' in line or 'CRITICAL' in line:
                    # Extract error message (simplified)
                    match = re.search(r'(ERROR|CRITICAL).*?:\s*(.+?)$', line)
                    if match:
                        error_msg = match.group(2)[:80]  # First 80 chars
                        error_types[error_msg] += 1
            
            if error_types:
                print(f"\n{Colors.RED}📊 Error Summary:{Colors.RESET}")
                for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  {count:>4}x {msg}")
        
        # Display SIP code analysis
        if sip_codes:
            print(f"\n{Colors.CYAN}📞 SIP Response Code Analysis:{Colors.RESET}")
            for code, count in sorted(sip_codes.items(), key=lambda x: x[1], reverse=True)[:5]:
                cause_info = lookup_cause_code(code)
                if cause_info:
                    print(f"  {count:>4}x SIP {code} - {Colors.YELLOW}{cause_info['description']}{Colors.RESET}")
                    print(f"         └─ {Colors.CYAN}{cause_info['meaning']}{Colors.RESET}")
                else:
                    print(f"  {count:>4}x SIP {code}")
        
        if not error_count and not sip_codes:
            print(f"\n{Colors.GREEN}✅ No errors found in recent logs{Colors.RESET}")
    
    def check_trunk_status(self):
        """Check trunk registration and failures with playbook reference"""
        if not os.path.exists(self.full_log):
            return
        
        cmd = f"tail -500 {self.full_log} | grep -E 'trunk.*Unreachable|Registration.*failed'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        if result.stdout.strip():
            trunk_issues = result.stdout.strip().split('\n')
            self.issues.append({
                "severity": "CRITICAL",
                "category": "Trunk",
                "message": f"Trunk connectivity issues detected",
                "details": trunk_issues,
                "playbook": "📖 Playbook: Trunk Offline / Registration Loss"
            })
            print(f"\n{Colors.RED}🔴 TRUNK ISSUES DETECTED:{Colors.RESET}")
            for issue in trunk_issues[-5:]:
                print(f"  {issue[:120]}")
            print(f"\n{Colors.MAGENTA}📖 Response Playbook:{Colors.RESET}")
            print(f"  1. Run: grep -E \"Registration.*failed|qualify.*Unreachable\" /var/log/asterisk/full | tail -50")
            print(f"  2. Identify affected endpoints and timestamps")
            print(f"  3. Notify carrier/network team for registration recovery")
        else:
            print(f"\n{Colors.GREEN}✅ No trunk issues detected{Colors.RESET}")
    
    def check_queue_performance(self):
        """Analyze queue metrics"""
        if not os.path.exists(self.queue_log):
            return
        
        cmd = f"tail -500 {self.queue_log}"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        enters = 0
        abandons = 0
        connects = 0
        wait_times = []
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|')
            if len(parts) < 6:
                continue
            
            event = parts[4]
            if event == "ENTERQUEUE":
                enters += 1
            elif event == "ABANDON":
                abandons += 1
            elif event == "CONNECT":
                connects += 1
                try:
                    wait_time = int(parts[5])
                    wait_times.append(wait_time)
                except (ValueError, IndexError):
                    pass
        
        if enters > 0:
            abandon_rate = (abandons / enters) * 100
            avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
            
            print(f"\n{Colors.CYAN}📞 Queue Performance (last 500 events):{Colors.RESET}")
            print(f"  Calls entered: {enters}")
            print(f"  Answered:      {connects} ({(connects/enters)*100:.1f}%)")
            print(f"  Abandoned:     {abandons} ({abandon_rate:.1f}%)")
            print(f"  Avg wait time: {avg_wait:.1f}s")
            
            if abandon_rate > 20:
                self.issues.append({
                    "severity": "HIGH",
                    "category": "Queue",
                    "message": f"High abandon rate: {abandon_rate:.1f}%",
                    "details": [f"Abandons: {abandons}/{enters}"]
                })
            
            if avg_wait > 60:
                self.issues.append({
                    "severity": "MEDIUM",
                    "category": "Queue",
                    "message": f"Long average wait time: {avg_wait:.1f}s",
                    "details": [f"Average: {avg_wait:.1f}s, Max: {max(wait_times) if wait_times else 0}s"]
                })
    
    def check_security_events(self):
        """Check for authentication failures and attacks with playbook"""
        if not os.path.exists(self.full_log):
            return
        
        cmd = f"tail -500 {self.full_log} | grep -i 'failed.*auth\\|SECURITY'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        if result.stdout.strip():
            security_events = result.stdout.strip().split('\n')
            
            # Extract IPs
            ips = defaultdict(int)
            for line in security_events:
                ip_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', line)
                if ip_match:
                    ips[ip_match.group(0)] += 1
            
            if len(security_events) > 20:
                self.issues.append({
                    "severity": "HIGH",
                    "category": "Security",
                    "message": f"Multiple authentication failures: {len(security_events)}",
                    "details": [f"{ip}: {count} attempts" for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:10]],
                    "playbook": "📖 Playbook: Authentication Storm / SIP Attack"
                })
                print(f"\n{Colors.YELLOW}🔒 Security Events:{Colors.RESET}")
                for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  {ip}: {count} failed attempts")
                
                print(f"\n{Colors.MAGENTA}📖 Response Playbook:{Colors.RESET}")
                print(f"  1. Validate volume: grep -i \"failed.*auth\" /var/log/asterisk/full | tail -50")
                print(f"  2. Block abusive IPs: {', '.join(list(ips.keys())[:3])}")
                print(f"  3. Check fail2ban status and coordinate with security operations")
            else:
                print(f"\n{Colors.GREEN}✅ No significant security issues{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    
    def check_database_issues(self):
        """Check for database connection problems with playbook"""
        if not os.path.exists(self.full_log):
            return
        
        cmd = f"tail -500 {self.full_log} | grep -i 'database.*fail\\|mysql.*error\\|mysql.*gone away'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        if result.stdout.strip():
            db_issues = result.stdout.strip().split('\n')
            self.issues.append({
                "severity": "CRITICAL",
                "category": "Database",
                "message": "Database connectivity issues",
                "details": db_issues,
                "playbook": "📖 Playbook: Database Connectivity Failure"
            })
            print(f"\n{Colors.RED}🔴 DATABASE ISSUES:{Colors.RESET}")
            for issue in db_issues[-5:]:
                print(f"  {issue[:120]}")
            
            print(f"\n{Colors.MAGENTA}📖 Response Playbook:{Colors.RESET}")
            print(f"  1. Confirm: grep -i \"database.*fail|mysql.*error\" /var/log/asterisk/full | tail -20")
            print(f"  2. Check MariaDB status: systemctl status mariadb")
            print(f"  3. Escalate with log snippet and concurrent GUI errors")
        else:
            print(f"\n{Colors.GREEN}✅ No database issues detected{Colors.RESET}")
    
    def print_summary(self):
        """Print issue summary"""
        if not self.issues:
            print(f"\n{Colors.GREEN}{'=' * 70}{Colors.RESET}")
            print(f"{Colors.GREEN}{Colors.BOLD}✅ No significant issues detected!{Colors.RESET}")
            print(f"{Colors.GREEN}{'=' * 70}{Colors.RESET}")
            return
        
        print("\n" + "=" * 70)
        print(f"{Colors.BOLD}📋 ISSUES SUMMARY{Colors.RESET}")
        print("=" * 70)
        
        critical = [i for i in self.issues if i["severity"] == "CRITICAL"]
        high = [i for i in self.issues if i["severity"] == "HIGH"]
        medium = [i for i in self.issues if i["severity"] == "MEDIUM"]
        
        if critical:
            print(f"\n{Colors.RED}🔴 CRITICAL ({len(critical)}):{Colors.RESET}")
            for issue in critical:
                print(f"  • [{issue['category']}] {issue['message']}")
        
        if high:
            print(f"\n{Colors.YELLOW}🟠 HIGH ({len(high)}):{Colors.RESET}")
            for issue in high:
                print(f"  • [{issue['category']}] {issue['message']}")
        
        if medium:
            print(f"\n{Colors.YELLOW}🟡 MEDIUM ({len(medium)}):{Colors.RESET}")
            for issue in medium:
                print(f"  • [{issue['category']}] {issue['message']}")
        
        print("\n" + "=" * 70)
    
    def analyze_dmesg(self):
        """Analyze kernel ring buffer for hardware/driver issues"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  🔍 KERNEL LOG ANALYSIS (dmesg)")
        print(f"{'='*70}{Colors.RESET}\n")
        
        try:
            result = subprocess.run(
                ["dmesg", "-T"],  # -T for human-readable timestamps
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                print(f"{Colors.RED}❌ Failed to read dmesg{Colors.RESET}")
                return
            
            lines = result.stdout.strip().split('\n')
            
            # Key patterns to search for
            patterns = {
                'hardware_errors': r'(?i)(hardware error|I/O error|disk error|corrected|uncorrected)',
                'network_issues': r'(?i)(link down|link up|eth\d+:|network|timeout|unreachable)',
                'memory_issues': r'(?i)(out of memory|oom|memory allocation|page allocation)',
                'driver_issues': r'(?i)(driver|module.*failed|unable to load|firmware)',
                'dahdi_issues': r'(?i)(dahdi|wctdm|wcte|opvxa|tdm|timing)',
                'usb_issues': r'(?i)(usb|device disconnect|reset.*device)',
            }
            
            findings = defaultdict(list)
            
            for line in lines[-1000:]:  # Last 1000 kernel messages
                for category, pattern in patterns.items():
                    if re.search(pattern, line):
                        findings[category].append(line)
            
            # Display findings
            if findings:
                for category, matches in findings.items():
                    if matches:
                        print(f"{Colors.YELLOW}  {category.replace('_', ' ').title()}:{Colors.RESET}")
                        for match in matches[-5:]:  # Show last 5
                            print(f"    {Colors.WHITE}{match[:90]}{Colors.RESET}")
                        if len(matches) > 5:
                            print(f"    {Colors.CYAN}... and {len(matches)-5} more{Colors.RESET}")
                        print()
                        
                        self.issues.append({
                            'type': category,
                            'severity': 'high' if 'error' in category else 'medium',
                            'count': len(matches)
                        })
            else:
                print(f"{Colors.GREEN}✅ No significant kernel issues found{Colors.RESET}")
                
        except Exception as e:
            print(f"{Colors.RED}❌ Error analyzing dmesg: {str(e)}{Colors.RESET}")
    
    def analyze_journalctl(self, hours=1):
        """Analyze systemd journal for service issues"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  📰 SYSTEMD JOURNAL ANALYSIS (journalctl)")
        print(f"{'='*70}{Colors.RESET}\n")
        
        try:
            # Get journal entries from last N hours
            since = f"-{hours}h"
            
            # Key services to monitor
            services = [
                'asterisk',
                'dahdi',
                'freepbx',
                'httpd',
                'apache2',
                'mysql',
                'mariadb',
                'network',
            ]
            
            print(f"{Colors.CYAN}Analyzing last {hours} hour(s) of system journal...{Colors.RESET}\n")
            
            # Check for errors across all services
            result = subprocess.run(
                ["journalctl", "--since", since, "-p", "err", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                print(f"{Colors.YELLOW}  System Errors ({len(lines)} found):{Colors.RESET}")
                
                # Group by service
                error_groups = defaultdict(list)
                for line in lines:
                    # Extract service name
                    service_match = re.search(r'(\w+)\[\d+\]:', line)
                    service = service_match.group(1) if service_match else 'unknown'
                    error_groups[service].append(line)
                
                for service, errors in sorted(error_groups.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
                    print(f"    {Colors.WHITE}{service}:{Colors.RESET} {Colors.RED}{len(errors)}{Colors.RESET} errors")
                    for error in errors[-3:]:  # Show last 3
                        print(f"      └─ {Colors.WHITE}{error[:80]}{Colors.RESET}")
                    print()
                    
                    self.issues.append({
                        'type': f'journal_{service}_errors',
                        'severity': 'high',
                        'count': len(errors)
                    })
            else:
                print(f"{Colors.GREEN}✅ No system errors in journal{Colors.RESET}")
            
            # Check specific services
            print(f"\n{Colors.CYAN}Service Status:{Colors.RESET}")
            for service in services:
                try:
                    status_result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    status = status_result.stdout.strip()
                    
                    if status == "active":
                        print(f"  {Colors.GREEN}✅ {service:<15} {Colors.BOLD}active{Colors.RESET}")
                    elif status == "inactive":
                        print(f"  {Colors.YELLOW}⚠️  {service:<15} {Colors.BOLD}inactive{Colors.RESET}")
                    elif status == "failed":
                        print(f"  {Colors.RED}❌ {service:<15} {Colors.BOLD}failed{Colors.RESET}")
                        self.issues.append({
                            'type': f'service_{service}_failed',
                            'severity': 'high',
                            'count': 1
                        })
                    else:
                        print(f"  {Colors.WHITE}○  {service:<15} {status}{Colors.RESET}")
                except:
                    pass  # Service doesn't exist
                    
        except Exception as e:
            print(f"{Colors.RED}❌ Error analyzing journal: {str(e)}{Colors.RESET}")
    
    def grep_logs_with_regex(self, log_file, pattern, context_lines=2):
        """Search log files with regex patterns and show context"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  🔎 REGEX SEARCH: {log_file}")
        print(f"  Pattern: {pattern}")
        print(f"{'='*70}{Colors.RESET}\n")
        
        if not os.path.exists(log_file):
            print(f"{Colors.RED}❌ Log file not found: {log_file}{Colors.RESET}")
            return []
        
        try:
            # Use grep with context for better performance on large files
            cmd = ["grep", "-E", "-n", "-i"]
            if context_lines > 0:
                cmd.extend(["-A", str(context_lines), "-B", str(context_lines)])
            cmd.extend([pattern, log_file])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            matches = []
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                matches = lines
                
                print(f"{Colors.GREEN}✅ Found {len(lines)} matching lines{Colors.RESET}\n")
                
                # Show first 20 matches
                for line in lines[:20]:
                    # Color the matching part
                    colored_line = re.sub(
                        f'({pattern})',
                        f'{Colors.YELLOW}\\1{Colors.RESET}',
                        line,
                        flags=re.IGNORECASE
                    )
                    print(f"  {Colors.WHITE}{colored_line}{Colors.RESET}")
                
                if len(lines) > 20:
                    print(f"\n  {Colors.CYAN}... and {len(lines)-20} more matches{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}No matches found{Colors.RESET}")
            
            return matches
            
        except Exception as e:
            print(f"{Colors.RED}❌ Error searching logs: {str(e)}{Colors.RESET}")
            return []
    
    def search_asterisk_logs(self, pattern_name=None):
        """Pre-defined regex searches for common Asterisk issues"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  🔍 ASTERISK LOG PATTERN SEARCH")
        print(f"{'='*70}{Colors.RESET}\n")
        
        # Common search patterns
        patterns = {
            'authentication_failures': r'(?i)(authentication failed|wrong password|failed to authenticate)',
            'codec_issues': r'(?i)(codec|unable to negotiate|no common codec)',
            'registration_failures': r'(?i)(registration.*failed|unable to register|registration denied)',
            'trunk_errors': r'(?i)(trunk.*(?:down|failed|unavailable)|sip.*(?:unreachable|timeout))',
            'database_errors': r'(?i)(database.*(?:error|failed)|mysql.*(?:error|connect)|lost connection)',
            'memory_issues': r'(?i)(out of.*(?:memory|descriptors)|allocation failed|too many)',
            'deadlocks': r'(?i)(deadlock|timeout.*lock|waiting for lock)',
            'segfault': r'(?i)(segmentation fault|sigsegv|core dump|signal 11)',
        }
        
        if pattern_name and pattern_name in patterns:
            # Search for specific pattern
            self.grep_logs_with_regex(self.full_log, patterns[pattern_name])
        else:
            # Search all patterns
            print(f"{Colors.YELLOW}Searching for common issues...{Colors.RESET}\n")
            
            for name, pattern in patterns.items():
                print(f"{Colors.CYAN}Checking: {name.replace('_', ' ').title()}{Colors.RESET}")
                matches = self.grep_logs_with_regex(self.full_log, pattern, context_lines=0)
                
                if matches:
                    print(f"  {Colors.RED}⚠️  Found {len(matches)} occurrences{Colors.RESET}")
                    self.issues.append({
                        'type': name,
                        'severity': 'high' if any(x in name for x in ['segfault', 'deadlock', 'database']) else 'medium',
                        'count': len(matches)
                    })
                else:
                    print(f"  {Colors.GREEN}✅ None found{Colors.RESET}")
                print()


if __name__ == "__main__":
    # Check root
    try:
        if os.geteuid() != 0:  # type: ignore
            print(f"{Colors.YELLOW}⚠️  This tool requires root access{Colors.RESET}")
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have geteuid
        pass
    
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="FreePBX Log Analyzer with Error Code Mapping")
    parser.add_argument("--hours", type=int, default=1, help="Analyze logs from last N hours (default: 1)")
    parser.add_argument("--codes-only", action="store_true", help="Only evaluate and map error codes")
    parser.add_argument("--lookup", type=str, help="Look up a specific SIP code (e.g., --lookup 486)")
    parser.add_argument("--dmesg", action="store_true", help="Analyze kernel logs (dmesg)")
    parser.add_argument("--journal", action="store_true", help="Analyze systemd journal")
    parser.add_argument("--grep", type=str, metavar="PATTERN", help="Search logs with regex pattern")
    parser.add_argument("--log-file", type=str, default="/var/log/asterisk/full", help="Log file to search (with --grep)")
    parser.add_argument("--search-patterns", action="store_true", help="Search for common Asterisk issues")
    parser.add_argument("--comprehensive", action="store_true", help="Run all analyses (full + dmesg + journal + patterns)")
    
    args = parser.parse_args()
    
    # Handle lookup mode
    if args.lookup:
        code_info = lookup_cause_code(args.lookup)
        if code_info:
            print(f"\n{Colors.CYAN}{Colors.BOLD}SIP Code {args.lookup} Lookup:{Colors.RESET}")
            print(f"  SIP Response: {Colors.YELLOW}{code_info['sip']}{Colors.RESET}")
            print(f"  Q.850 Cause:  {Colors.GREEN}{code_info['q850']}{Colors.RESET}")
            print(f"  Description:  {Colors.CYAN}{code_info['description']}{Colors.RESET}")
            print(f"  Asterisk:     {Colors.MAGENTA}{code_info['asterisk_cause']}{Colors.RESET}")
            print(f"  Meaning:      {Colors.WHITE}{code_info['meaning']}{Colors.RESET}")
        else:
            print(f"{Colors.RED}No mapping found for SIP code {args.lookup}{Colors.RESET}")
        sys.exit(0)
    
    analyzer = LogAnalyzer()
    
    # Handle codes-only mode
    if args.codes_only:
        print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  📋 Error Code Evaluation Only")
        print(f"{'='*70}{Colors.RESET}\n")
        analyzer.evaluate_error_codes()
        sys.exit(0)
    
    # Handle dmesg mode
    if args.dmesg:
        analyzer.analyze_dmesg()
        analyzer.print_summary()
        sys.exit(0)
    
    # Handle journal mode
    if args.journal:
        analyzer.analyze_journalctl(hours=args.hours)
        analyzer.print_summary()
        sys.exit(0)
    
    # Handle grep mode
    if args.grep:
        analyzer.grep_logs_with_regex(args.log_file, args.grep, context_lines=2)
        sys.exit(0)
    
    # Handle pattern search mode
    if args.search_patterns:
        analyzer.search_asterisk_logs()
        analyzer.print_summary()
        sys.exit(0)
    
    # Handle comprehensive mode
    if args.comprehensive:
        print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}")
        print(f"  🔬 COMPREHENSIVE SYSTEM ANALYSIS")
        print(f"{'='*70}{Colors.RESET}\n")
        
        analyzer.analyze_last_n_hours(hours=args.hours)
        analyzer.analyze_dmesg()
        analyzer.analyze_journalctl(hours=args.hours)
        analyzer.search_asterisk_logs()
        analyzer.print_summary()
        sys.exit(0)
    
    # Full analysis (default)
    analyzer.analyze_last_n_hours(hours=args.hours)
    analyzer.print_summary()
