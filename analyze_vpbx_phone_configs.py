#!/usr/bin/env python3
"""
VPBX Phone Configuration Deep Analysis Tool

Analyzes scraped VPBX data to provide comprehensive insights into:
- Phone inventory across all sites
- Configuration patterns and anomalies
- Security issues (weak passwords, default configs)
- Version compliance
- Device health and issues
"""

import os
import re
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime

class VPBXPhoneAnalyzer:
    """Deep analyzer for VPBX phone configurations"""
    
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.results = {
            'sites': {},
            'phones': [],
            'inventory': Counter(),
            'security_issues': [],
            'config_patterns': defaultdict(Counter),
            'version_info': defaultdict(list),
            'anomalies': [],
            'statistics': {}
        }
        
    def analyze_all(self):
        """Run complete analysis"""
        print("=" * 80)
        print("VPBX Phone Configuration Deep Analysis")
        print("=" * 80)
        print()
        
        # Load main table
        self.load_main_table()
        
        # Analyze each site
        self.analyze_sites()
        
        # Generate reports
        self.generate_inventory_report()
        self.generate_security_report()
        self.generate_configuration_report()
        self.generate_version_report()
        self.generate_anomaly_report()
        
        # Save results
        self.save_results()
        
        return self.results
    
    def load_main_table(self):
        """Load the main VPBX table CSV"""
        csv_file = self.data_dir / "table_data.csv"
        
        if not csv_file.exists():
            print(f"Warning: {csv_file} not found")
            return
        
        print(f"Loading main table: {csv_file}")
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('ID'):
                    site_id = row['ID']
                    self.results['sites'][site_id] = {
                        'id': site_id,
                        'handle': row.get('Handle', ''),
                        'name': row.get('NAME', ''),
                        'ip': row.get('IP', ''),
                        'status': row.get('Status', ''),
                        'freepbx_version': row.get('FreePBX', ''),
                        'asterisk_version': row.get('Asterisk', ''),
                        'device_count': row.get('Devices', '0'),
                        'call_center': row.get('Call Center', ''),  # Asternic Call Center 2
                        'devices': []
                    }
                    
                    # Determine platform type
                    fpbx_ver = row.get('FreePBX', '').upper()
                    if 'FUSION' in fpbx_ver:
                        self.results['sites'][site_id]['platform'] = 'Fusion'
                    elif '123NET UC' in fpbx_ver or 'UC' in fpbx_ver:
                        self.results['sites'][site_id]['platform'] = '123NET UC'
                    else:
                        self.results['sites'][site_id]['platform'] = 'FreePBX'
        
        print(f"  Loaded {len(self.results['sites'])} sites")
        print()
    
    def analyze_sites(self):
        """Analyze all site directories"""
        print("Analyzing site configurations...")
        print()
        
        entry_dirs = sorted([d for d in self.data_dir.iterdir() if d.is_dir() and d.name.startswith('entry_')])
        
        total = len(entry_dirs)
        for idx, entry_dir in enumerate(entry_dirs, 1):
            site_id = entry_dir.name.replace('entry_', '')
            
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{total} sites analyzed...")
            
            # Analyze each page type
            self.analyze_site_config(site_id, entry_dir)
            self.analyze_phone_configs(site_id, entry_dir)
            self.analyze_view_configs(site_id, entry_dir)
        
        print(f"  Completed: {total} sites analyzed")
        print()
    
    def analyze_site_config(self, site_id, entry_dir):
        """Analyze site_specific_config.txt for device inventory"""
        config_file = entry_dir / "site_specific_config.txt"
        
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract device table data
            devices = self.extract_devices_from_table(content)
            
            if site_id in self.results['sites']:
                self.results['sites'][site_id]['devices'] = devices
            
            for device in devices:
                device['site_id'] = site_id
                device['site_handle'] = self.results['sites'].get(site_id, {}).get('handle', '')
                device['site_name'] = self.results['sites'].get(site_id, {}).get('name', '')
                self.results['phones'].append(device)
                
                # Count by make/model
                make_model = f"{device['make']}_{device['model']}"
                self.results['inventory'][make_model] += 1
                self.results['inventory'][f"make_{device['make']}"] += 1
            
            # Extract site-wide XML config
            site_config = self.extract_site_xml_config(content)
            if site_config and site_id in self.results['sites']:
                self.results['sites'][site_id]['site_config'] = site_config
                
                # Check for security issues
                self.check_site_security(site_id, site_config)
            
        except Exception as e:
            print(f"    Error analyzing site config for {site_id}: {e}")
    
    def extract_devices_from_table(self, content):
        """Extract device information from table format"""
        devices = []
        
        # Look for device table patterns
        # Format: Device_ID | Directory_Name | Extension | MAC | Make | Model
        lines = content.split('\n')
        
        in_device_table = False
        for i, line in enumerate(lines):
            # Detect table start
            if 'Device ID' in line and 'MAC' in line and 'Make' in line:
                in_device_table = True
                continue
            
            if in_device_table:
                # Stop at "Showing X to Y" or "Previous/Next"
                if 'Showing' in line or 'Previous' in line or 'Next' in line:
                    break
                
                # Parse device rows
                # Pattern: number | name | extension | site_code | ... | MAC | make | model | Edit
                parts = [p.strip() for p in line.split('|')]
                
                if len(parts) >= 8 and parts[0].isdigit():
                    try:
                        device = {
                            'device_id': parts[0],
                            'directory_name': parts[1],
                            'extension': self.extract_extension(parts[1]),
                            'cid': parts[2] if len(parts) > 2 else '',
                            'mac': self.clean_mac_address(parts[-4]) if len(parts) > 4 else '',
                            'make': parts[-3].lower() if len(parts) > 3 else '',
                            'model': parts[-2] if len(parts) > 2 else ''
                        }
                        
                        if device['mac']:  # Only add if we have a MAC
                            devices.append(device)
                    except Exception as e:
                        pass  # Skip malformed rows
        
        return devices
    
    def extract_extension(self, directory_name):
        """Extract extension from directory name like 'Conf Room <142>'"""
        match = re.search(r'<(\d+)>', directory_name)
        return match.group(1) if match else ''
    
    def clean_mac_address(self, mac):
        """Clean and normalize MAC address"""
        # Remove whitespace and convert to lowercase
        mac = mac.strip().lower()
        # Keep only hex digits and colons/dashes
        mac = re.sub(r'[^0-9a-f:]', '', mac)
        return mac if len(mac) >= 12 else ''
    
    def extract_site_xml_config(self, content):
        """Extract site-wide XML configuration"""
        config = {}
        
        # Extract SIP server
        match = re.search(r'voIpProt\.server\.1\.address\s*=\s*"([^"]+)"', content)
        if match:
            config['sip_server'] = match.group(1)
        
        # Extract admin passwords
        match = re.search(r'device\.auth\.localAdminPassword\s*=\s*"([^"]+)"', content)
        if match:
            config['admin_password'] = match.group(1)
        
        match = re.search(r'device\.auth\.localUserPassword\s*=\s*"([^"]+)"', content)
        if match:
            config['user_password'] = match.group(1)
        
        return config if config else None
    
    def check_site_security(self, site_id, config):
        """Check for security issues in site configuration"""
        issues = []
        
        # Check for weak/default admin passwords
        if 'admin_password' in config:
            pwd = config['admin_password']
            if len(pwd) < 8:
                issues.append({
                    'site_id': site_id,
                    'type': 'weak_admin_password',
                    'severity': 'high',
                    'detail': f"Admin password too short: {len(pwd)} characters"
                })
            
            # Check for common patterns
            if pwd.isdigit() or pwd.lower() in ['password', 'admin', '12345678']:
                issues.append({
                    'site_id': site_id,
                    'type': 'default_admin_password',
                    'severity': 'critical',
                    'detail': f"Potentially default or weak admin password"
                })
        
        self.results['security_issues'].extend(issues)
    
    def analyze_phone_configs(self, site_id, entry_dir):
        """Analyze individual phone configurations"""
        edit_file = entry_dir / "edit_main.txt"
        
        if not edit_file.exists():
            return
        
        try:
            with open(edit_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract template assignments
            template_matches = re.finditer(r'Template\s*\n([^\n]+)', content)
            for match in template_matches:
                template = match.group(1).strip()
                if template and not template.startswith('Single Line'):
                    self.results['config_patterns']['templates'][template] += 1
            
        except Exception as e:
            pass
    
    def analyze_view_configs(self, site_id, entry_dir):
        """Analyze view_config.txt for detailed phone settings"""
        config_file = entry_dir / "view_config.txt"
        
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract SIP credentials
            sip_config = {}
            
            patterns = {
                'userid': r'reg\.1\.auth\.userid\s*=\s*"([^"]+)"',
                'password': r'reg\.1\.auth\.password\s*=\s*"([^"]+)"',
                'address': r'reg\.1\.address\s*=\s*"([^"]+)"',
                'displayname': r'reg\.1\.displayname\s*=\s*"([^"]+)"',
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                if match:
                    sip_config[key] = match.group(1)
            
            if sip_config:
                # Track password patterns
                if 'password' in sip_config:
                    pwd = sip_config['password']
                    pwd_len = len(pwd)
                    self.results['config_patterns']['password_lengths'][pwd_len] += 1
                    
                    # Check if MD5 hash (32 hex chars)
                    if len(pwd) == 32 and all(c in '0123456789abcdef' for c in pwd.lower()):
                        self.results['config_patterns']['password_types']['md5_hash'] += 1
                    else:
                        self.results['config_patterns']['password_types']['plaintext'] += 1
            
            # Extract transfer type settings
            match = re.search(r'call\.defaulttransfertype\s*=\s*"([^"]+)"', content)
            if match:
                transfer_type = match.group(1)
                self.results['config_patterns']['transfer_types'][transfer_type] += 1
            
            # Check for log files
            if 'app.log' in content:
                log_match = re.search(r'(/home/[^\s]+\.log)', content)
                if log_match and site_id in self.results['sites']:
                    if 'log_path' not in self.results['sites'][site_id]:
                        self.results['sites'][site_id]['log_path'] = log_match.group(1)
            
        except Exception as e:
            pass
    
    def generate_inventory_report(self):
        """Generate phone inventory statistics"""
        print("=" * 80)
        print("PHONE INVENTORY REPORT")
        print("=" * 80)
        print()
        
        total_phones = len(self.results['phones'])
        print(f"Total Phones: {total_phones}")
        print()
        
        # By manufacturer
        print("By Manufacturer:")
        manufacturers = [(k.replace('make_', ''), v) for k, v in self.results['inventory'].items() 
                        if k.startswith('make_')]
        manufacturers.sort(key=lambda x: x[1], reverse=True)
        
        for make, count in manufacturers:
            percentage = (count / total_phones * 100) if total_phones > 0 else 0
            print(f"  {make.capitalize():20} {count:5} ({percentage:5.1f}%)")
        print()
        
        # By model (top 20)
        print("Top 20 Models:")
        models = [(k.replace('_', ' '), v) for k, v in self.results['inventory'].items() 
                 if not k.startswith('make_')]
        models.sort(key=lambda x: x[1], reverse=True)
        
        for model, count in models[:20]:
            percentage = (count / total_phones * 100) if total_phones > 0 else 0
            print(f"  {model:30} {count:5} ({percentage:5.1f}%)")
        print()
        
        self.results['statistics']['total_phones'] = total_phones
        self.results['statistics']['manufacturers'] = dict(manufacturers)
        self.results['statistics']['top_models'] = dict(models[:20])
    
    def generate_security_report(self):
        """Generate security analysis report"""
        print("=" * 80)
        print("SECURITY ANALYSIS")
        print("=" * 80)
        print()
        
        if not self.results['security_issues']:
            print("✓ No major security issues detected")
            print()
            return
        
        # Group by severity
        by_severity = defaultdict(list)
        for issue in self.results['security_issues']:
            by_severity[issue['severity']].append(issue)
        
        for severity in ['critical', 'high', 'medium', 'low']:
            issues = by_severity.get(severity, [])
            if issues:
                print(f"{severity.upper()} Severity: {len(issues)} issues")
                for issue in issues[:10]:  # Show first 10
                    print(f"  Site {issue['site_id']}: {issue['detail']}")
                if len(issues) > 10:
                    print(f"  ... and {len(issues) - 10} more")
                print()
    
    def generate_configuration_report(self):
        """Generate configuration patterns report"""
        print("=" * 80)
        print("CONFIGURATION PATTERNS")
        print("=" * 80)
        print()
        
        # Transfer types
        if self.results['config_patterns']['transfer_types']:
            print("Transfer Type Distribution:")
            for transfer_type, count in self.results['config_patterns']['transfer_types'].most_common():
                print(f"  {transfer_type:20} {count:5}")
            print()
        
        # Password analysis
        if self.results['config_patterns']['password_types']:
            print("Password Storage Types:")
            for pwd_type, count in self.results['config_patterns']['password_types'].most_common():
                print(f"  {pwd_type:20} {count:5}")
            print()
        
        if self.results['config_patterns']['password_lengths']:
            print("Password Length Distribution:")
            lengths = sorted(self.results['config_patterns']['password_lengths'].items())
            for length, count in lengths:
                print(f"  {length:2} characters: {count:5}")
            print()
        
        # Template usage
        if self.results['config_patterns']['templates']:
            print("Top 10 Phone Templates:")
            for template, count in self.results['config_patterns']['templates'].most_common(10):
                print(f"  {template:40} {count:5}")
            print()
    
    def generate_version_report(self):
        """Generate FreePBX/Asterisk version report"""
        print("=" * 80)
        print("VERSION ANALYSIS")
        print("=" * 80)
        print()
        
        # Collect version info
        freepbx_versions = Counter()
        asterisk_versions = Counter()
        platforms = Counter()
        call_center_sites = []
        
        for site_id, site in self.results['sites'].items():
            if site.get('freepbx_version'):
                freepbx_versions[site['freepbx_version']] += 1
            if site.get('asterisk_version'):
                asterisk_versions[site['asterisk_version']] += 1
            if site.get('platform'):
                platforms[site['platform']] += 1
            if site.get('call_center'):
                call_center_sites.append(site_id)
        
        print("Platform Distribution:")
        for platform, count in sorted(platforms.items(), key=lambda x: x[1], reverse=True):
            print(f"  {platform:20} {count:5} sites")
        print()
        
        print("FreePBX Versions:")
        for version, count in sorted(freepbx_versions.items(), reverse=True):
            print(f"  {version:20} {count:5} sites")
        print()
        
        print("Asterisk Versions:")
        for version, count in sorted(asterisk_versions.items(), reverse=True):
            print(f"  {version:20} {count:5} sites")
        print()
        
        print(f"Call Center (Asternic Call Center 2):")
        print(f"  Installed: {len(call_center_sites)} sites")
        print(f"  Not installed: {len(self.results['sites']) - len(call_center_sites)} sites")
        print()
        
        self.results['statistics']['freepbx_versions'] = dict(freepbx_versions)
        self.results['statistics']['asterisk_versions'] = dict(asterisk_versions)
        self.results['statistics']['platforms'] = dict(platforms)
        self.results['statistics']['call_center_count'] = len(call_center_sites)
    
    def generate_anomaly_report(self):
        """Detect and report anomalies"""
        print("=" * 80)
        print("ANOMALY DETECTION")
        print("=" * 80)
        print()
        
        anomalies = []
        
        # Find sites with unusual device counts
        device_counts = [int(site.get('device_count', 0)) for site in self.results['sites'].values()]
        if device_counts:
            avg_devices = sum(device_counts) / len(device_counts)
            
            for site_id, site in self.results['sites'].items():
                count = int(site.get('device_count', 0))
                if count > avg_devices * 3:
                    anomalies.append({
                        'type': 'high_device_count',
                        'site_id': site_id,
                        'handle': site.get('handle'),
                        'detail': f"{count} devices (avg: {avg_devices:.1f})"
                    })
                elif count > 0 and count < 3:
                    anomalies.append({
                        'type': 'low_device_count',
                        'site_id': site_id,
                        'handle': site.get('handle'),
                        'detail': f"{count} devices"
                    })
        
        # Find sites with mismatched device counts
        for site_id, site in self.results['sites'].items():
            reported_count = int(site.get('device_count', 0))
            actual_count = len(site.get('devices', []))
            
            if reported_count > 0 and actual_count > 0 and abs(reported_count - actual_count) > 2:
                anomalies.append({
                    'type': 'device_count_mismatch',
                    'site_id': site_id,
                    'handle': site.get('handle'),
                    'detail': f"Reported: {reported_count}, Found: {actual_count}"
                })
        
        if anomalies:
            for anomaly in anomalies[:20]:  # Show first 20
                print(f"  [{anomaly['type']}] Site {anomaly['site_id']} ({anomaly.get('handle', 'N/A')}): {anomaly['detail']}")
            if len(anomalies) > 20:
                print(f"  ... and {len(anomalies) - 20} more anomalies")
        else:
            print("✓ No significant anomalies detected")
        
        print()
        self.results['anomalies'] = anomalies
    
    def save_results(self):
        """Save analysis results to JSON"""
        output_file = self.data_dir / "analysis_results.json"
        
        # Convert Counters to dicts for JSON serialization
        serializable_results = {
            'sites': self.results['sites'],
            'phones': self.results['phones'],
            'inventory': dict(self.results['inventory']),
            'security_issues': self.results['security_issues'],
            'config_patterns': {
                k: dict(v) for k, v in self.results['config_patterns'].items()
            },
            'anomalies': self.results['anomalies'],
            'statistics': self.results['statistics'],
            'generated_at': datetime.now().isoformat()
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2)
        
        print(f"Results saved to: {output_file}")
        print()
        
        # Also save phone inventory as CSV
        self.save_phone_inventory_csv()
    
    def save_phone_inventory_csv(self):
        """Save complete phone inventory as CSV"""
        output_file = self.data_dir / "phone_inventory_complete.csv"
        
        if not self.results['phones']:
            return
        
        fieldnames = ['site_id', 'site_handle', 'site_name', 'device_id', 
                     'directory_name', 'extension', 'mac', 'make', 'model', 'cid']
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for phone in self.results['phones']:
                writer.writerow({k: phone.get(k, '') for k in fieldnames})
        
        print(f"Phone inventory CSV saved to: {output_file}")
        print()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Deep analysis of VPBX phone configurations'
    )
    
    parser.add_argument(
        '--data-dir',
        default='freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive',
        help='Directory containing scraped VPBX data'
    )
    
    args = parser.parse_args()
    
    analyzer = VPBXPhoneAnalyzer(args.data_dir)
    results = analyzer.analyze_all()
    
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print()
    print(f"Results saved to: {analyzer.data_dir}/analysis_results.json")
    print(f"Phone inventory: {analyzer.data_dir}/phone_inventory_complete.csv")
    print()

if __name__ == '__main__':
    main()
