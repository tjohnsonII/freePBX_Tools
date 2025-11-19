
#!/usr/bin/env python3
"""
Phone Configuration Analyzer
---------------------------
Parses and analyzes VoIP phone configuration files (Polycom, Yealink, Cisco, etc.)
Provides security audits, feature analysis, and compliance checks.

VARIABLE MAP (Key Objects & Structures)
---------------------------------------
config_data: Dict[str, Any]   # Parsed config parameters from file
phone_type: str               # Detected phone vendor/type (polycom, yealink, etc.)
findings: Dict[str, Any]      # All analysis results (security_issues, warnings, features, etc.)
security_standards: Dict      # Security policy/baseline values
recommended_features: Dict    # Feature keys and recommended values

Major Methods:
    - parse_config_file: Dispatches to vendor-specific parser
    - analyze_*: Each analyzes a config aspect (SIP, security, network, etc.)
    - print_report: Outputs human-readable summary
    - export_json/csv: Save results for automation

Usage: See main() for CLI options and examples
"""

import re
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Any, Optional



# =========================
# Terminal Color Codes
# =========================
class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'



# =========================
# Main Analyzer Class
# =========================
class PhoneConfigAnalyzer:
    """
    Parse and analyze VoIP phone configuration files.
    Handles vendor detection, parsing, and all analysis routines.
    Results are stored in self.findings for reporting/export.
    """
    
    def __init__(self):
        # Parsed config parameters (key-value pairs)
        self.config_data = {}
        # Detected phone type (polycom, yealink, etc.)
        self.phone_type = None
        # Model (optional, not always detected)
        self.model = None
        # All findings/results from analysis
        self.findings = {
            'security_issues': [],      # List of security problems
            'config_warnings': [],      # List of config warnings
            'feature_status': {},       # Feature enablement status
            'sip_accounts': [],         # SIP account details
            'network_config': {},       # Network config summary
            'line_keys': [],            # Line key assignments
            'softkeys': [],             # Custom softkeys
            'statistics': {}            # Misc. stats (e.g., line key summary)
        }
        
        # Security baselines (policy)
        self.security_standards = {
            'min_password_length': 8,
            'require_https': True,
            'default_passwords': ['456', '123', 'admin', 'password', 'polycom', 'yealink'],
            'weak_ciphers': ['NULL', 'EXPORT', 'DES', 'MD5', 'RC4'],
            'secure_protocols': ['TLS', 'SRTP', 'HTTPS']
        }
        
        # Feature recommendations (best practices)
        self.recommended_features = {
            'voice.volume.persist.handset': '1',
            'voice.volume.persist.headset': '1',
            'feature.presence.enabled': '1',
            'ptt.pageMode.enable': '1',
            'sec.TLS.cipherList': 'RSA:!EXP:!LOW:!NULL:!MD5:@STRENGTH'
        }
    
    def detect_phone_type(self, content: str) -> str:
        """
        Detect phone manufacturer from config content using unique markers.
        Returns: 'polycom', 'yealink', 'cisco', 'grandstream', 'sangoma', or 'unknown'
        """
        if '<PHONE_CONFIG>' in content or 'voIpProt.SIP' in content:
            return 'polycom'
        elif 'account.1.enable' in content and 'static.auto_provision' in content:
            return 'yealink'
        elif '<cisco>' in content or ('<device>' in content and 'cisco' in content.lower()):
            return 'cisco'
        elif 'P-Value' in content or 'account.1.enable' in content:
            return 'grandstream'
        elif '[SIP]' in content or 'registration_1_' in content:
            return 'sangoma'
        else:
            return 'unknown'
    
    def parse_polycom_xml(self, filepath: Path) -> Dict[str, Any]:
        """
        Parse Polycom XML configuration file.
        Returns a dict of config parameters. Falls back to regex if XML is invalid.
        """
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            # Extract all attributes from ALL element (Polycom convention)
            if root.tag == 'PHONE_CONFIG':
                all_elem = root.find('.//ALL')
                if all_elem is not None:
                    self.config_data = dict(all_elem.attrib)
            return self.config_data
        except ET.ParseError as e:
            print(f"{Colors.YELLOW}Warning: XML parse error - {e}{Colors.RESET}")
            # Fallback to regex parsing for broken XML
            return self.parse_polycom_text(filepath)
    
    def parse_polycom_text(self, filepath: Path) -> Dict[str, Any]:
        """
        Parse Polycom config using text/regex (fallback method).
        Handles .cfg and broken XML files. Returns dict of config params.
        """
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        # Pattern: parameter="value"
        pattern = r'(\S+)\s*=\s*"([^"]*)"'
        matches = re.findall(pattern, content)
        for key, value in matches:
            self.config_data[key] = value
        return self.config_data
    
    def parse_yealink_cfg(self, filepath: Path) -> Dict[str, Any]:
        """
        Parse Yealink configuration file (key = value format).
        Ignores comments and blank lines. Returns dict of config params.
        """
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        # Yealink format: parameter = value
        pattern = r'^([^#\s][^=]+?)\s*=\s*(.+?)$'
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.match(pattern, line)
            if match:
                key, value = match.groups()
                self.config_data[key.strip()] = value.strip()
        return self.config_data
    
    def parse_config_file(self, filepath: Path) -> Dict[str, Any]:
        """
        Main config parsing dispatcher. Detects phone type and calls appropriate parser.
        Returns dict of config params.
        """
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        self.phone_type = self.detect_phone_type(content)
        print(f"{Colors.CYAN}Detected phone type: {Colors.BOLD}{self.phone_type.upper()}{Colors.RESET}")
        if self.phone_type == 'polycom':
            if filepath.suffix.lower() in ['.xml', '.cfg']:
                return self.parse_polycom_xml(filepath)
            else:
                return self.parse_polycom_text(filepath)
        elif self.phone_type == 'yealink':
            return self.parse_yealink_cfg(filepath)
        else:
            # Generic key=value parser for unknown types
            return self.parse_polycom_text(filepath)
    
    def analyze_sip_accounts(self):
        """
        Extract and analyze SIP account configurations.
        Checks for exposed passwords and collects account details.
        Populates self.findings['sip_accounts'] and adds security issues if found.
        """
        sip_accounts = []
        # Polycom: reg.X.* parameters (X = line number)
        reg_nums = set()
        for key in self.config_data.keys():
            if key.startswith('reg.'):
                match = re.match(r'reg\.(\d+)\.', key)
                if match:
                    reg_nums.add(int(match.group(1)))
        for reg_num in sorted(reg_nums):
            account = {
                'line': reg_num,
                'address': self.config_data.get(f'reg.{reg_num}.address', ''),
                'user_id': self.config_data.get(f'reg.{reg_num}.auth.userId', ''),
                'display_name': self.config_data.get(f'reg.{reg_num}.displayName', ''),
                'label': self.config_data.get(f'reg.{reg_num}.line.1.label', ''),
                'server': self.config_data.get(f'voIpProt.server.{reg_num}.address', ''),
                'password_set': self.config_data.get(f'reg.{reg_num}.auth.password.set', '0'),
            }
            # Check if password is exposed (should be masked)
            pwd_key = f'reg.{reg_num}.auth.password'
            if pwd_key in self.config_data and self.config_data[pwd_key]:
                self.findings['security_issues'].append({
                    'severity': 'CRITICAL',
                    'issue': 'SIP password exposed in config file',
                    'line': reg_num,
                    'detail': 'Password should be masked or excluded from exports'
                })
            sip_accounts.append(account)
        self.findings['sip_accounts'] = sip_accounts
        return sip_accounts
    
    def analyze_security(self):
        """Comprehensive security analysis"""
        issues = []
        
        # Check admin passwords
        admin_pwd = self.config_data.get('device.auth.localAdminPassword', '')
        admin_pwd_set = self.config_data.get('device.auth.localAdminPassword.set', '0')
        
        if admin_pwd and len(admin_pwd) < self.security_standards['min_password_length']:
            issues.append({
                'severity': 'HIGH',
                'issue': 'Weak admin password',
                'detail': f'Password length {len(admin_pwd)} < minimum {self.security_standards["min_password_length"]}'
            })
        
        if admin_pwd in self.security_standards['default_passwords']:
            issues.append({
                'severity': 'CRITICAL',
                'issue': 'Default admin password detected',
                'detail': f'Password "{admin_pwd}" is a known default'
            })
        
        # Check TLS cipher suite
        cipher_list = self.config_data.get('sec.TLS.cipherList', '')
        if cipher_list:
            for weak_cipher in self.security_standards['weak_ciphers']:
                if weak_cipher in cipher_list.upper():
                    issues.append({
                        'severity': 'MEDIUM',
                        'issue': f'Weak cipher enabled: {weak_cipher}',
                        'detail': f'Cipher suite: {cipher_list}'
                    })
        
        # Check provisioning server security
        provision_url = self.config_data.get('apps.push.serverRootURL', '')
        if provision_url and not provision_url.startswith('https://'):
            issues.append({
                'severity': 'MEDIUM',
                'issue': 'Insecure provisioning server',
                'detail': f'URL uses HTTP instead of HTTPS: {provision_url}'
            })
        
        # Check TR-069 (ACS) configuration
        tr069_enabled = self.config_data.get('device.tr069.periodicInform.interval', '0')
        if tr069_enabled != '0':
            acs_url = self.config_data.get('device.tr069.acs.url', '')
            if acs_url and not acs_url.startswith('https://'):
                issues.append({
                    'severity': 'LOW',
                    'issue': 'TR-069 uses insecure connection',
                    'detail': f'ACS URL: {acs_url}'
                })
        
        self.findings['security_issues'].extend(issues)
        return issues
    
    def analyze_network_config(self):
        """Extract network configuration"""
        network = {
            'vlan_id': self.config_data.get('device.net.vlanId', 'none'),
            'lldp_enabled': self.config_data.get('device.net.lldpEnable', '0'),
            'qos_enabled': self.config_data.get('device.qos.enable', '0'),
            'sip_port': self.config_data.get('voIpProt.SIP.localPort', '5060'),
            'ntp_server': self.config_data.get('device.sntp.serverName', '') or 
                         self.config_data.get('tcpIpApp.sntp.address', ''),
            'syslog_server': self.config_data.get('device.syslog.serverName', ''),
            'time_zone': self.config_data.get('device.sntp.gmtOffset', '0'),
        }
        
        self.findings['network_config'] = network
        return network
    
    def analyze_line_keys(self):
        """Analyze line key configurations (BLF, Speed Dial, etc.)"""
        line_keys = []
        
        # Find all line key configurations
        line_key_nums = set()
        for key in self.config_data.keys():
            if key.startswith('lineKey.'):
                match = re.match(r'lineKey\.(\d+)\.', key)
                if match:
                    line_key_nums.add(int(match.group(1)))
        
        # Categorize line keys
        categories = Counter()
        
        for lk_num in sorted(line_key_nums):
            category = self.config_data.get(f'lineKey.{lk_num}.category', 'None')
            if category != 'None':
                line_key = {
                    'key': lk_num,
                    'category': category,
                    'index': self.config_data.get(f'lineKey.{lk_num}.index', ''),
                    'label': self.config_data.get(f'lineKey.{lk_num}.label', ''),
                }
                line_keys.append(line_key)
                categories[category] += 1
        
        self.findings['line_keys'] = line_keys
        self.findings['statistics']['line_key_summary'] = dict(categories)
        
        return line_keys
    
    def analyze_softkeys(self):
        """Analyze softkey configurations"""
        softkeys = []
        
        softkey_nums = set()
        for key in self.config_data.keys():
            if key.startswith('softkey.') and not key.startswith('softkey.feature'):
                match = re.match(r'softkey\.(\d+)\.', key)
                if match:
                    softkey_nums.add(int(match.group(1)))
        
        for sk_num in sorted(softkey_nums):
            enabled = self.config_data.get(f'softkey.{sk_num}.enable', '0')
            if enabled == '1':
                softkey = {
                    'key': sk_num,
                    'label': self.config_data.get(f'softkey.{sk_num}.label', ''),
                    'action': self.config_data.get(f'softkey.{sk_num}.action', ''),
                    'use_idle': self.config_data.get(f'softkey.{sk_num}.use.idle', '0'),
                    'use_active': self.config_data.get(f'softkey.{sk_num}.use.active', '0'),
                }
                softkeys.append(softkey)
        
        self.findings['softkeys'] = softkeys
        return softkeys
    
    def analyze_features(self):
        """Analyze enabled features and check against recommendations"""
        features = {}
        warnings = []
        
        # Check recommended features
        for feature_key, recommended_value in self.recommended_features.items():
            actual_value = self.config_data.get(feature_key, 'not_set')
            features[feature_key] = {
                'current': actual_value,
                'recommended': recommended_value,
                'compliant': actual_value == recommended_value
            }
            
            if actual_value != recommended_value and actual_value != 'not_set':
                warnings.append({
                    'feature': feature_key,
                    'current': actual_value,
                    'recommended': recommended_value
                })
        
        # Check for important features
        important_features = {
            'Presence': self.config_data.get('feature.presence.enabled', '0'),
            'Paging': self.config_data.get('ptt.pageMode.enable', '0'),
            'Volume Persist (Handset)': self.config_data.get('voice.volume.persist.handset', '0'),
            'Volume Persist (Headset)': self.config_data.get('voice.volume.persist.headset', '0'),
            'Enhanced Feature Keys': self.config_data.get('feature.enhancedFeatureKeys.enabled', '0'),
            'Line Key Reassignment': self.config_data.get('lineKey.reassignment.enabled', '0'),
        }
        
        self.findings['feature_status'] = important_features
        self.findings['config_warnings'] = warnings
        
        return features
    
    def analyze_dial_plan(self):
        """Analyze dial plan configuration"""
        dial_plan = self.config_data.get('dialplan.digitmap', '')
        
        if dial_plan:
            # Parse dial plan patterns
            patterns = dial_plan.split('|')
            
            dial_info = {
                'digit_map': dial_plan,
                'pattern_count': len(patterns),
                'patterns': patterns,
                'supports_911': any('911' in p for p in patterns),
                'supports_international': any('011' in p or '00' in p for p in patterns),
                'supports_long_distance': any('1[2-9]' in p for p in patterns),
            }
            
            self.findings['dial_plan'] = dial_info
            
            # Warnings
            if not dial_info['supports_911']:
                self.findings['config_warnings'].append({
                    'feature': 'Emergency Dialing',
                    'detail': '911 pattern not found in dial plan'
                })
    
    def analyze_provisioning(self):
        """Analyze provisioning configuration"""
        prov_info = {
            'server': self.config_data.get('device.prov.serverName', ''),
            'type': self.config_data.get('device.prov.serverType', ''),
            'auto_enabled': self.config_data.get('device.prov.AutoProvEnabled', '0'),
            'ztp_enabled': self.config_data.get('device.prov.ztpEnabled', '0'),
        }
        
        if any(prov_info.values()):
            self.findings['provisioning'] = prov_info
        
        return prov_info
    
    def analyze_attendant_resources(self):
        """Analyze attendant console resources (BLF monitoring)"""
        attendant_resources = []
        
        # Find all attendant.resourceList entries
        resource_nums = set()
        for key in self.config_data.keys():
            if key.startswith('attendant.resourceList.'):
                match = re.match(r'attendant\.resourceList\.(\d+)\.', key)
                if match:
                    resource_nums.add(int(match.group(1)))
        
        for res_num in sorted(resource_nums):
            address = self.config_data.get(f'attendant.resourceList.{res_num}.address', '')
            if address:
                resource = {
                    'index': res_num,
                    'address': address,
                    'label': self.config_data.get(f'attendant.resourceList.{res_num}.label', ''),
                    'type': self.config_data.get(f'attendant.resourceList.{res_num}.type', ''),
                }
                attendant_resources.append(resource)
        
        if attendant_resources:
            self.findings['attendant_resources'] = attendant_resources
        
        return attendant_resources
    
    def analyze_all(self, filepath: Path):
        """Run complete analysis on config file"""
        print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}  Phone Configuration Analyzer{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
        
        print(f"Analyzing: {Colors.BOLD}{filepath.name}{Colors.RESET}\n")
        
        # Parse config
        self.parse_config_file(filepath)
        
        if not self.config_data:
            print(f"{Colors.RED}Error: No configuration data parsed{Colors.RESET}")
            return None
        
        print(f"Parsed {Colors.GREEN}{len(self.config_data)}{Colors.RESET} configuration parameters\n")
        
        # Run analyses
        print(f"{Colors.YELLOW}Running analyses...{Colors.RESET}\n")
        
        self.analyze_sip_accounts()
        self.analyze_security()
        self.analyze_network_config()
        self.analyze_line_keys()
        self.analyze_softkeys()
        self.analyze_features()
        self.analyze_dial_plan()
        self.analyze_provisioning()
        self.analyze_attendant_resources()
        
        return self.findings
    
    def print_report(self):
        """Print comprehensive analysis report"""
        
        # SIP Accounts
        if self.findings['sip_accounts']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}📞 SIP ACCOUNTS ({len(self.findings['sip_accounts'])}){Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}")
            
            for account in self.findings['sip_accounts']:
                print(f"\n  Line {Colors.BOLD}{account['line']}{Colors.RESET}: {account['display_name']}")
                print(f"    Extension:  {account['address']}")
                print(f"    User ID:    {account['user_id']}")
                print(f"    Server:     {account['server']}")
                print(f"    Label:      {account['label']}")
        
        # Security Issues
        if self.findings['security_issues']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.RED}{Colors.BOLD}🔒 SECURITY ISSUES ({len(self.findings['security_issues'])}){Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}")
            
            for issue in self.findings['security_issues']:
                severity = issue['severity']
                color = Colors.RED if severity == 'CRITICAL' else Colors.YELLOW if severity == 'HIGH' else Colors.WHITE
                
                print(f"\n  {color}[{severity}]{Colors.RESET} {issue['issue']}")
                print(f"    {issue['detail']}")
        else:
            print(f"\n{Colors.GREEN}✓ No security issues detected{Colors.RESET}")
        
        # Network Configuration
        if self.findings['network_config']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}🌐 NETWORK CONFIGURATION{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}")
            
            net = self.findings['network_config']
            print(f"\n  VLAN ID:      {net.get('vlan_id', 'none')}")
            print(f"  NTP Server:   {net.get('ntp_server', 'none')}")
            print(f"  Syslog:       {net.get('syslog_server', 'none')}")
            print(f"  SIP Port:     {net.get('sip_port', '5060')}")
            print(f"  LLDP:         {'Enabled' if net.get('lldp_enabled') == '1' else 'Disabled'}")
            print(f"  QoS:          {'Enabled' if net.get('qos_enabled') == '1' else 'Disabled'}")
        
        # Feature Status
        if self.findings['feature_status']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}⚙️  FEATURE STATUS{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
            
            for feature, enabled in self.findings['feature_status'].items():
                status = f"{Colors.GREEN}Enabled{Colors.RESET}" if enabled == '1' else f"{Colors.YELLOW}Disabled{Colors.RESET}"
                print(f"  {feature:30} {status}")
        
        # Line Keys Summary
        if self.findings.get('statistics', {}).get('line_key_summary'):
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}🔘 LINE KEYS SUMMARY{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
            
            for category, count in self.findings['statistics']['line_key_summary'].items():
                print(f"  {category:20} {count:3}")
        
        # Softkeys
        if self.findings['softkeys']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}🎹 CUSTOM SOFTKEYS ({len(self.findings['softkeys'])}){Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
            
            for sk in self.findings['softkeys']:
                print(f"  Key {sk['key']:2}: {sk['label']:15} → {sk['action']}")
        
        # Provisioning Configuration
        if self.findings.get('provisioning'):
            prov = self.findings['provisioning']
            if prov.get('server'):
                print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
                print(f"{Colors.CYAN}{Colors.BOLD}🔧 PROVISIONING CONFIGURATION{Colors.RESET}")
                print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
                
                print(f"  Server:        {Colors.GREEN}{prov['server']}{Colors.RESET}")
                print(f"  Type:          {prov['type']}")
                auto_status = f"{Colors.GREEN}Enabled{Colors.RESET}" if prov['auto_enabled'] == '1' else f"{Colors.YELLOW}Disabled{Colors.RESET}"
                print(f"  Auto-Provision: {auto_status}")
                
                # Security check for provisioning
                if prov['type'] == 'HTTPS':
                    print(f"  Security:      {Colors.GREEN}✓ HTTPS (Secure){Colors.RESET}")
                elif prov['type'] == 'HTTP':
                    print(f"  Security:      {Colors.RED}⚠ HTTP (Insecure){Colors.RESET}")
        
        # Attendant Resources (BLF Monitoring)
        if self.findings.get('attendant_resources'):
            resources = self.findings['attendant_resources']
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.CYAN}{Colors.BOLD}👥 ATTENDANT RESOURCES ({len(resources)} monitored extensions){Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
            
            # Show first 10 and summary
            for resource in resources[:10]:
                ext = resource['address'].split('@')[0] if '@' in resource['address'] else resource['address']
                label = resource['label'] if resource['label'] else '(No label)'
                print(f"  {ext:6} → {label}")
            
            if len(resources) > 10:
                print(f"\n  ... and {len(resources) - 10} more extensions")
                print(f"\n  {Colors.YELLOW}💡 Full list available in JSON export{Colors.RESET}")
        
        # Configuration Warnings
        if self.findings['config_warnings']:
            print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  CONFIGURATION WARNINGS ({len(self.findings['config_warnings'])}){Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}")
            
            for warning in self.findings['config_warnings']:
                print(f"\n  Feature: {warning.get('feature', 'Unknown')}")
                print(f"    Current:     {warning.get('current', 'N/A')}")
                print(f"    Recommended: {warning.get('recommended', 'N/A')}")
                if 'detail' in warning:
                    print(f"    Detail:      {warning['detail']}")
        
        # Analysis Summary & Insights
        self.print_summary()
        
        print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    def print_summary(self):
        """Print comprehensive analysis summary with insights"""
        print(f"\n{Colors.CYAN}{'─'*78}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}📊 ANALYSIS SUMMARY & INSIGHTS{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*78}{Colors.RESET}\n")
        
        # Determine phone type/role based on configuration
        phone_role = self.determine_phone_role()
        print(f"{Colors.BOLD}Phone Type:{Colors.RESET} {phone_role}")
        
        # Configuration statistics
        sip_accounts = [acc for acc in self.findings['sip_accounts'] if acc['address']]
        if sip_accounts:
            acc = sip_accounts[0]
            print(f"{Colors.BOLD}Primary Extension:{Colors.RESET} {acc['address']} on {acc['server']}")
        
        print(f"{Colors.BOLD}Total Parameters:{Colors.RESET} {len(self.config_data)}")
        
        # Line key utilization
        if self.findings.get('statistics', {}).get('line_key_summary'):
            total_keys = sum(self.findings['statistics']['line_key_summary'].values())
            print(f"{Colors.BOLD}Line Keys Configured:{Colors.RESET} {total_keys}")
            
            # Show breakdown
            summary = self.findings['statistics']['line_key_summary']
            breakdown = []
            if summary.get('Line'): breakdown.append(f"{summary['Line']} Line")
            if summary.get('SpeedDial'): breakdown.append(f"{summary['SpeedDial']} Speed Dial")
            if summary.get('BLF'): breakdown.append(f"{summary['BLF']} BLF")
            if breakdown:
                print(f"  └─ {', '.join(breakdown)}")
        
        # Attendant resources insight
        if self.findings.get('attendant_resources'):
            resources = self.findings['attendant_resources']
            print(f"\n{Colors.BOLD}Attendant Console:{Colors.RESET} Monitoring {len(resources)} extensions")
            
            # Check for remote/cell phones
            remote_exts = [r for r in resources if any(x in r['label'].lower() for x in ['cell', 'home', 'mobile'])]
            if remote_exts:
                print(f"  └─ Includes {len(remote_exts)} remote/cell numbers (hybrid setup)")
            
            # Check for special extensions
            special = [r for r in resources if any(x in r['label'].lower() for x in ['open', 'paging', 'conference', 'lab'])]
            if special:
                print(f"  └─ Special extensions: {', '.join([r['label'] for r in special[:3]])}")
        
        # Provisioning status
        if self.findings.get('provisioning') and self.findings['provisioning'].get('server'):
            prov = self.findings['provisioning']
            security_status = "✓ Secure" if prov['type'] == 'HTTPS' else "⚠ Insecure"
            print(f"\n{Colors.BOLD}Provisioning:{Colors.RESET} {prov['type']} from {prov['server']} ({security_status})")
        
        # Security summary
        critical_issues = [i for i in self.findings['security_issues'] if i['severity'] == 'CRITICAL']
        high_issues = [i for i in self.findings['security_issues'] if i['severity'] == 'HIGH']
        medium_issues = [i for i in self.findings['security_issues'] if i['severity'] == 'MEDIUM']
        
        print(f"\n{Colors.BOLD}Security Status:{Colors.RESET}")
        if not self.findings['security_issues']:
            print(f"  {Colors.GREEN}✓ No issues detected (passwords properly excluded){Colors.RESET}")
        else:
            if critical_issues:
                print(f"  {Colors.RED}✗ {len(critical_issues)} CRITICAL issue(s) - immediate action required{Colors.RESET}")
            if high_issues:
                print(f"  {Colors.YELLOW}⚠ {len(high_issues)} HIGH severity issue(s){Colors.RESET}")
            if medium_issues:
                print(f"  {Colors.YELLOW}⚠ {len(medium_issues)} MEDIUM severity issue(s){Colors.RESET}")
        
        # Feature compliance
        enabled_features = [f for f, v in self.findings['feature_status'].items() if v == '1']
        disabled_features = [f for f, v in self.findings['feature_status'].items() if v == '0']
        
        if enabled_features or disabled_features:
            print(f"\n{Colors.BOLD}Feature Status:{Colors.RESET}")
            if enabled_features:
                print(f"  {Colors.GREEN}✓ {len(enabled_features)} enabled{Colors.RESET}: {', '.join(enabled_features[:3])}")
                if len(enabled_features) > 3:
                    print(f"    and {len(enabled_features) - 3} more...")
            if disabled_features:
                print(f"  {Colors.YELLOW}⚠ {len(disabled_features)} disabled{Colors.RESET}: {', '.join(disabled_features[:3])}")
        
        # Custom softkeys
        if self.findings['softkeys']:
            softkey_labels = [sk['label'] for sk in self.findings['softkeys'] if sk['label']]
            if softkey_labels:
                print(f"\n{Colors.BOLD}Custom Softkeys:{Colors.RESET} {', '.join(softkey_labels)}")
        
        # Notable configurations
        print(f"\n{Colors.BOLD}Notable Configuration:{Colors.RESET}")
        
        # Check for DNS configuration
        dns_primary = self.config_data.get('device.dns.serverAddress', '')
        dns_alt = self.config_data.get('device.dns.altSrvAddress', '')
        if dns_primary or dns_alt:
            dns_servers = [s for s in [dns_primary, dns_alt] if s]
            print(f"  • DNS configured: {', '.join(dns_servers)}")
        
        # Check for VLAN
        vlan = self.findings['network_config'].get('vlan_id', 'none')
        if vlan != 'none' and vlan:
            print(f"  • VLAN tagging: {vlan}")
        else:
            print(f"  • {Colors.YELLOW}VLAN not configured (consider for voice traffic separation){Colors.RESET}")
        
        # Check for QoS
        qos = self.findings['network_config'].get('qos_enabled', '0')
        if qos == '1':
            print(f"  • QoS/DSCP enabled for call quality")
        
        # Check timezone
        tz_offset = self.findings['network_config'].get('time_zone', '0')
        if tz_offset == '-18000':
            print(f"  • Timezone: EST/EDT (UTC-5)")
        elif tz_offset != '0':
            hours = int(tz_offset) / 3600
            print(f"  • Timezone: UTC{hours:+.0f}")
        
        # Recommendations
        recommendations = []
        
        if not self.findings['security_issues'] and not critical_issues and not high_issues:
            recommendations.append("Configuration is secure ✓")
        
        if vlan == 'none' or not vlan:
            recommendations.append("Consider VLAN tagging for voice traffic")
        
        if qos != '1':
            recommendations.append("Enable QoS/DSCP for improved call quality")
        
        if disabled_features:
            if 'Paging' in disabled_features:
                recommendations.append("Consider enabling Paging if overhead system exists")
        
        if recommendations:
            print(f"\n{Colors.BOLD}Recommendations:{Colors.RESET}")
            for rec in recommendations[:3]:
                print(f"  • {rec}")
    
    def determine_phone_role(self):
        """Determine the role/type of phone based on configuration"""
        attendant_count = len(self.findings.get('attendant_resources', []))
        blf_count = self.findings.get('statistics', {}).get('line_key_summary', {}).get('BLF', 0)
        speed_dial_count = self.findings.get('statistics', {}).get('line_key_summary', {}).get('BLF', 0)
        
        if attendant_count > 15:
            # Check for remote numbers
            has_remote = any('cell' in r['label'].lower() or 'home' in r['label'].lower() 
                           for r in self.findings.get('attendant_resources', []))
            if has_remote:
                return f"{Colors.MAGENTA}Receptionist Console (Hybrid Office/Remote){Colors.RESET}"
            else:
                return f"{Colors.MAGENTA}Receptionist Console (Heavy Monitoring){Colors.RESET}"
        elif attendant_count > 5:
            return f"{Colors.CYAN}Receptionist Console{Colors.RESET}"
        elif blf_count > 50:
            return f"{Colors.CYAN}Executive/Manager Phone (Heavy BLF){Colors.RESET}"
        elif blf_count > 20:
            return f"{Colors.BLUE}Power User Phone (BLF enabled){Colors.RESET}"
        elif speed_dial_count > 10:
            return f"{Colors.BLUE}Power User Phone (Speed Dial focus){Colors.RESET}"
        else:
            return f"{Colors.WHITE}Standard User Phone{Colors.RESET}"
    
    def export_json(self, output_path: Path):
        """Export findings to JSON"""
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'phone_type': self.phone_type,
            'findings': self.findings,
            'config_count': len(self.config_data)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"{Colors.GREEN}✓ JSON report saved: {output_path}{Colors.RESET}")
    
    def export_csv_summary(self, output_path: Path):
        """Export summary to CSV"""
        import csv
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Category', 'Item', 'Value', 'Status'])
            
            # SIP Accounts
            for account in self.findings['sip_accounts']:
                writer.writerow(['SIP Account', f"Line {account['line']}", account['address'], 'Active'])
            
            # Security Issues
            for issue in self.findings['security_issues']:
                writer.writerow(['Security', issue['issue'], issue['detail'], issue['severity']])
            
            # Features
            for feature, enabled in self.findings['feature_status'].items():
                status = 'Enabled' if enabled == '1' else 'Disabled'
                writer.writerow(['Feature', feature, '', status])
        
        print(f"{Colors.GREEN}✓ CSV summary saved: {output_path}{Colors.RESET}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Analyze VoIP phone configuration files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s phone_config.xml
  %(prog)s --json output.json --csv summary.csv config.cfg
  %(prog)s --directory ./configs/
  
Supported phone types:
  - Polycom VVX/SoundPoint (.xml, .cfg)
  - Yealink T4x/T5x (.cfg)
  - Cisco SPA (.xml)
  - Grandstream GXP (.cfg)
  - Sangoma (.conf)
        """
    )
    
    parser.add_argument(
        'config_file',
        nargs='?',
        type=Path,
        help='Phone configuration file to analyze'
    )
    
    parser.add_argument(
        '--directory', '-d',
        type=Path,
        help='Analyze all config files in directory'
    )
    
    parser.add_argument(
        '--json',
        type=Path,
        help='Export findings to JSON file'
    )
    
    parser.add_argument(
        '--csv',
        type=Path,
        help='Export summary to CSV file'
    )
    
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    args = parser.parse_args()
    
    if args.no_color:
        # Disable colors
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')
    
    # Determine files to analyze
    config_files = []
    
    if args.directory:
        if not args.directory.is_dir():
            print(f"Error: {args.directory} is not a directory")
            return 1
        
        # Find all config files
        patterns = ['*.xml', '*.cfg', '*.conf', '*.txt']
        for pattern in patterns:
            config_files.extend(args.directory.glob(pattern))
        
        if not config_files:
            print(f"Error: No configuration files found in {args.directory}")
            return 1
        
        print(f"Found {len(config_files)} configuration files")
    
    elif args.config_file:
        if not args.config_file.exists():
            print(f"Error: File not found: {args.config_file}")
            return 1
        config_files = [args.config_file]
    
    else:
        parser.print_help()
        return 1
    
    # Analyze each file
    for config_file in config_files:
        analyzer = PhoneConfigAnalyzer()
        
        try:
            analyzer.analyze_all(config_file)
            analyzer.print_report()
            
            # Export if requested
            if args.json:
                json_path = args.json if len(config_files) == 1 else \
                           args.json.parent / f"{config_file.stem}_{args.json.name}"
                analyzer.export_json(json_path)
            
            if args.csv:
                csv_path = args.csv if len(config_files) == 1 else \
                          args.csv.parent / f"{config_file.stem}_{args.csv.name}"
                analyzer.export_csv_summary(csv_path)
        
        except Exception as e:
            print(f"{Colors.RED}Error analyzing {config_file}: {e}{Colors.RESET}")
            import traceback
            traceback.print_exc()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
