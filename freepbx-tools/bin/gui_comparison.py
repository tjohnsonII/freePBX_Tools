#!/usr/bin/env python3
"""
FreePBX GUI vs CLI Comparison Tool
----------------------------------
Extract data from FreePBX web interface and compare with our tool

VARIABLE MAP (Key Script Variables)
-----------------------------------
FreePBXGUIComparator : Main class for GUI/CLI comparison
base_url      : Base URL of FreePBX web interface
username      : Web interface username
password      : Web interface password
session       : Requests session for HTTP calls
HAS_BS4       : Boolean, True if BeautifulSoup4 is available
args          : Parsed command-line arguments (if any)
cli_data      : Data extracted from CLI tool
gui_data      : Data extracted from GUI scraping

Key Function Arguments:
-----------------------
url           : URL to fetch
data          : Data to compare
args          : Parsed command-line arguments

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    FreePBXGUIComparator.__init__    : Initialize comparator with credentials
    FreePBXGUIComparator.login       : Login to FreePBX web interface
    FreePBXGUIComparator.fetch_page  : Fetch a page from the web interface
    FreePBXGUIComparator.extract_data: Extract relevant data from GUI
    compare_data                     : Compare CLI and GUI data
    main                             : CLI entry point, parses args and runs comparison
"""

import requests
import json
import re
import subprocess

# Optional import for BeautifulSoup - graceful fallback if not available
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("Warning: BeautifulSoup4 not available. Install with: pip3 install beautifulsoup4")
    print("GUI comparison features will be limited without BeautifulSoup4.")

class FreePBXGUIComparator:
    def __init__(self, base_url, username="admin", password="admin"):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        
    def login(self):
        """Login to FreePBX web interface"""
        if not HAS_BS4:
            print("Error: BeautifulSoup4 required for GUI login. Install with: pip3 install beautifulsoup4")
            return False
            
        login_url = f"{self.base_url}/admin/index.php"
        
        # Get login page first
        response = self.session.get(login_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find CSRF token if present
        csrf_token = None
        csrf_input = soup.find('input', {'name': 'token'})
        if csrf_input:
            csrf_token = str(csrf_input.get('value', ''))
        
        # Login
        login_data = {
            'username': self.username,
            'password': self.password,
        }
        if csrf_token:
            login_data['token'] = csrf_token
            
        response = self.session.post(login_url, data=login_data)
        return "welcome" in response.text.lower() or "dashboard" in response.text.lower()
    
    def get_inbound_routes(self):
        """Extract inbound routes from GUI"""
        if not HAS_BS4:
            print("Error: BeautifulSoup4 required for HTML parsing. Install with: pip3 install beautifulsoup4")
            return []
            
        url = f"{self.base_url}/admin/config.php?display=incoming"
        response = self.session.get(url)
        
        # Parse the inbound routes table
        soup = BeautifulSoup(response.content, 'html.parser')
        routes = []
        
        # Look for routes table (structure varies by FreePBX version)
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip header
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    did = cells[0].get_text(strip=True)
                    description = cells[1].get_text(strip=True)
                    destination = cells[2].get_text(strip=True)
                    
                    if did and did != 'DID':  # Skip headers
                        routes.append({
                            'did': did,
                            'description': description,
                            'destination': destination
                        })
        
        return routes
    
    def compare_with_tool(self, did):
        """Compare GUI data with our tool output"""
        print(f"\n🔍 GUI vs TOOL COMPARISON: {did}")
        print("=" * 50)
        
        # Get GUI data
        gui_routes = self.get_inbound_routes()
        gui_route = None
        for route in gui_routes:
            if route['did'] == did:
                gui_route = route
                break
        
        if not gui_route:
            print(f"❌ DID {did} not found in GUI")
            return False
        
        print(f"🌐 GUI DATA:")
        print(f"   DID: {gui_route['did']}")
        print(f"   Description: {gui_route['description']}")
        print(f"   Destination: {gui_route['destination']}")
        
        # Get tool data
        cmd = ["python", "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py", "--did", str(did)]
        try:
            tool_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback for different Python command or missing file
            try:
                cmd = ["python3", "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py", "--did", str(did)]
                tool_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"❌ Could not execute call flow tool for DID {did}")
                return False
        
        tool_description = ""
        tool_destination = ""
        
        for line in tool_result.stdout.split('\n'):
            if "✓ Found route:" in line:
                tool_description = line.split("✓ Found route: ")[1].strip()
            elif "✓ Destination:" in line:
                tool_destination = line.split("✓ Destination: ")[1].strip()
        
        print(f"🔧 TOOL DATA:")
        print(f"   Description: {tool_description}")
        print(f"   Destination: {tool_destination}")
        
        # Compare
        desc_match = gui_route['description'] == tool_description
        dest_match = gui_route['destination'] in tool_destination or tool_destination in gui_route['destination']
        
        print(f"\n✅ COMPARISON:")
        print(f"   Description Match: {'✓' if desc_match else '❌'}")
        print(f"   Destination Match: {'✓' if dest_match else '❌'}")
        
        if not desc_match:
            print(f"   ⚠️  Description: GUI='{gui_route['description']}' vs Tool='{tool_description}'")
        if not dest_match:
            print(f"   ⚠️  Destination: GUI='{gui_route['destination']}' vs Tool='{tool_destination}'")
        
        return desc_match and dest_match

# Usage example:
# comparator = FreePBXGUIComparator("http://205.251.183.48", "admin", "password")
# if comparator.login():
#     comparator.compare_with_tool("2485815200")

# Requirements:
# pip3 install beautifulsoup4 requests
# 
# Or run the installer which will attempt to install these automatically:
# sudo ./install.sh