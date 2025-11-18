#!/usr/bin/env python3
"""
deep_analyze_scraped_data.py

Purpose:
    Perform comprehensive, deep analysis of scraped VPBX (Virtual PBX) data. Extracts, audits, and summarizes all information from HTML and config files, including:
    - Server credentials (FTP, SSH, REST API)
    - Phone configurations (SIP credentials, MAC addresses)
    - Site-specific settings
    - Device inventory
    - Security analysis
    - Version tracking

Technical Overview:
    1. Loads all scraped HTML/config files for each site from a specified directory.
    2. Extracts structured data (servers, phones, SIP configs, site configs) using regex and HTML parsing.
    3. Performs security audits (weak passwords, EOL versions, etc) and platform detection.
    4. Aggregates statistics and generates multiple CSV/JSON reports for further analysis.
    5. Outputs all results to the data directory for downstream use.

Variable Legend:
    data_dir: Path to directory containing all scraped site folders (entry_*).
    entry_dirs: List of Path objects for each site (entry_12345, etc).
    site_id: Unique identifier for each site (from folder name).
    self.results: Main dict holding all extracted and computed data.
        - servers: Dict of server info per site_id
        - phones: List of all phone/device dicts
        - sip_configs: List of SIP config dicts
        - site_configs: Dict of site-wide XML config per site_id
        - security_audit: List of security issue dicts
        - statistics: Dict of overall stats
        - platforms: Counter of detected platform types
    server_info: Dict of extracted server fields for a site
    device: Dict of extracted phone/device fields
    config: Dict of extracted site XML config fields
    issues: List of security issue dicts for a site/config
    args: Parsed command-line arguments

Script Flow:
    - ComprehensiveVPBXAnalyzer: Main class for all analysis logic
        - analyze_all(): Orchestrates full analysis for all sites
        - analyze_site(): Extracts all data for a single site
        - extract_server_info(): Parses server credentials/info from HTML
        - extract_device_inventory(): Parses phone/device table from HTML
        - extract_site_xml_config(): Parses site-wide XML config from HTML
        - extract_sip_configs(): Parses SIP credentials from HTML
        - audit_server_security(): Checks for weak/EOL credentials/versions
        - audit_site_config_security(): Checks for weak phone admin passwords
        - generate_*(): Prints and saves various reports
        - save_*_csv(): Writes CSV files for inventory, security, credentials
    - main(): Handles CLI args, runs analysis, prints output summary

"""

import re
import json
import csv
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import html

class ComprehensiveVPBXAnalyzer:
    """
    Deep analyzer for all scraped VPBX data.
    Loads, parses, audits, and summarizes all site/server/phone/config/security data from a directory of scraped HTML/config files.
    Produces comprehensive JSON and CSV reports for further analysis.
    """
    
    def __init__(self, data_dir):
        # Path to directory containing all entry_* site folders
        self.data_dir = Path(data_dir)
        # Main results dict for all extracted and computed data
        self.results = {
            'servers': {},           # Server-level data (credentials, versions)
            'phones': [],            # All phone devices across all sites
            'sip_configs': [],       # SIP registration configs
            'site_configs': {},      # Site-wide XML configurations
            'security_audit': [],    # Security findings
            'statistics': {},        # Overall stats
            'platforms': Counter(),  # Platform distribution
        }
        
    def analyze_all(self):
        """
        Run comprehensive analysis for all sites in data_dir.
        - Iterates over all entry_* folders
        - Extracts all server, phone, config, and security data
        - Aggregates statistics and generates reports
        - Saves all results to JSON/CSV files
        Returns: self.results
        """
        print("=" * 80)
        print("COMPREHENSIVE VPBX DATA ANALYSIS")
        print("=" * 80)
        print()
        
        # Find all entry directories
        # Find all entry_* directories (one per site)
        entry_dirs = sorted([d for d in self.data_dir.iterdir() 
                   if d.is_dir() and d.name.startswith('entry_')])
        
        total = len(entry_dirs)
        print(f"Found {total} sites to analyze")
        print()
        
        for idx, entry_dir in enumerate(entry_dirs, 1):
            site_id = entry_dir.name.replace('entry_', '')
            
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{total} sites analyzed...")
            
            # Analyze all aspects of this site
            self.analyze_site(site_id, entry_dir)
        
        print(f"\n✓ Completed: {total} sites analyzed\n")
        
        # Generate comprehensive reports
        self.generate_server_inventory()
        self.generate_phone_inventory()
        self.generate_security_report()
        self.generate_configuration_summary()
        self.generate_statistics()
        
        # Save all results
        self.save_results()
        
        return self.results
    
    def analyze_site(self, site_id, entry_dir):
        """
        Analyze all files for a single site (entry_dir).
        - Extracts server info, phone inventory, site XML config, SIP configs
        - Runs security audits and platform detection
        - Appends all results to self.results
        """
        
        # 1. Extract server credentials and info from detail_main.html
        detail_html = entry_dir / "detail_main.html"
        if detail_html.exists():
            server_info = self.extract_server_info(detail_html)
            if server_info:
                server_info['site_id'] = site_id
                self.results['servers'][site_id] = server_info
                
                # Platform detection
                platform = self.detect_platform(server_info)
                self.results['platforms'][platform] += 1
                server_info['platform'] = platform
                
                # Security audit
                self.audit_server_security(site_id, server_info)
        
        # 2. Extract phone device inventory from site_specific_config
        site_config_txt = entry_dir / "site_specific_config.txt"
        site_config_html = entry_dir / "site_specific_config.html"
        
        if site_config_html.exists():
            devices = self.extract_device_inventory(site_config_html)
            for device in devices:
                device['site_id'] = site_id
                device['site_handle'] = self.results['servers'].get(site_id, {}).get('handle', '')
                self.results['phones'].append(device)
            
            # Extract site-wide XML config
            site_xml_config = self.extract_site_xml_config(site_config_html)
            if site_xml_config:
                self.results['site_configs'][site_id] = site_xml_config
                self.audit_site_config_security(site_id, site_xml_config)
        
        # 3. Extract SIP credentials from view_config
        view_config_html = entry_dir / "view_config.html"
        if view_config_html.exists():
            sip_configs = self.extract_sip_configs(view_config_html)
            for sip_config in sip_configs:
                sip_config['site_id'] = site_id
                self.results['sip_configs'].append(sip_config)
    
    def extract_server_info(self, html_file):
        """
        Extract all server information from detail_main.html for a site.
        Uses regex to parse all credential/version fields and admin URL.
        Returns: dict of server fields or None on error.
        """
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Unescape HTML entities
            content = html.unescape(content)
            
            patterns = {
                'handle': r'name="handle"\s+value="([^"]+)"',
                'company': r'name="cname"\s+value="([^"]*)"',
                'status': r'<select[^>]+name="status"[^>]*>.*?<option[^>]+selected[^>]*>([^<]+)</option>',
                'system_ip': r'name="ip"\s+value="([^"]+)"',
                'ftp_host': r'name="ftp_host"\s+value="([^"]+)"',
                'ftp_user': r'name="ftp_user"\s+value="([^"]+)"',
                'ftp_password': r'name="ftp_pass"\s+value="([^"]+)"',
                'rest_user': r'name="rest_user"\s+value="([^"]+)"',
                'rest_password': r'name="rest_pass"\s+value="([^"]+)"',
                'freepbx_version': r'name="freepbx_version"\s+value="([^"]+)"',
                'asterisk_version': r'name="asterisk_version"\s+value="([^"]+)"',
                'deployment_id': r'name="deployment_id"\s+value="([^"]+)"',
                'vm_id': r'name="vmName"\s+value="([^"]+)"',
                'call_center': r'name="asternic"\s+value="([^"]*)"',
                'over_the_top': r'name="overTheTop"[^>]*>.*?<option[^>]+value="([^"]+)"[^>]+selected',
            }
            
            server_info = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    value = match.group(1).strip()
                    server_info[key] = value
            
            # Extract admin URL (special case)
            admin_url_match = re.search(r'href="([^"]*admin/config\.php[^"]*)"', content)
            if admin_url_match:
                server_info['admin_url'] = admin_url_match.group(1)
            
            return server_info if server_info else None
            
        except Exception as e:
            print(f"    Error extracting server info: {e}")
            return None
    
    def extract_device_inventory(self, html_file):
        """
        Extract device inventory table from HTML for a site.
        Parses each row for device_id, MAC, make, model, directory_name, extension.
        Returns: list of device dicts.
        """
        devices = []
        
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find device table rows - look for patterns in the HTML table
            # Pattern: <tr>...<td>device_id</td><td>mac</td><td>make</td><td>model</td>...
            
            # Find table with device data
            table_pattern = r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>.*?<td[^>]*>([^<]*)</td>.*?<td[^>]*>([0-9a-fA-F:]+)</td>.*?<td[^>]*>(\w+)</td>.*?<td[^>]*>([^<]+)</td>'
            
            # Alternative: parse row by row
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            rows = re.findall(row_pattern, content, re.DOTALL)
            
            for row in rows:
                # Look for device data pattern
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                
                if len(cells) >= 10:  # Typical device row has many columns
                    # Try to identify device rows by checking for MAC address pattern
                    mac_found = False
                    device_id = None
                    mac = None
                    make = None
                    model = None
                    directory_name = None
                    
                    for i, cell in enumerate(cells):
                        cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                        
                        # Device ID (usually first column, numeric)
                        if i == 0 and cell_text.isdigit():
                            device_id = cell_text
                        
                        # Directory name (usually has <extension> format)
                        if '<' in cell_text and '>' in cell_text:
                            directory_name = cell_text
                        
                        # MAC address (12 hex chars with colons)
                        if re.match(r'^[0-9a-fA-F]{12}$|^[0-9a-fA-F:]{17}$', cell_text):
                            mac = cell_text
                            mac_found = True
                        
                        # Make (polycom, cisco, yealink, etc.)
                        if cell_text.lower() in ['polycom', 'cisco', 'yealink', 'grandstream', 
                                                  'fanvil', 'algo', 'sangoma']:
                            make = cell_text.lower()
                        
                        # Model (VVX400, CP-7841, etc.)
                        if re.match(r'^[A-Z0-9\-]+\d+', cell_text, re.IGNORECASE):
                            if not make or i > cells.index(next((c for c in cells if make in c.lower()), '')):
                                model = cell_text
                    
                    if mac_found and device_id and make:
                        # Extract extension from directory name
                        extension = ''
                        if directory_name:
                            ext_match = re.search(r'<(\d+)>', directory_name)
                            if ext_match:
                                extension = ext_match.group(1)
                        
                        device = {
                            'device_id': device_id,
                            'directory_name': directory_name or '',
                            'extension': extension,
                            'mac': mac,
                            'make': make,
                            'model': model or '',
                        }
                        devices.append(device)
        
        except Exception as e:
            print(f"    Error extracting devices: {e}")
        
        return devices
    
    def extract_site_xml_config(self, html_file):
        """
        Extract site-wide XML configuration from HTML for a site.
        Looks for key config fields (SIP server, admin/user password, NTP, GMT offset).
        Returns: dict of config fields or None.
        """
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            config = {}
            
            # Extract from XML in the page
            patterns = {
                'sip_server': r'voIpProt\.server\.1\.address\s*=\s*"([^"]+)"',
                'admin_password': r'device\.auth\.localAdminPassword\s*=\s*"([^"]+)"',
                'user_password': r'device\.auth\.localUserPassword\s*=\s*"([^"]+)"',
                'ntp_server': r'device\.sntp\.serverName\s*=\s*"([^"]*)"',
                'gmt_offset': r'device\.sntp\.gmtOffset\s*=\s*"([^"]*)"',
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                if match:
                    config[key] = match.group(1)
            
            return config if config else None
            
        except Exception as e:
            return None
    
    def extract_sip_configs(self, html_file):
        """
        Extract SIP configuration from view_config.html for a site.
        Looks for SIP registration parameters (userid, password, address, etc).
        Returns: list of SIP config dicts.
        """
        configs = []
        
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for SIP registration parameters in XML
            patterns = {
                'userid': r'reg\.1\.auth\.userid\s*=\s*"([^"]+)"',
                'password': r'reg\.1\.auth\.password\s*=\s*"([^"]+)"',
                'address': r'reg\.1\.address\s*=\s*"([^"]+)"',
                'displayname': r'reg\.1\.displayname\s*=\s*"([^"]+)"',
                'label': r'reg\.1\.line\.1\.label\s*=\s*"([^"]+)"',
            }
            
            config = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                if match:
                    config[key] = match.group(1)
            
            if config:
                configs.append(config)
        
        except Exception as e:
            pass
        
        return configs
    
    def detect_platform(self, server_info):
        """
        Detect platform type (FreePBX, Fusion, or 123NET UC) for a server.
        Uses version and VM ID fields to classify platform.
        Returns: string platform name.
        """
        fpbx_ver = server_info.get('freepbx_version', '').upper()
        vm_id = server_info.get('vm_id', '').upper()
        
        if 'FUSION' in fpbx_ver or 'FUSION' in vm_id:
            return 'Fusion'
        elif '123NET UC' in fpbx_ver or 'UC' in fpbx_ver:
            return '123NET UC'
        else:
            return 'FreePBX'
    
    def audit_server_security(self, site_id, server_info):
        """
        Audit server-level security for a site.
        Checks for weak FTP/REST passwords, EOL Asterisk versions, etc.
        Appends any issues found to self.results['security_audit'].
        """
        issues = []
        
        # Check FTP password strength
        ftp_pass = server_info.get('ftp_password', '')
        if ftp_pass:
            if len(ftp_pass) < 12:
                issues.append({
                    'site_id': site_id,
                    'type': 'weak_ftp_password',
                    'severity': 'high',
                    'detail': f"FTP password only {len(ftp_pass)} characters"
                })
            
            if ftp_pass.isdigit() or ftp_pass.isalpha():
                issues.append({
                    'site_id': site_id,
                    'type': 'simple_ftp_password',
                    'severity': 'high',
                    'detail': "FTP password is only digits or letters"
                })
        
        # Check REST password (should be MD5 hash)
        rest_pass = server_info.get('rest_password', '')
        if rest_pass:
            if len(rest_pass) != 32 or not all(c in '0123456789abcdef' for c in rest_pass.lower()):
                issues.append({
                    'site_id': site_id,
                    'type': 'plain_rest_password',
                    'severity': 'critical',
                    'detail': "REST password not MD5 hashed"
                })
        
        # Check for old/EOL versions
        asterisk_ver = server_info.get('asterisk_version', '')
        if asterisk_ver.startswith('1.8') or asterisk_ver.startswith('11.') or asterisk_ver.startswith('13.'):
            issues.append({
                'site_id': site_id,
                'type': 'eol_asterisk',
                'severity': 'high',
                'detail': f"Asterisk {asterisk_ver} is End-of-Life"
            })
        
        self.results['security_audit'].extend(issues)
    
    def audit_site_config_security(self, site_id, config):
        """
        Audit site-wide phone configuration security for a site.
        Checks for weak/numeric admin passwords.
        Appends any issues found to self.results['security_audit'].
        """
        issues = []
        
        # Check admin password
        admin_pass = config.get('admin_password', '')
        if admin_pass:
            if len(admin_pass) < 8:
                issues.append({
                    'site_id': site_id,
                    'type': 'weak_admin_password',
                    'severity': 'critical',
                    'detail': f"Phone admin password only {len(admin_pass)} characters"
                })
            
            if admin_pass.isdigit():
                issues.append({
                    'site_id': site_id,
                    'type': 'numeric_admin_password',
                    'severity': 'critical',
                    'detail': "Phone admin password is numeric only"
                })
        
        self.results['security_audit'].extend(issues)
    
    def generate_server_inventory(self):
        """
        Generate and print a complete server inventory report.
        Shows platform and status breakdowns, call center stats.
        """
        print("=" * 80)
        print("SERVER INVENTORY")
        print("=" * 80)
        print()
        
        total_servers = len(self.results['servers'])
        print(f"Total Servers: {total_servers}")
        print()
        
        # Platform breakdown
        print("By Platform:")
        for platform, count in self.results['platforms'].most_common():
            pct = (count / total_servers * 100) if total_servers > 0 else 0
            print(f"  {platform:20} {count:5} ({pct:5.1f}%)")
        print()
        
        # Status breakdown
        statuses = Counter()
        for server in self.results['servers'].values():
            status = server.get('status', 'unknown')
            statuses[status] += 1
        
        print("By Status:")
        for status, count in statuses.most_common():
            pct = (count / total_servers * 100) if total_servers > 0 else 0
            print(f"  {status:25} {count:5} ({pct:5.1f}%)")
        print()
        
        # Call Center
        call_center_count = sum(1 for s in self.results['servers'].values() 
                               if s.get('call_center'))
        print(f"Asternic Call Center 2 Installed: {call_center_count} servers")
        print()
    
    def generate_phone_inventory(self):
        """
        Generate and print a phone inventory report.
        Shows manufacturer and model breakdowns.
        """
        print("=" * 80)
        print("PHONE INVENTORY")
        print("=" * 80)
        print()
        
        total_phones = len(self.results['phones'])
        print(f"Total Phones: {total_phones}")
        print()
        
        # By manufacturer
        makes = Counter()
        for phone in self.results['phones']:
            makes[phone.get('make', 'unknown')] += 1
        
        print("By Manufacturer:")
        for make, count in makes.most_common():
            pct = (count / total_phones * 100) if total_phones > 0 else 0
            print(f"  {make.capitalize():20} {count:5} ({pct:5.1f}%)")
        print()
        
        # By model (top 20)
        models = Counter()
        for phone in self.results['phones']:
            make = phone.get('make', 'unknown')
            model = phone.get('model', 'unknown')
            models[f"{make} {model}"] += 1
        
        print("Top 20 Models:")
        for model, count in models.most_common(20):
            pct = (count / total_phones * 100) if total_phones > 0 else 0
            print(f"  {model:35} {count:5} ({pct:5.1f}%)")
        print()
    
    def generate_security_report(self):
        """
        Generate and print a security audit report.
        Groups issues by severity and type.
        """
        print("=" * 80)
        print("SECURITY AUDIT")
        print("=" * 80)
        print()
        
        if not self.results['security_audit']:
            print("✓ No security issues detected")
            print()
            return
        
        # Group by severity
        by_severity = defaultdict(list)
        for issue in self.results['security_audit']:
            by_severity[issue['severity']].append(issue)
        
        total_issues = len(self.results['security_audit'])
        print(f"Total Issues: {total_issues}")
        print()
        
        for severity in ['critical', 'high', 'medium', 'low']:
            issues = by_severity.get(severity, [])
            if issues:
                print(f"{severity.upper()}: {len(issues)} issues")
                
                # Group by type
                by_type = defaultdict(int)
                for issue in issues:
                    by_type[issue['type']] += 1
                
                for issue_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {issue_type:30} {count:5} occurrences")
                print()
    
    def generate_configuration_summary(self):
        """
        Generate and print a configuration summary.
        Shows FreePBX and Asterisk version breakdowns.
        """
        print("=" * 80)
        print("CONFIGURATION SUMMARY")
        print("=" * 80)
        print()
        
        # FreePBX versions
        fpbx_versions = Counter()
        for server in self.results['servers'].values():
            ver = server.get('freepbx_version', 'unknown')
            fpbx_versions[ver] += 1
        
        print("Top 10 FreePBX Versions:")
        for version, count in fpbx_versions.most_common(10):
            print(f"  {version:25} {count:5} servers")
        print()
        
        # Asterisk versions
        ast_versions = Counter()
        for server in self.results['servers'].values():
            ver = server.get('asterisk_version', 'unknown')
            ast_versions[ver] += 1
        
        print("Top 10 Asterisk Versions:")
        for version, count in ast_versions.most_common(10):
            print(f"  {version:25} {count:5} servers")
        print()
    
    def generate_statistics(self):
        """
        Generate overall statistics and store in self.results['statistics'].
        """
        self.results['statistics'] = {
            'total_servers': len(self.results['servers']),
            'total_phones': len(self.results['phones']),
            'total_sip_configs': len(self.results['sip_configs']),
            'security_issues': len(self.results['security_audit']),
            'platforms': dict(self.results['platforms']),
            'generated_at': datetime.now().isoformat()
        }
    
    def save_results(self):
        """
        Save all results to files in the data directory.
        - comprehensive_analysis.json: All extracted and computed data
        - server_inventory.csv: Server inventory
        - phone_inventory.csv: Phone inventory
        - security_audit.csv: Security findings
        - server_credentials_SENSITIVE.csv: Credentials (keep secure)
        """
        output_dir = self.data_dir
        
        # 1. Save comprehensive JSON
        json_file = output_dir / "comprehensive_analysis.json"
        
        # Convert Counters to dicts for JSON
        serializable_results = {
            'servers': self.results['servers'],
            'phones': self.results['phones'],
            'sip_configs': self.results['sip_configs'],
            'site_configs': self.results['site_configs'],
            'security_audit': self.results['security_audit'],
            'statistics': self.results['statistics'],
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2)
        
        print(f"✓ Saved: {json_file}")
        
        # 2. Save server inventory CSV
        self.save_server_inventory_csv()
        
        # 3. Save phone inventory CSV
        self.save_phone_inventory_csv()
        
        # 4. Save security audit CSV
        self.save_security_audit_csv()
        
        # 5. Save credentials (SENSITIVE!)
        self.save_credentials_csv()
        
        print()
    
    def save_server_inventory_csv(self):
        """
        Save server inventory as CSV (server_inventory.csv).
        """
        csv_file = self.data_dir / "server_inventory.csv"
        
        if not self.results['servers']:
            return
        
        fieldnames = ['site_id', 'handle', 'company', 'platform', 'status', 
                     'system_ip', 'freepbx_version', 'asterisk_version', 
                     'deployment_id', 'vm_id', 'call_center']
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            
            for site_id, server in self.results['servers'].items():
                row = {'site_id': site_id, **server}
                writer.writerow(row)
        
        print(f"✓ Saved: {csv_file}")
    
    def save_phone_inventory_csv(self):
        """
        Save phone inventory as CSV (phone_inventory.csv).
        """
        csv_file = self.data_dir / "phone_inventory.csv"
        
        if not self.results['phones']:
            return
        
        fieldnames = ['site_id', 'site_handle', 'device_id', 'directory_name', 
                     'extension', 'mac', 'make', 'model']
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(self.results['phones'])
        
        print(f"✓ Saved: {csv_file}")
    
    def save_security_audit_csv(self):
        """
        Save security audit as CSV (security_audit.csv).
        """
        csv_file = self.data_dir / "security_audit.csv"
        
        if not self.results['security_audit']:
            return
        
        fieldnames = ['site_id', 'severity', 'type', 'detail']
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results['security_audit'])
        
        print(f"✓ Saved: {csv_file}")
    
    def save_credentials_csv(self):
        """
        Save server credentials as CSV (server_credentials_SENSITIVE.csv).
        This file contains sensitive information and should be kept secure.
        """
        csv_file = self.data_dir / "server_credentials_SENSITIVE.csv"
        
        if not self.results['servers']:
            return
        
        fieldnames = ['site_id', 'handle', 'company', 'system_ip', 
                     'ftp_host', 'ftp_user', 'ftp_password',
                     'rest_user', 'rest_password', 'admin_url']
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            
            for site_id, server in self.results['servers'].items():
                row = {'site_id': site_id, **server}
                writer.writerow(row)
        
        print(f"✓ Saved: {csv_file} (KEEP SECURE!)")

def main():
    """
    Main entry point for the script.
    Parses command-line arguments, runs comprehensive analysis, prints output summary.
    """
    import argparse
    parser = argparse.ArgumentParser(
        description='Comprehensive deep analysis of scraped VPBX data'
    )
    parser.add_argument(
        '--data-dir',
        default='freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive',
        help='Directory containing scraped VPBX data'
    )
    args = parser.parse_args()
    analyzer = ComprehensiveVPBXAnalyzer(args.data_dir)
    results = analyzer.analyze_all()
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print()
    print("Output files:")
    print("  - comprehensive_analysis.json (complete data)")
    print("  - server_inventory.csv (server list)")
    print("  - phone_inventory.csv (all phones)")
    print("  - security_audit.csv (security findings)")
    print("  - server_credentials_SENSITIVE.csv (credentials - KEEP SECURE!)")
    print()

if __name__ == '__main__':
    main()
