#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
find_chrome_cookies():
    Locate the Chrome cookies SQLite file on the local system.
extract_cookies_from_chrome(domain="secure.123.net"):
    Extract cookies for a given domain from Chrome's cookie store.
manual_cookie_entry():
    Prompt user for manual cookie entry if extraction fails.
main():
    Orchestrate cookie extraction and saving to file.
"""
"""
Browser Cookie Extractor for Windows
Extracts cookies from Chrome/Edge for secure.123.net
"""

import json
import sqlite3
import os
from pathlib import Path
import shutil
import sys

def find_chrome_cookies():
    """Find Chrome cookies database"""
    appdata = os.getenv('LOCALAPPDATA')
    if not appdata:
        return None
    
    chrome_path = Path(appdata) / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Network' / 'Cookies'
    
    if chrome_path.exists():
        return chrome_path
    
    # Try Edge
    edge_path = Path(appdata) / 'Microsoft' / 'Edge' / 'User Data' / 'Default' / 'Network' / 'Cookies'
    if edge_path.exists():
        return edge_path
    
    return None

def extract_cookies_from_chrome(domain="secure.123.net"):
    """Extract cookies from Chrome/Edge"""
    cookies_db = find_chrome_cookies()
    
    if not cookies_db:
        print("❌ Could not find Chrome/Edge cookies database")
        return None
    
    # Copy database (can't read while browser is using it)
    temp_db = Path("temp_cookies.db")
    try:
        shutil.copy2(cookies_db, temp_db)
    except Exception as e:
        print(f"❌ Could not copy cookies database: {e}")
        print("   Close your browser and try again")
        return None
    
    # Read cookies
    try:
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT name, value, encrypted_value 
            FROM cookies 
            WHERE host_key LIKE ?
        ''', (f'%{domain}%',))
        
        cookies = {}
        for name, value, encrypted_value in cursor.fetchall():
            # Note: encrypted_value needs decryption (requires Windows DPAPI)
            # For now, just use unencrypted values if available
            if value:
                cookies[name] = value
        
        conn.close()
        temp_db.unlink()
        
        return cookies if cookies else None
        
    except Exception as e:
        print(f"❌ Error reading cookies: {e}")
        if temp_db.exists():
            temp_db.unlink()
        return None

def manual_cookie_entry():
    """Manually enter cookies"""
    print("\n" + "="*60)
    print("MANUAL COOKIE ENTRY")
    print("="*60)
    print("\nIn your browser (while logged into secure.123.net):")
    print("1. Press F12 (Developer Tools)")
    print("2. Go to Console tab")
    print("3. Paste this and press Enter:")
    print("\n   document.cookie\n")
    print("4. Copy the output")
    print("="*60 + "\n")
    
    cookie_string = input("Paste the cookie string here: ").strip()
    
    if not cookie_string:
        return None
    
    # Parse cookie string
    cookies = {}
    for cookie in cookie_string.split('; '):
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            cookies[name] = value
    
    return cookies if cookies else None

def main():
    print("\n" + "="*60)
    print("123.NET COOKIE EXTRACTOR")
    print("="*60)
    
    print("\nAttempting automatic extraction from Chrome/Edge...")
    
    cookies = extract_cookies_from_chrome()
    
    if not cookies:
        print("\n⚠️  Automatic extraction failed")
        print("\nOptions:")
        print("  1. Manual entry")
        print("  2. Cancel")
        
        choice = input("\nChoice (1 or 2): ").strip()
        
        if choice == '1':
            cookies = manual_cookie_entry()
        else:
            print("Cancelled")
            return 1
    
    if not cookies:
        print("\n❌ No cookies extracted")
        return 1
    
    print(f"\n✅ Extracted {len(cookies)} cookies:")
    for name in cookies.keys():
        print(f"   - {name}")
    
    # Save to file
    output_file = Path("cookies.json")
    with open(output_file, 'w') as f:
        json.dump(cookies, f, indent=2)
    
    print(f"\n✅ Saved to: {output_file}")
    print("\nNow you can run:")
    print("  python ticket_scraper_session.py --customer CUSTOMER --cookie-file cookies.json")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
