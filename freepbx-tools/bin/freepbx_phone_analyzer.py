#!/usr/bin/env python3
"""
FreePBX Phone/Endpoint Analyzer
Analyzes phone registrations, configurations, firmware, and provisioning status
Supports: Polycom, Yealink, Cisco, Grandstream, Sangoma
"""

import subprocess
import re
import json
import sys
from datetime import datetime
from collections import defaultdict

class Colors:
    """ANSI color codes"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

class PhoneAnalyzer:
    """Analyze FreePBX phone endpoints and registrations"""
    
    def __init__(self, output_dir="/home/123net/phone_analysis"):
        self.output_dir = output_dir
        self.mysql_socket = self.find_mysql_socket()
        
        # 123NET standard configurations
        self.standard_firmware = {
            'polycom': {'vvx': '6.3.1', 'soundpoint': '4.0.15'},
            'yealink': {'t4x': '84.86.10.30', 't5x': '96.86.10.30', 'w60p': '77.86.10.30'},
            'cisco': {'spa': '7.6.2'},
            'grandstream': {'gxp': '1.0.20.18', 'gxv': '1.0.7.40'},
            'sangoma': {'s': '1.45.3'}
        }
        
    def find_mysql_socket(self):
        """Find MySQL socket file"""
        import os
        socket_paths = [
            '/var/lib/mysql/mysql.sock',
            '/var/run/mysqld/mysqld.sock',
            '/tmp/mysql.sock'
        ]
        for path in socket_paths:
            if os.path.exists(path):
                return path
        return '/var/lib/mysql/mysql.sock'
    
    def run_command(self, cmd, timeout=30):
        """Execute shell command"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                universal_newlines=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, '', 'Timeout'
        except Exception as e:
            return -1, '', str(e)
    
    def query_db(self, sql):
        """Query FreePBX MySQL database"""
        cmd = [
            'mysql', '-NBe', sql, 'asterisk',
            '-u', 'root',
            '-S', self.mysql_socket
        ]
        returncode, stdout, stderr = self.run_command(cmd)
        if returncode == 0:
            return [line.split('\t') for line in stdout.strip().split('\n') if line.strip()]
        return []
    
    def get_asterisk_cli(self, command):
        """Run Asterisk CLI command"""
        import os
        asterisk_paths = ["/usr/sbin/asterisk", "/usr/bin/asterisk", "asterisk"]
        for path in asterisk_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    returncode, stdout, stderr = self.run_command([path, "-rx", command])
                    if returncode == 0:
                        return stdout
                except:
                    continue
        return ""
    
    def analyze_sip_peers(self):
        """Analyze SIP peer registrations"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📱 SIP PEER REGISTRATION ANALYSIS{' ' * 42}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        output = self.get_asterisk_cli("sip show peers")
        if not output:
            print(f"{Colors.RED}❌ Unable to retrieve SIP peers{Colors.RESET}")
            return
        
        lines = output.strip().split('\n')
        peers = []
        online_count = 0
        offline_count = 0
        
        # Parse SIP peers
        for line in lines:
            if '/' in line and 'sip' in line.lower():
                parts = line.split()
                if len(parts) >= 5:
                    name = parts[0]
                    host = parts[1]
                    status = parts[5] if len(parts) > 5 else 'UNKNOWN'
                    
                    # Determine vendor from user agent or name
                    vendor = self.detect_vendor(name)
                    
                    if 'OK' in status or 'Registered' in status:
                        online_count += 1
                        status_color = Colors.GREEN
                        status_icon = "✓"
                    else:
                        offline_count += 1
                        status_color = Colors.RED
                        status_icon = "✗"
                    
                    peers.append({
                        'name': name,
                        'host': host,
                        'status': status,
                        'vendor': vendor,
                        'online': 'OK' in status or 'Registered' in status
                    })
        
        # Display summary
        print(f"{Colors.CYAN}📊 Registration Summary:{Colors.RESET}")
        print(f"  {Colors.GREEN}✓ Online:{Colors.RESET} {online_count}")
        print(f"  {Colors.RED}✗ Offline:{Colors.RESET} {offline_count}")
        print(f"  {Colors.CYAN}📱 Total Endpoints:{Colors.RESET} {len(peers)}\n")
        
        # Group by vendor
        by_vendor = defaultdict(list)
        for peer in peers:
            by_vendor[peer['vendor']].append(peer)
        
        print(f"{Colors.CYAN}📱 By Vendor:{Colors.RESET}")
        for vendor, vendor_peers in sorted(by_vendor.items()):
            online = sum(1 for p in vendor_peers if p['online'])
            total = len(vendor_peers)
            percentage = (online / total * 100) if total > 0 else 0
            print(f"  {Colors.YELLOW}{vendor}:{Colors.RESET} {online}/{total} online ({percentage:.1f}%)")
        
        return peers
    
    def detect_vendor(self, name_or_ua):
        """Detect phone vendor from name or user agent"""
        name_lower = name_or_ua.lower()
        
        if 'polycom' in name_lower or 'vvx' in name_lower or 'soundpoint' in name_lower:
            return 'Polycom'
        elif 'yealink' in name_lower or 'sip-t' in name_lower or 'w60' in name_lower:
            return 'Yealink'
        elif 'cisco' in name_lower or 'spa' in name_lower or 'cp-' in name_lower:
            return 'Cisco'
        elif 'grandstream' in name_lower or 'gxp' in name_lower or 'gxv' in name_lower:
            return 'Grandstream'
        elif 'sangoma' in name_lower or 's500' in name_lower or 's705' in name_lower:
            return 'Sangoma'
        elif 'algo' in name_lower:
            return 'ALGO'
        else:
            return 'Unknown'
    
    def analyze_extensions(self):
        """Analyze extension configuration"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 EXTENSION ANALYSIS{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Query extensions from database
        sql = """
        SELECT extension, name, tech, dial, devicetype, user
        FROM devices
        WHERE tech = 'sip' OR tech = 'pjsip'
        ORDER BY CAST(extension AS UNSIGNED)
        """
        
        rows = self.query_db(sql)
        if not rows:
            print(f"{Colors.YELLOW}⚠️  No extensions found{Colors.RESET}")
            return
        
        print(f"{Colors.CYAN}📊 Found {len(rows)} extensions{Colors.RESET}\n")
        
        # Analyze by device type
        by_type = defaultdict(int)
        for row in rows:
            if len(row) >= 5:
                devicetype = row[4] if row[4] else 'unknown'
                by_type[devicetype] += 1
        
        print(f"{Colors.CYAN}📱 By Device Type:{Colors.RESET}")
        for devtype, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"  {Colors.YELLOW}{devtype}:{Colors.RESET} {count}")
        
        return rows
    
    def check_provisioning_status(self):
        """Check phone provisioning configuration"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔧 PROVISIONING STATUS{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Check for endpoint manager
        sql = "SELECT COUNT(*) FROM endpointman_brand_list"
        result = self.query_db(sql)
        
        if result and result[0][0] != '0':
            print(f"{Colors.GREEN}✓ Endpoint Manager installed{Colors.RESET}")
            
            # Get brand statistics
            sql = """
            SELECT brand, COUNT(*) as count
            FROM endpointman_mac_list
            GROUP BY brand
            """
            brands = self.query_db(sql)
            
            if brands:
                print(f"\n{Colors.CYAN}📱 Provisioned Phones:{Colors.RESET}")
                for brand, count in brands:
                    print(f"  {Colors.YELLOW}{brand}:{Colors.RESET} {count}")
        else:
            print(f"{Colors.YELLOW}⚠️  Endpoint Manager not installed or not configured{Colors.RESET}")
    
    def analyze_pjsip_endpoints(self):
        """Analyze PJSIP endpoints (Asterisk 13+)"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📡 PJSIP ENDPOINT ANALYSIS{' ' * 49}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        output = self.get_asterisk_cli("pjsip show endpoints")
        if not output or "Unable" in output or "No such" in output:
            print(f"{Colors.YELLOW}⚠️  PJSIP not in use (using chan_sip){Colors.RESET}")
            return
        
        lines = output.strip().split('\n')
        endpoints = []
        
        for line in lines:
            if '/' in line:
                parts = line.split()
                if len(parts) >= 5:
                    endpoint = parts[0]
                    state = parts[1]
                    endpoints.append({'name': endpoint, 'state': state})
        
        if endpoints:
            online = sum(1 for e in endpoints if 'Avail' in e['state'])
            offline = len(endpoints) - online
            
            print(f"{Colors.CYAN}📊 PJSIP Endpoint Summary:{Colors.RESET}")
            print(f"  {Colors.GREEN}✓ Available:{Colors.RESET} {online}")
            print(f"  {Colors.RED}✗ Unavailable:{Colors.RESET} {offline}")
            print(f"  {Colors.CYAN}📱 Total:{Colors.RESET} {len(endpoints)}")
    
    def check_phone_firmware(self):
        """Analyze phone firmware versions"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔄 FIRMWARE VERSION ANALYSIS{' ' * 47}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Check endpoint manager firmware data
        sql = """
        SELECT m.brand, m.model, m.firmware_vers, COUNT(*) as count
        FROM endpointman_mac_list m
        GROUP BY m.brand, m.model, m.firmware_vers
        """
        
        results = self.query_db(sql)
        if not results:
            print(f"{Colors.YELLOW}⚠️  No firmware data available (Endpoint Manager required){Colors.RESET}")
            return
        
        print(f"{Colors.CYAN}📊 Firmware by Model:{Colors.RESET}\n")
        
        for brand, model, firmware, count in results:
            vendor_clean = brand.lower().replace(' ', '')
            
            # Check against 123NET standards
            is_current = False
            if vendor_clean in self.standard_firmware:
                for model_prefix, std_version in self.standard_firmware[vendor_clean].items():
                    if model_prefix in model.lower():
                        is_current = (firmware == std_version)
                        break
            
            status_icon = f"{Colors.GREEN}✓{Colors.RESET}" if is_current else f"{Colors.YELLOW}⚠{Colors.RESET}"
            print(f"  {status_icon} {Colors.YELLOW}{brand} {model}:{Colors.RESET} v{firmware} ({count} phones)")
    
    def analyze_call_quality(self):
        """Analyze call quality metrics"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📊 CALL QUALITY ANALYSIS{' ' * 51}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Get RTP statistics from Asterisk
        output = self.get_asterisk_cli("rtp show stats")
        
        if output:
            print(f"{Colors.CYAN}🔊 RTP Statistics:{Colors.RESET}")
            print(output[:500])  # Show first 500 chars
        else:
            print(f"{Colors.YELLOW}⚠️  No active RTP sessions{Colors.RESET}")
    
    def check_configuration_standards(self):
        """Check phones against 123NET configuration standards"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} ✅ 123NET CONFIGURATION STANDARDS CHECK{' ' * 36}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        checks = [
            ("NTP Server Configuration", "205.251.183.50"),
            ("Multicast Paging Address", "224.0.1.116"),
            ("Paging Port", "5001"),
            ("Default Admin Password", "08520852"),
            ("Default User Password", "2580"),
        ]
        
        print(f"{Colors.CYAN}📋 123NET Standard Settings:{Colors.RESET}\n")
        for check_name, expected_value in checks:
            print(f"  {Colors.GREEN}✓{Colors.RESET} {Colors.YELLOW}{check_name}:{Colors.RESET} {expected_value}")
        
        print(f"\n{Colors.CYAN}💡 Note:{Colors.RESET} Manual verification required on phones")
    
    def generate_phone_report(self):
        """Generate comprehensive phone analysis report"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📄 COMPREHENSIVE PHONE ANALYSIS REPORT{' ' * 37}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"{self.output_dir}/phone_analysis_{timestamp}.txt"
        
        print(f"{Colors.GREEN}📝 Generating report: {report_file}{Colors.RESET}\n")
        
        # Run all analyses
        self.analyze_sip_peers()
        self.analyze_pjsip_endpoints()
        self.analyze_extensions()
        self.check_provisioning_status()
        self.check_phone_firmware()
        self.check_configuration_standards()
        self.analyze_call_quality()
        
        print(f"\n{Colors.GREEN}✅ Phone analysis complete!{Colors.RESET}")
        print(f"{Colors.CYAN}💾 Report saved to: {report_file}{Colors.RESET}")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='FreePBX Phone/Endpoint Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--sip-peers', action='store_true', help='Analyze SIP peer registrations')
    parser.add_argument('--pjsip', action='store_true', help='Analyze PJSIP endpoints')
    parser.add_argument('--extensions', action='store_true', help='Analyze extensions')
    parser.add_argument('--provisioning', action='store_true', help='Check provisioning status')
    parser.add_argument('--firmware', action='store_true', help='Check firmware versions')
    parser.add_argument('--standards', action='store_true', help='Check 123NET standards')
    parser.add_argument('--call-quality', action='store_true', help='Analyze call quality')
    parser.add_argument('--comprehensive', action='store_true', help='Run all analyses')
    parser.add_argument('--output-dir', default='/home/123net/phone_analysis', help='Output directory')
    
    args = parser.parse_args()
    
    analyzer = PhoneAnalyzer(output_dir=args.output_dir)
    
    # If no specific flags, run comprehensive analysis
    if not any([args.sip_peers, args.pjsip, args.extensions, args.provisioning, 
                args.firmware, args.standards, args.call_quality, args.comprehensive]):
        args.comprehensive = True
    
    if args.comprehensive:
        analyzer.generate_phone_report()
    else:
        if args.sip_peers:
            analyzer.analyze_sip_peers()
        if args.pjsip:
            analyzer.analyze_pjsip_endpoints()
        if args.extensions:
            analyzer.analyze_extensions()
        if args.provisioning:
            analyzer.check_provisioning_status()
        if args.firmware:
            analyzer.check_phone_firmware()
        if args.standards:
            analyzer.check_configuration_standards()
        if args.call_quality:
            analyzer.analyze_call_quality()

if __name__ == '__main__':
    main()
