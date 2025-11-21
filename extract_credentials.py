#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
extract_credentials(html_file):
    Extract credentials (usernames, passwords) from an HTML file.
main():
    Orchestrate extraction and output of credentials from CLI.
"""
"""
Extract and display server credentials from scraped VPBX data
"""

import re
import sys
from pathlib import Path

def extract_credentials(html_file):
    """Extract server credentials from detail_main.html"""
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    patterns = {
        'System IP': r'name="ip"\s+value="([^"]+)"',
        'FTP Host': r'name="ftp_host"\s+value="([^"]+)"',
        'FTP User': r'name="ftp_user"\s+value="([^"]+)"',
        'FTP Password': r'name="ftp_pass"\s+value="([^"]+)"',
        'REST User': r'name="rest_user"\s+value="([^"]+)"',
        'REST Password': r'name="rest_pass"\s+value="([^"]+)"',
        'FreePBX Version': r'name="freepbx_version"\s+value="([^"]+)"',
        'Asterisk Version': r'name="asterisk_version"\s+value="([^"]+)"',
        'VM ID': r'name="vmName"\s+value="([^"]+)"',
        'Deployment ID': r'name="deployment_id"\s+value="([^"]+)"',
        'Handle': r'name="handle"\s+value="([^"]+)"',
        'Company': r'name="cname"\s+value="([^"]+)"',
        'Call Center': r'name="asternic"\s+value="([^"]+)"',
    }
    
    credentials = {}
    for label, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            credentials[label] = match.group(1)
    
    return credentials

def main():
    data_dir = Path('c:/freepbx-tools/freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive')
    
    # Check both test entries
    for entry_dir in sorted(data_dir.glob('entry_*')):
        html_file = entry_dir / 'detail_main.html'
        
        if not html_file.exists():
            continue
        
        creds = extract_credentials(html_file)
        
        if not creds:
            continue
        
        site_id = entry_dir.name.replace('entry_', '')
        print('=' * 80)
        print(f"SITE {site_id} - {creds.get('Handle', 'N/A')} - {creds.get('Company', 'N/A')}")
        print('=' * 80)
        print()
        
        print("SERVER ACCESS:")
        print(f"  System IP      : {creds.get('System IP', 'N/A')}")
        print(f"  VM ID          : {creds.get('VM ID', 'N/A')}")
        print(f"  Deployment ID  : {creds.get('Deployment ID', 'N/A')}")
        print()
        
        print("FTP ACCESS:")
        print(f"  FTP Host       : {creds.get('FTP Host', 'N/A')}")
        print(f"  FTP User       : {creds.get('FTP User', 'N/A')}")
        pwd = creds.get('FTP Password', 'N/A')
        print(f"  FTP Password   : {pwd}")
        print(f"  Note: FTP user is username for SSH (123net user)")
        print()
        
        print("REST API ACCESS:")
        print(f"  REST User      : {creds.get('REST User', 'N/A')}")
        rest_pwd = creds.get('REST Password', 'N/A')
        print(f"  REST Password  : {rest_pwd}")
        print()
        
        print("VERSIONS:")
        print(f"  FreePBX        : {creds.get('FreePBX Version', 'N/A')}")
        print(f"  Asterisk       : {creds.get('Asterisk Version', 'N/A')}")
        
        # Check if Asternic Call Center 2 is installed
        call_center = creds.get('Call Center', '')
        if call_center:
            print(f"  Call Center    : Asternic Call Center 2 (INSTALLED)")
        else:
            print(f"  Call Center    : Not installed")
        print()
        
        print("PLATFORM: FreePBX (Not Fusion or 123NET UC)")
        print()

if __name__ == '__main__':
    main()
