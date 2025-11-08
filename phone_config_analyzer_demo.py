#!/usr/bin/env python3
"""
Phone Config Analyzer - Demo Script
Demonstrates various capabilities and use cases
"""

import sys
from pathlib import Path
from phone_config_analyzer import PhoneConfigAnalyzer, Colors

def demo_basic_analysis():
    """Demo 1: Basic config analysis"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 1: Basic Configuration Analysis{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    config_file = Path('freepbx-tools/bin/123net_internal_docs/CSU_VVX600.cfg')
    
    if not config_file.exists():
        print(f"{Colors.RED}Error: Sample config not found{Colors.RESET}")
        return
    
    analyzer = PhoneConfigAnalyzer()
    findings = analyzer.analyze_all(config_file)
    analyzer.print_report()
    
    return findings

def demo_security_check(findings):
    """Demo 2: Security compliance checking"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 2: Security Compliance Check{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    if not findings:
        print(f"{Colors.YELLOW}No findings to analyze{Colors.RESET}")
        return
    
    # Count by severity
    severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    
    for issue in findings['security_issues']:
        severity = issue['severity']
        severity_counts[severity] += 1
    
    # Print summary
    print(f"{Colors.BOLD}Security Issue Summary:{Colors.RESET}\n")
    
    for severity, count in severity_counts.items():
        if count > 0:
            color = Colors.RED if severity == 'CRITICAL' else \
                   Colors.YELLOW if severity in ['HIGH', 'MEDIUM'] else Colors.WHITE
            print(f"  {color}{severity:10}{Colors.RESET} {count:3} issues")
    
    # Compliance status
    critical_count = severity_counts['CRITICAL']
    high_count = severity_counts['HIGH']
    
    print()
    if critical_count == 0 and high_count == 0:
        print(f"{Colors.GREEN}✓ COMPLIANT{Colors.RESET} - No critical or high severity issues")
    elif critical_count > 0:
        print(f"{Colors.RED}✗ NON-COMPLIANT{Colors.RESET} - {critical_count} critical issues require immediate attention")
    else:
        print(f"{Colors.YELLOW}⚠ WARNING{Colors.RESET} - {high_count} high severity issues should be addressed")
    
    print()

def demo_sip_account_extraction(findings):
    """Demo 3: SIP account information extraction"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 3: SIP Account Extraction{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    if not findings or not findings.get('sip_accounts'):
        print(f"{Colors.YELLOW}No SIP accounts found{Colors.RESET}")
        return
    
    print(f"{Colors.BOLD}Extracting SIP credentials for provisioning database...{Colors.RESET}\n")
    
    for account in findings['sip_accounts']:
        if account['address']:  # Only show configured accounts
            print(f"Extension: {Colors.GREEN}{account['address']}{Colors.RESET}")
            print(f"  User ID:      {account['user_id']}")
            print(f"  Display Name: {account['display_name']}")
            print(f"  SIP Server:   {account['server']}")
            print(f"  Label:        {account['label']}")
            print(f"  Password Set: {'Yes' if account['password_set'] == '1' else 'No'}")
            print()

def demo_line_key_analysis(findings):
    """Demo 4: Line key configuration analysis"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 4: Line Key Configuration Analysis{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    if not findings or not findings.get('line_keys'):
        print(f"{Colors.YELLOW}No line keys configured{Colors.RESET}")
        return
    
    # Categorize line keys
    by_category = {}
    for lk in findings['line_keys']:
        category = lk['category']
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(lk)
    
    # Show summary
    print(f"{Colors.BOLD}Line Key Distribution:{Colors.RESET}\n")
    
    for category, keys in sorted(by_category.items()):
        print(f"  {Colors.CYAN}{category:15}{Colors.RESET} {len(keys):3} keys")
        
        # Show first few of each type
        if len(keys) <= 5:
            for lk in keys:
                label = lk.get('label', '')
                if label:
                    print(f"    Key {lk['key']:2}: {label}")
        else:
            print(f"    Keys {keys[0]['key']}-{keys[-1]['key']}")
    
    print()
    
    # Calculate utilization
    total_keys = len(findings['line_keys'])
    print(f"{Colors.BOLD}Line Key Utilization:{Colors.RESET}")
    print(f"  Configured:  {total_keys}")
    print(f"  Available:   96 (typical VVX600 with expansion modules)")
    print(f"  Utilization: {total_keys/96*100:.1f}%")
    print()

def demo_feature_compliance(findings):
    """Demo 5: Feature compliance checking"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 5: Feature Compliance Checking{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    if not findings or not findings.get('feature_status'):
        print(f"{Colors.YELLOW}No feature status available{Colors.RESET}")
        return
    
    # Required features (company policy)
    required_features = {
        'Presence': 'Enable BLF/presence for line monitoring',
        'Paging': 'Support overhead paging system',
        'Volume Persist (Handset)': 'Remember user volume preferences',
        'Volume Persist (Headset)': 'Remember user volume preferences',
    }
    
    print(f"{Colors.BOLD}Required Feature Compliance:{Colors.RESET}\n")
    
    all_compliant = True
    
    for feature, description in required_features.items():
        status = findings['feature_status'].get(feature, '0')
        enabled = status == '1'
        
        if enabled:
            print(f"  {Colors.GREEN}✓{Colors.RESET} {feature:30} {Colors.GREEN}Enabled{Colors.RESET}")
        else:
            print(f"  {Colors.RED}✗{Colors.RESET} {feature:30} {Colors.RED}Disabled{Colors.RESET}")
            print(f"    → {description}")
            all_compliant = False
    
    print()
    if all_compliant:
        print(f"{Colors.GREEN}✓ All required features are enabled{Colors.RESET}")
    else:
        print(f"{Colors.RED}✗ Some required features are disabled{Colors.RESET}")
    
    print()

def demo_network_audit(findings):
    """Demo 6: Network configuration audit"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 6: Network Configuration Audit{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    if not findings or not findings.get('network_config'):
        print(f"{Colors.YELLOW}No network configuration found{Colors.RESET}")
        return
    
    net = findings['network_config']
    
    print(f"{Colors.BOLD}Network Configuration Review:{Colors.RESET}\n")
    
    # Check VLAN
    vlan = net.get('vlan_id', 'none')
    if vlan == 'none' or not vlan:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} VLAN:        {Colors.YELLOW}Not configured{Colors.RESET}")
        print(f"    → Consider VLAN tagging for voice traffic separation")
    else:
        print(f"  {Colors.GREEN}✓{Colors.RESET} VLAN:        {Colors.GREEN}{vlan}{Colors.RESET}")
    
    # Check NTP
    ntp = net.get('ntp_server', '')
    if ntp:
        print(f"  {Colors.GREEN}✓{Colors.RESET} NTP Server:  {Colors.GREEN}{ntp}{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} NTP Server:  {Colors.YELLOW}Not configured{Colors.RESET}")
        print(f"    → Time synchronization required for accurate CDR")
    
    # Check Syslog
    syslog = net.get('syslog_server', '')
    if syslog:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Syslog:      {Colors.GREEN}{syslog}{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} Syslog:      {Colors.YELLOW}Not configured{Colors.RESET}")
        print(f"    → Centralized logging recommended for troubleshooting")
    
    # Check QoS
    qos = net.get('qos_enabled', '0')
    if qos == '1':
        print(f"  {Colors.GREEN}✓{Colors.RESET} QoS:         {Colors.GREEN}Enabled{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} QoS:         {Colors.YELLOW}Disabled{Colors.RESET}")
        print(f"    → QoS/DSCP tagging improves call quality")
    
    # Check LLDP
    lldp = net.get('lldp_enabled', '0')
    if lldp == '1':
        print(f"  {Colors.GREEN}✓{Colors.RESET} LLDP:        {Colors.GREEN}Enabled{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} LLDP:        {Colors.YELLOW}Disabled{Colors.RESET}")
        print(f"    → LLDP enables automatic VLAN assignment")
    
    print()

def demo_json_export():
    """Demo 7: JSON export for automation"""
    print(f"\n{Colors.CYAN}{'='*78}{Colors.RESET}")
    print(f"{Colors.BOLD}DEMO 7: JSON Export for Automation{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*78}{Colors.RESET}\n")
    
    print(f"{Colors.BOLD}Exporting analysis results to JSON...{Colors.RESET}\n")
    
    config_file = Path('freepbx-tools/bin/123net_internal_docs/CSU_VVX600.cfg')
    
    if not config_file.exists():
        print(f"{Colors.RED}Error: Sample config not found{Colors.RESET}")
        return
    
    analyzer = PhoneConfigAnalyzer()
    analyzer.analyze_all(config_file)
    
    # Export
    json_path = Path('demo_analysis.json')
    analyzer.export_json(json_path)
    
    print(f"\n{Colors.BOLD}JSON output can be used for:{Colors.RESET}")
    print(f"  • Automated compliance checking")
    print(f"  • Integration with monitoring systems")
    print(f"  • Historical tracking and trending")
    print(f"  • Bulk processing pipelines")
    print(f"  • API integrations")
    print()
    
    # Show sample code
    print(f"{Colors.BOLD}Example Python usage:{Colors.RESET}\n")
    print(f"{Colors.YELLOW}import json")
    print(f"with open('demo_analysis.json') as f:")
    print(f"    data = json.load(f)")
    print(f"")
    print(f"# Check for critical issues")
    print(f"critical = [i for i in data['findings']['security_issues']")
    print(f"            if i['severity'] == 'CRITICAL']")
    print(f"")
    print(f"if critical:")
    print(f"    alert_admin(critical){Colors.RESET}")
    print()

def main():
    """Run all demos"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                            ║")
    print("║                   Phone Configuration Analyzer Demo                       ║")
    print("║                                                                            ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")
    
    print("This demo showcases the various capabilities of the Phone Config Analyzer.")
    print("Press Enter to continue through each demo...")
    
    try:
        input()
    except:
        pass
    
    # Run demos
    findings = demo_basic_analysis()
    
    if findings:
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_security_check(findings)
        
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_sip_account_extraction(findings)
        
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_line_key_analysis(findings)
        
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_feature_compliance(findings)
        
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_network_audit(findings)
        
        try:
            input(f"\n{Colors.CYAN}Press Enter for next demo...{Colors.RESET}")
        except:
            pass
        
        demo_json_export()
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                            ║")
    print("║                         Demo Complete!                                     ║")
    print("║                                                                            ║")
    print("║  For more information, see:                                                ║")
    print("║    • PHONE_CONFIG_ANALYZER_README.md                                       ║")
    print("║    • PHONE_CONFIG_ANALYZER_QUICKREF.md                                     ║")
    print("║                                                                            ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")

if __name__ == '__main__':
    main()
