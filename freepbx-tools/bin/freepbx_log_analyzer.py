#!/usr/bin/env python3
"""
FreePBX Log Analyzer - Automated issue detection
Analyzes Asterisk logs to detect errors, trunk issues, queue performance, and security events
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
        """Count errors and warnings"""
        if not os.path.exists(self.full_log):
            print(f"{Colors.YELLOW}⚠️  Log file not found: {self.full_log}{Colors.RESET}")
            return
        
        cmd = f"tail -1000 {self.full_log} | grep -E 'ERROR|CRITICAL'"
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        errors = result.stdout.strip().split('\n') if result.stdout.strip() else []
        error_count = len([e for e in errors if e])
        
        if error_count > 0:
            self.issues.append({
                "severity": "HIGH",
                "category": "Errors",
                "message": f"Found {error_count} errors in last 1000 lines",
                "details": errors[-10:]  # Last 10 errors
            })
            
            # Count by type
            error_types = defaultdict(int)
            for line in errors:
                if line:
                    # Extract error message (simplified)
                    match = re.search(r'(ERROR|CRITICAL).*?:\s*(.+?)$', line)
                    if match:
                        error_msg = match.group(2)[:80]  # First 80 chars
                        error_types[error_msg] += 1
            
            if error_types:
                print(f"\n{Colors.RED}📊 Error Summary:{Colors.RESET}")
                for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  {count:>4}x {msg}")
        else:
            print(f"\n{Colors.GREEN}✅ No errors found in recent logs{Colors.RESET}")
    
    def check_trunk_status(self):
        """Check trunk registration and failures"""
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
                "details": trunk_issues
            })
            print(f"\n{Colors.RED}🔴 TRUNK ISSUES DETECTED:{Colors.RESET}")
            for issue in trunk_issues[-5:]:
                print(f"  {issue[:120]}")
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
        """Check for authentication failures and attacks"""
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
                    "details": [f"{ip}: {count} attempts" for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:10]]
                })
                print(f"\n{Colors.YELLOW}🔒 Security Events:{Colors.RESET}")
                for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  {ip}: {count} failed attempts")
            else:
                print(f"\n{Colors.GREEN}✅ No significant security issues{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}✅ No security issues detected{Colors.RESET}")
    
    def check_database_issues(self):
        """Check for database connection problems"""
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
                "details": db_issues
            })
            print(f"\n{Colors.RED}🔴 DATABASE ISSUES:{Colors.RESET}")
            for issue in db_issues[-5:]:
                print(f"  {issue[:120]}")
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
