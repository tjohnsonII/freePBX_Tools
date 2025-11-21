#!/usr/bin/env python3

"""
Ultimate VPBX Data Analyzer - Deep Intelligence Extraction
Extracts every possible piece of actionable data from comprehensive scrape

VARIABLE MAP LEGEND
-------------------
UltimateVPBXAnalyzer attributes:
    data_dir         : Path, root directory containing all site data folders
    sites            : list of dict, analyzed site summaries
    all_credentials  : list, all credentials found across sites
    all_devices      : list, all device records found
    all_sip_accounts : list, all SIP account records
    all_site_notes   : list, all notes/comments found
    all_configs      : list, all parsed config files
    security_issues  : list, all security issues found
    version_data     : list, version info for all sites

Key method variables:
    entry_dirs       : list of Path, directories for each site (entry_*)
    site_id          : str, unique identifier for a site
    entry_dir        : Path, directory for a single site's data
    site             : dict, all extracted data for a site
    detail_main      : Path, main HTML file for a site
    row, record      : dict, single data record in loops
    results          : list, results from a function or query
    args             : argparse.Namespace, parsed CLI arguments
    f                : file handle (for reading/writing)
"""

import re
import json
import csv
from pathlib import Path
from collections import defaultdict, Counter
from html import unescape
import argparse


class UltimateVPBXAnalyzer:
    """Comprehensive analysis of all scraped VPBX data"""
    
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.sites = []
        self.all_credentials = []
        self.all_devices = []
        self.all_sip_accounts = []
        self.all_site_notes = []
        self.all_configs = []
        self.security_issues = []
        self.version_data = []
        
    def analyze_all_sites(self):
        """Main analysis orchestrator"""
        print(f"🔍 Analyzing VPBX data in: {self.data_dir}")
        
        # Find all entry directories
        entry_dirs = sorted([d for d in self.data_dir.iterdir() if d.is_dir() and d.name.startswith('entry_')])
        print(f"📊 Found {len(entry_dirs)} sites to analyze\n")
        
        for i, entry_dir in enumerate(entry_dirs, 1):
            if i % 50 == 0:
                print(f"   Processing site {i}/{len(entry_dirs)}...")
            
            site_id = entry_dir.name.replace('entry_', '')
            site_data = self.analyze_site(entry_dir, site_id)
            if site_data:
                self.sites.append(site_data)
        
        print(f"\n✅ Analyzed {len(self.sites)} sites successfully")
        return self.sites
    
    def analyze_site(self, entry_dir, site_id):
        """Deep analysis of single site"""
        detail_main = entry_dir / "detail_main.html"
        if not detail_main.exists():
            return None
        
        site = {'site_id': site_id}
        
        # Extract all data types
        site.update(self.extract_server_credentials(detail_main))
        site.update(self.extract_version_info(detail_main))
        site.update(self.extract_contact_info(detail_main))
        
        # Parse all sub-pages
        site['notes'] = self.extract_site_notes(entry_dir / "site_notes.html")
        site['devices'] = self.extract_devices_enhanced(entry_dir / "site_specific_config.html", site_id)
        site['sip_configs'] = self.extract_sip_configs(entry_dir / "view_config.html")
        site['xml_configs'] = self.extract_xml_configs(entry_dir / "bulk_attribute_edit.html")
        
        # Platform and feature detection
        site['platform'] = self.detect_platform(site)
        site['features'] = self.detect_features(site)
        
        # Security analysis
        site['security'] = self.audit_site_security(site)
        
        # Aggregate data
        if site.get('system_ip'):
            self.all_credentials.append(self.format_credentials(site))
        if site['devices']:
            self.all_devices.extend(site['devices'])
        if site['sip_configs']:
            self.all_sip_accounts.extend(site['sip_configs'])
        if site['notes']:
            self.all_site_notes.append({'site_id': site_id, 'notes': site['notes']})
        if site['security']:
            for issue in site['security']:
                issue['site_id'] = site_id
                self.security_issues.append(issue)
        
        self.version_data.append({
            'site_id': site_id,
            'freepbx_version': site.get('freepbx_version', ''),
            'asterisk_version': site.get('asterisk_version', ''),
            'platform': site.get('platform', ''),
            'system_ip': site.get('system_ip', '')
        })
        
        return site
    
    def extract_server_credentials(self, html_file):
        """Extract ALL server credentials"""
        if not html_file.exists():
            return {}
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        creds = {}
        
        # Server identification
        patterns = {
            'handle': r'name="handle"\s+value="([^"]*)"',
            'company': r'name="company"\s+value="([^"]*)"',
            'system_ip': r'name="ip"\s+value="([^"]*)"',
            'deployment_id': r'name="deployment_id"\s+value="([^"]*)"',
            'vm_id': r'name="vm_id"\s+value="([^"]*)"',
            
            # FTP/SFTP credentials
            'ftp_host': r'name="ftp_host"\s+value="([^"]*)"',
            'ftp_user': r'name="ftp_user"\s+value="([^"]*)"',
            'ftp_pass': r'name="ftp_pass"\s+value="([^"]*)"',
            
            # REST API credentials
            'rest_user': r'name="rest_user"\s+value="([^"]*)"',
            'rest_pass': r'name="rest_pass"\s+value="([^"]*)"',
            
            # System info
            'freepbx_version': r'name="freepbx_version"\s+value="([^"]*)"',
            'asterisk_version': r'name="asterisk_version"\s+value="([^"]*)"',
            
            # Features
            'call_center': r'name="call_center"\s+value="([^"]*)"',
            'status': r'name="status"\s+value="([^"]*)"',
            'polycom_uc': r'name="polycom_uc"\s+value="([^"]*)"',
            
            # Contact/billing
            'acct_rep': r'name="acct_rep"\s+value="([^"]*)"',
            'monthly_cost': r'name="monthly_cost"\s+value="([^"]*)"',
            'setup_cost': r'name="setup_cost"\s+value="([^"]*)"',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, html)
            if match:
                value = unescape(match.group(1)).strip()
                if value:
                    creds[key] = value
        
        # Build admin URLs
        if creds.get('system_ip') and creds.get('ftp_pass'):
            creds['admin_url'] = f"http://{creds['system_ip']}/admin/config.php?username=i123net&password={creds['ftp_pass']}"
            creds['ssh_command'] = f"ssh 123net@{creds['system_ip']}"
        
        return creds
    
    def extract_version_info(self, html_file):
        """Extract version details"""
        if not html_file.exists():
            return {}
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        versions = {}
        
        # Parse version strings
        if freepbx := re.search(r'name="freepbx_version"\s+value="([^"]*)"', html):
            versions['freepbx_version'] = freepbx.group(1)
            versions['freepbx_major'] = freepbx.group(1).split('.')[0] if '.' in freepbx.group(1) else ''
        
        if asterisk := re.search(r'name="asterisk_version"\s+value="([^"]*)"', html):
            versions['asterisk_version'] = asterisk.group(1)
            versions['asterisk_major'] = asterisk.group(1).split('.')[0] if '.' in asterisk.group(1) else ''
        
        return versions
    
    def extract_contact_info(self, html_file):
        """Extract contact and billing info"""
        if not html_file.exists():
            return {}
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        contact = {}
        
        patterns = {
            'phone': r'name="phone"\s+value="([^"]*)"',
            'email': r'name="email"\s+value="([^"]*)"',
            'address': r'name="address"\s+value="([^"]*)"',
            'city': r'name="city"\s+value="([^"]*)"',
            'state': r'name="state"\s+value="([^"]*)"',
            'zip': r'name="zip"\s+value="([^"]*)"',
        }
        
        for key, pattern in patterns.items():
            if match := re.search(pattern, html):
                value = unescape(match.group(1)).strip()
                if value:
                    contact[key] = value
        
        return contact
    
    def extract_site_notes(self, html_file):
        """Extract site notes content"""
        if not html_file.exists():
            return ""
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        
        # Try to find textarea content
        if match := re.search(r'<textarea[^>]*name="notes"[^>]*>(.*?)</textarea>', html, re.DOTALL):
            notes = unescape(match.group(1)).strip()
            return notes
        
        # Try to find in div/pre tags
        if match := re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL):
            notes = unescape(match.group(1)).strip()
            return notes
        
        return ""
    
    def extract_devices_enhanced(self, html_file, site_id):
        """Enhanced device extraction with table parsing"""
        if not html_file.exists():
            return []
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        devices = []
        
        # Find device table rows - multiple patterns
        patterns = [
            # Pattern 1: Standard table rows
            r'<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>',
            # Pattern 2: Input fields in table
            r'<input[^>]*name="mac\[\]"[^>]*value="([^"]+)"',
        ]
        
        # Try MAC address extraction first (most reliable)
        mac_matches = re.findall(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', html)
        
        if mac_matches:
            # Found MAC addresses - try to get associated data
            for mac in mac_matches:
                device = {'site_id': site_id, 'mac': mac.upper()}
                
                # Try to find model/extension near this MAC
                mac_area = re.search(rf'{re.escape(mac)}.*?(?:<tr|<input|$)', html, re.IGNORECASE | re.DOTALL)
                if mac_area:
                    area_text = mac_area.group(0)
                    
                    # Look for extension numbers
                    if ext_match := re.search(r'\b(\d{3,5})\b', area_text):
                        device['extension'] = ext_match.group(1)
                    
                    # Look for model names
                    models = ['VVX', 'SoundPoint', 'OBi', 'SPA', 'Yealink', 'Grandstream', 'Cisco', 'Polycom']
                    for model in models:
                        if model.lower() in area_text.lower():
                            device['model'] = model
                            break
                
                devices.append(device)
        
        # Alternative: Parse table structure
        if not devices:
            # Look for device tables with headers
            table_match = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
            if table_match:
                table_html = table_match.group(1)
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
                
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    if len(cells) >= 3:
                        # Try to identify columns
                        device = {'site_id': site_id}
                        
                        for cell in cells:
                            cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                            
                            # MAC address
                            if re.match(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', cell_text):
                                device['mac'] = cell_text.upper()
                            # Extension
                            elif re.match(r'^\d{3,5}$', cell_text):
                                device['extension'] = cell_text
                            # Model
                            elif any(model.lower() in cell_text.lower() for model in ['vvx', 'soundpoint', 'obi', 'spa', 'yealink']):
                                device['model'] = cell_text
                        
                        if device.get('mac') or device.get('extension'):
                            devices.append(device)
        
        return devices
    
    def extract_sip_configs(self, html_file):
        """Extract SIP registration configurations"""
        if not html_file.exists():
            return []
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        sip_accounts = []
        
        # Polycom SIP registration patterns
        patterns = [
            (r'reg\.(\d+)\.address\s*=\s*"?([^"\s<]+)"?', 'server'),
            (r'reg\.(\d+)\.auth\.userId\s*=\s*"?([^"\s<]+)"?', 'userid'),
            (r'reg\.(\d+)\.auth\.password\s*=\s*"?([^"\s<]+)"?', 'password'),
            (r'reg\.(\d+)\.displayName\s*=\s*"?([^"<]+)"?', 'displayname'),
            (r'reg\.(\d+)\.label\s*=\s*"?([^"<]+)"?', 'label'),
        ]
        
        # Collect all registration data
        reg_data = defaultdict(dict)
        
        for pattern, field in patterns:
            matches = re.findall(pattern, html)
            for reg_num, value in matches:
                reg_data[reg_num][field] = unescape(value).strip()
        
        # Convert to list
        for reg_num, data in reg_data.items():
            if data.get('userid') or data.get('password'):
                account = {
                    'registration': reg_num,
                    'server': data.get('server', ''),
                    'userid': data.get('userid', ''),
                    'password': data.get('password', ''),
                    'displayname': data.get('displayname', ''),
                    'label': data.get('label', '')
                }
                sip_accounts.append(account)
        
        return sip_accounts
    
    def extract_xml_configs(self, html_file):
        """Extract XML configuration parameters"""
        if not html_file.exists():
            return {}
        
        html = html_file.read_text(encoding='utf-8', errors='ignore')
        configs = {}
        
        # Common Polycom XML parameters
        patterns = {
            'admin_password': r'device\.auth\.localAdminPassword\s*=\s*"?([^"\s<]+)"?',
            'provision_server': r'apps\.push\.serverRootURL\s*=\s*"?([^"\s<]+)"?',
            'syslog_server': r'device\.syslog\.serverName\s*=\s*"?([^"\s<]+)"?',
            'ntp_server': r'tcpIpApp\.sntp\.address\s*=\s*"?([^"\s<]+)"?',
            'vlan_id': r'device\.net\.vlanId\s*=\s*"?([^"\s<]+)"?',
            'qos_audio': r'device\.qos\.ip\.rtp\.port\.audio\s*=\s*"?([^"\s<]+)"?',
        }
        
        for key, pattern in patterns.items():
            if match := re.search(pattern, html):
                configs[key] = unescape(match.group(1)).strip()
        
        return configs
    
    def detect_platform(self, site):
        """Detect FreePBX/Fusion/123NET UC platform"""
        vm_id = site.get('vm_id', '').upper()
        freepbx_ver = site.get('freepbx_version', '')
        
        if 'FUSION' in vm_id:
            return 'Fusion'
        elif '123NET UC' in vm_id or 'UCAAS' in vm_id:
            return '123NET UC'
        elif freepbx_ver:
            return 'FreePBX'
        else:
            return 'Unknown'
    
    def detect_features(self, site):
        """Detect enabled features"""
        features = []
        
        if site.get('call_center', '').lower() == 'yes':
            features.append('Asternic Call Center 2')
        
        if site.get('polycom_uc', '').lower() == 'yes':
            features.append('Polycom UC Software')
        
        if site.get('sip_configs'):
            features.append('SIP Trunking')
        
        if site.get('devices'):
            features.append(f"{len(site['devices'])} Devices")
        
        return features
    
    def audit_site_security(self, site):
        """Comprehensive security audit"""
        issues = []
        
        # FTP password strength
        ftp_pass = site.get('ftp_pass', '')
        if ftp_pass:
            if len(ftp_pass) < 12:
                issues.append({
                    'severity': 'high',
                    'type': 'weak_ftp_password',
                    'detail': f'FTP password only {len(ftp_pass)} characters'
                })
            if ftp_pass.isdigit():
                issues.append({
                    'severity': 'high',
                    'type': 'numeric_ftp_password',
                    'detail': 'FTP password is numeric only'
                })
            if not re.search(r'[A-Z]', ftp_pass) or not re.search(r'[a-z]', ftp_pass):
                issues.append({
                    'severity': 'medium',
                    'type': 'weak_ftp_complexity',
                    'detail': 'FTP password lacks uppercase/lowercase mix'
                })
        
        # REST password format check
        rest_pass = site.get('rest_pass', '')
        if rest_pass and len(rest_pass) != 32:
            issues.append({
                'severity': 'medium',
                'type': 'non_md5_rest_password',
                'detail': f'REST password is {len(rest_pass)} chars (should be 32-char MD5)'
            })
        
        # Asterisk version EOL check
        asterisk_ver = site.get('asterisk_version', '')
        if asterisk_ver:
            major = asterisk_ver.split('.')[0] if '.' in asterisk_ver else ''
            eol_versions = ['1', '10', '11', '12', '13', '14', '15']
            if major in eol_versions:
                issues.append({
                    'severity': 'high',
                    'type': 'eol_asterisk',
                    'detail': f'Asterisk {major}.x is EOL (current: {asterisk_ver})'
                })
        
        # FreePBX version EOL check
        freepbx_ver = site.get('freepbx_version', '')
        if freepbx_ver:
            major = freepbx_ver.split('.')[0] if '.' in freepbx_ver else ''
            eol_versions = ['2', '12', '13']
            if major in eol_versions:
                issues.append({
                    'severity': 'high',
                    'type': 'eol_freepbx',
                    'detail': f'FreePBX {major}.x is EOL (current: {freepbx_ver})'
                })
        
        # Device admin password check
        for device_cfg in site.get('xml_configs', {}).items():
            if device_cfg[0] == 'admin_password':
                pwd = device_cfg[1]
                if len(pwd) < 8:
                    issues.append({
                        'severity': 'critical',
                        'type': 'weak_device_password',
                        'detail': f'Device admin password only {len(pwd)} characters'
                    })
                if pwd.isdigit():
                    issues.append({
                        'severity': 'critical',
                        'type': 'numeric_device_password',
                        'detail': 'Device admin password is numeric only'
                    })
        
        # SIP password check
        for sip in site.get('sip_configs', []):
            if pwd := sip.get('password'):
                if len(pwd) < 12:
                    issues.append({
                        'severity': 'medium',
                        'type': 'weak_sip_password',
                        'detail': f'SIP password for {sip.get("userid", "unknown")} only {len(pwd)} characters'
                    })
        
        return issues
    
    def format_credentials(self, site):
        """Format credentials for export"""
        return {
            'site_id': site.get('site_id', ''),
            'handle': site.get('handle', ''),
            'company': site.get('company', ''),
            'system_ip': site.get('system_ip', ''),
            'ftp_host': site.get('ftp_host', ''),
            'ftp_user': site.get('ftp_user', ''),
            'ftp_password': site.get('ftp_pass', ''),
            'rest_user': site.get('rest_user', ''),
            'rest_password': site.get('rest_pass', ''),
            'ssh_command': site.get('ssh_command', ''),
            'admin_url': site.get('admin_url', ''),
        }
    
    def generate_reports(self, output_dir):
        """Generate comprehensive reports"""
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        print(f"\n📝 Generating comprehensive reports...")
        
        # 1. Full credentials export
        self.export_credentials(output_dir / "ALL_CREDENTIALS_SENSITIVE.csv")
        
        # 2. Server inventory with full details
        self.export_server_inventory(output_dir / "server_inventory_complete.csv")
        
        # 3. Device inventory
        self.export_device_inventory(output_dir / "device_inventory_all.csv")
        
        # 4. SIP accounts
        self.export_sip_accounts(output_dir / "sip_accounts_all.csv")
        
        # 5. Site notes knowledge base
        self.export_site_notes(output_dir / "site_notes_knowledge_base.txt")
        
        # 6. Security audit comprehensive
        self.export_security_audit(output_dir / "security_audit_comprehensive.csv")
        
        # 7. Version analysis
        self.export_version_analysis(output_dir / "version_analysis.csv")
        
        # 8. Platform distribution
        self.export_platform_stats(output_dir / "platform_statistics.txt")
        
        # 9. Executive summary
        self.export_executive_summary(output_dir / "EXECUTIVE_SUMMARY.txt")
        
        # 10. Full JSON dump
        self.export_json_dump(output_dir / "complete_analysis.json")
        
        print(f"✅ All reports generated in: {output_dir}")
    
    def export_credentials(self, filename):
        """Export all server credentials"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            if not self.all_credentials:
                return
            
            writer = csv.DictWriter(f, fieldnames=self.all_credentials[0].keys())
            writer.writeheader()
            writer.writerows(self.all_credentials)
        
        print(f"   ✓ Credentials: {len(self.all_credentials)} servers → {filename.name}")
    
    def export_server_inventory(self, filename):
        """Export server inventory"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['site_id', 'handle', 'company', 'platform', 'status', 'system_ip',
                         'freepbx_version', 'asterisk_version', 'vm_id', 'call_center',
                         'device_count', 'features', 'acct_rep', 'monthly_cost']
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for site in self.sites:
                writer.writerow({
                    'site_id': site.get('site_id', ''),
                    'handle': site.get('handle', ''),
                    'company': site.get('company', ''),
                    'platform': site.get('platform', ''),
                    'status': site.get('status', ''),
                    'system_ip': site.get('system_ip', ''),
                    'freepbx_version': site.get('freepbx_version', ''),
                    'asterisk_version': site.get('asterisk_version', ''),
                    'vm_id': site.get('vm_id', ''),
                    'call_center': site.get('call_center', ''),
                    'device_count': len(site.get('devices', [])),
                    'features': ', '.join(site.get('features', [])),
                    'acct_rep': site.get('acct_rep', ''),
                    'monthly_cost': site.get('monthly_cost', ''),
                })
        
        print(f"   ✓ Inventory: {len(self.sites)} servers → {filename.name}")
    
    def export_device_inventory(self, filename):
        """Export all devices"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['site_id', 'mac', 'extension', 'model']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for device in self.all_devices:
                writer.writerow({
                    'site_id': device.get('site_id', ''),
                    'mac': device.get('mac', ''),
                    'extension': device.get('extension', ''),
                    'model': device.get('model', ''),
                })
        
        print(f"   ✓ Devices: {len(self.all_devices)} phones → {filename.name}")
    
    def export_sip_accounts(self, filename):
        """Export SIP accounts"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            if not self.all_sip_accounts:
                return
            
            writer = csv.DictWriter(f, fieldnames=self.all_sip_accounts[0].keys())
            writer.writeheader()
            writer.writerows(self.all_sip_accounts)
        
        print(f"   ✓ SIP Accounts: {len(self.all_sip_accounts)} registrations → {filename.name}")
    
    def export_site_notes(self, filename):
        """Export all site notes"""
        with open(filename, 'w', encoding='utf-8') as f:
            for note_data in self.all_site_notes:
                f.write(f"\n{'='*80}\n")
                f.write(f"SITE: {note_data['site_id']}\n")
                f.write(f"{'='*80}\n")
                f.write(note_data['notes'])
                f.write(f"\n")
        
        print(f"   ✓ Site Notes: {len(self.all_site_notes)} sites → {filename.name}")
    
    def export_security_audit(self, filename):
        """Export security findings"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['site_id', 'severity', 'type', 'detail']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.security_issues)
        
        # Count by severity
        severity_counts = Counter(issue['severity'] for issue in self.security_issues)
        print(f"   ✓ Security: {len(self.security_issues)} issues → {filename.name}")
        print(f"      Critical: {severity_counts.get('critical', 0)}, High: {severity_counts.get('high', 0)}, Medium: {severity_counts.get('medium', 0)}")
    
    def export_version_analysis(self, filename):
        """Export version distribution"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['site_id', 'freepbx_version', 'asterisk_version', 'platform', 'system_ip'])
            writer.writeheader()
            writer.writerows(self.version_data)
        
        print(f"   ✓ Versions: {len(self.version_data)} systems → {filename.name}")
    
    def export_platform_stats(self, filename):
        """Export platform statistics"""
        platform_counts = Counter(site.get('platform', 'Unknown') for site in self.sites)
        status_counts = Counter(site.get('status', 'Unknown') for site in self.sites)
        call_center_count = sum(1 for site in self.sites if site.get('call_center', '').lower() == 'yes')
        
        freepbx_versions = Counter(site.get('freepbx_version', 'Unknown') for site in self.sites)
        asterisk_versions = Counter(site.get('asterisk_version', 'Unknown') for site in self.sites)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("VPBX PLATFORM STATISTICS\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Total Sites Analyzed: {len(self.sites)}\n\n")
            
            f.write("PLATFORM DISTRIBUTION:\n")
            for platform, count in platform_counts.most_common():
                pct = (count / len(self.sites) * 100) if self.sites else 0
                f.write(f"  {platform:20s} {count:4d} sites ({pct:5.1f}%)\n")
            
            f.write(f"\nSTATUS DISTRIBUTION:\n")
            for status, count in status_counts.most_common():
                pct = (count / len(self.sites) * 100) if self.sites else 0
                f.write(f"  {status:20s} {count:4d} sites ({pct:5.1f}%)\n")
            
            f.write(f"\nFEATURES:\n")
            f.write(f"  Call Center Enabled: {call_center_count} sites\n")
            f.write(f"  Total Devices: {len(self.all_devices)} phones\n")
            f.write(f"  Total SIP Accounts: {len(self.all_sip_accounts)} registrations\n")
            
            f.write(f"\nTOP FREEPBX VERSIONS:\n")
            for version, count in freepbx_versions.most_common(10):
                f.write(f"  {version:20s} {count:4d} sites\n")
            
            f.write(f"\nTOP ASTERISK VERSIONS:\n")
            for version, count in asterisk_versions.most_common(10):
                f.write(f"  {version:20s} {count:4d} sites\n")
        
        print(f"   ✓ Platform Stats → {filename.name}")
    
    def export_executive_summary(self, filename):
        """Generate executive summary"""
        # Calculate key metrics
        total_sites = len(self.sites)
        total_devices = len(self.all_devices)
        critical_issues = sum(1 for issue in self.security_issues if issue['severity'] == 'critical')
        high_issues = sum(1 for issue in self.security_issues if issue['severity'] == 'high')
        
        eol_asterisk = sum(1 for site in self.sites 
                          if site.get('asterisk_major', '') in ['1', '10', '11', '12', '13', '14', '15'])
        eol_freepbx = sum(1 for site in self.sites 
                         if site.get('freepbx_major', '') in ['2', '12', '13'])
        
        platform_counts = Counter(site.get('platform', 'Unknown') for site in self.sites)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("╔" + "═" * 78 + "╗\n")
            f.write("║" + " " * 20 + "VPBX INFRASTRUCTURE ANALYSIS" + " " * 30 + "║\n")
            f.write("║" + " " * 25 + "EXECUTIVE SUMMARY" + " " * 36 + "║\n")
            f.write("╚" + "═" * 78 + "╝\n\n")
            
            f.write("INFRASTRUCTURE OVERVIEW:\n")
            f.write("-" * 80 + "\n")
            f.write(f"  Total VPBX Sites: {total_sites}\n")
            f.write(f"  Total Devices: {total_devices}\n")
            f.write(f"  Total SIP Accounts: {len(self.all_sip_accounts)}\n\n")
            
            f.write("PLATFORM BREAKDOWN:\n")
            f.write("-" * 80 + "\n")
            for platform, count in platform_counts.most_common():
                pct = (count / total_sites * 100) if total_sites else 0
                f.write(f"  {platform}: {count} sites ({pct:.1f}%)\n")
            f.write("\n")
            
            f.write("SECURITY POSTURE:\n")
            f.write("-" * 80 + "\n")
            f.write(f"  🔴 CRITICAL Issues: {critical_issues}\n")
            f.write(f"  🟠 HIGH Issues: {high_issues}\n")
            f.write(f"  Total Security Findings: {len(self.security_issues)}\n\n")
            
            f.write("VERSION COMPLIANCE:\n")
            f.write("-" * 80 + "\n")
            f.write(f"  ⚠️  EOL Asterisk Versions: {eol_asterisk} sites ({eol_asterisk/total_sites*100:.1f}%)\n")
            f.write(f"  ⚠️  EOL FreePBX Versions: {eol_freepbx} sites ({eol_freepbx/total_sites*100:.1f}%)\n\n")
            
            f.write("TOP PRIORITIES:\n")
            f.write("-" * 80 + "\n")
            
            if critical_issues > 0:
                f.write(f"  1. IMMEDIATE: Address {critical_issues} critical security issues\n")
            if high_issues > 0:
                f.write(f"  2. HIGH: Remediate {high_issues} high-severity security findings\n")
            if eol_asterisk > 0:
                f.write(f"  3. MEDIUM: Upgrade {eol_asterisk} systems running EOL Asterisk\n")
            if eol_freepbx > 0:
                f.write(f"  4. MEDIUM: Upgrade {eol_freepbx} systems running EOL FreePBX\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("REPORTS GENERATED:\n")
            f.write("  • ALL_CREDENTIALS_SENSITIVE.csv - Complete access credentials\n")
            f.write("  • server_inventory_complete.csv - Full server inventory\n")
            f.write("  • device_inventory_all.csv - All phone devices\n")
            f.write("  • security_audit_comprehensive.csv - Security findings\n")
            f.write("  • version_analysis.csv - Version distribution\n")
            f.write("  • platform_statistics.txt - Platform breakdowns\n")
            f.write("  • site_notes_knowledge_base.txt - All site notes\n")
            f.write("  • complete_analysis.json - Full data dump\n")
        
        print(f"   ✓ Executive Summary → {filename.name}")
    
    def export_json_dump(self, filename):
        """Export complete analysis as JSON"""
        data = {
            'metadata': {
                'total_sites': len(self.sites),
                'total_devices': len(self.all_devices),
                'total_sip_accounts': len(self.all_sip_accounts),
                'total_security_issues': len(self.security_issues),
            },
            'sites': self.sites,
            'credentials': self.all_credentials,
            'devices': self.all_devices,
            'sip_accounts': self.all_sip_accounts,
            'security_issues': self.security_issues,
            'version_data': self.version_data,
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        print(f"   ✓ JSON Dump → {filename.name}")

# =====================
# Main CLI Entry Point
# =====================

def main():
        """
        Main entry point for the Ultimate VPBX Data Analyzer CLI.
        Handles argument parsing, orchestrates the full analysis workflow, and triggers report generation.
        Steps:
            1. Parse command-line arguments for data and output directories.
            2. Initialize the analyzer with the provided data directory.
            3. Run the full analysis across all sites.
            4. Generate all summary and detail reports in the output directory.
            5. Print completion message.
        """
        # Set up command-line argument parsing
        parser = argparse.ArgumentParser(description='Ultimate VPBX Data Analyzer')
        parser.add_argument('--data-dir', required=True, help='Directory containing scraped VPBX data')
        parser.add_argument('--output-dir', default='.', help='Output directory for reports')

        # Parse arguments from sys.argv
        args = parser.parse_args()

        # Initialize the main analyzer object with the data directory
        analyzer = UltimateVPBXAnalyzer(args.data_dir)

        # Run the main analysis routine for all sites
        analyzer.analyze_all_sites()

        # Generate all output reports (JSON, HTML, etc.)
        analyzer.generate_reports(args.output_dir)

        # Notify user of completion
        print("\n🎉 Ultimate analysis complete!")


if __name__ == '__main__':
    # If this script is run directly (not imported), invoke the main CLI entry point
    main()
