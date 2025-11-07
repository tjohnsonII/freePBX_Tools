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
        self.check_trunk_status()
        self.check_queue_performance()
        self.check_security_events()
        self.check_database_issues()
        
        return self.issues
    
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


if __name__ == "__main__":
    # Check root
    try:
        if os.geteuid() != 0:  # type: ignore
            print(f"{Colors.YELLOW}⚠️  This tool requires root access{Colors.RESET}")
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have geteuid
        pass
    
    # Parse hours argument
    hours = 1
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            print(f"{Colors.YELLOW}Invalid hours argument, using default: 1{Colors.RESET}")
    
    analyzer = LogAnalyzer()
    analyzer.analyze_last_n_hours(hours=hours)
    analyzer.print_summary()
