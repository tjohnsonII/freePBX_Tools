#!/usr/bin/env python3
"""
123NET Ticket Scraper - Session-Based Version
---------------------------------------------
This script scrapes support tickets from 123NET using an existing browser session (cookies).
It allows authentication via cookies exported from a browser, avoiding the need to store credentials in the script.

Key Features:
- Uses browser session cookies for authentication
- Fetches ticket lists and details for a customer
- Supports interactive or file-based cookie entry
- Outputs all ticket data to JSON for later analysis

Author: 123NET Team

====================================
Variable Map Legend (Key Variables)
====================================

Global/Script Arguments:
-----------------------
args.customer (str): Customer handle to fetch tickets for
args.cookie_file (str): Path to JSON file with cookies
args.interactive (bool): Whether to prompt for cookies interactively
args.test_only (bool): Only test authentication, do not scrape
args.output (str): Output directory for JSON results

SessionTicketScraper Class:
--------------------------
self.base_url (str): Base URL for 123NET admin portal
self.session (requests.Session): Persistent HTTP session with cookies

get_customer_tickets():
    customer_handle (str): Customer identifier
    tickets (list[dict]): List of ticket metadata dicts

get_ticket_details():
    ticket_id (str): Ticket identifier
    ticket_url (str): Optional direct URL to ticket
    details (dict): Full ticket details and messages

test_authentication():
    test_url (str): URL used to verify authentication

extract_cookies_from_browser():
    cookies (dict): Dictionary of cookie name/value pairs

Other:
------
cookies (dict): Cookies loaded from file or entered interactively
tickets (list[dict]): List of tickets for customer
detailed_tickets (list[dict]): List of tickets with full details
output_dir (Path): Output directory as pathlib.Path
output_file (Path): Output JSON file path
full_ticket (dict): Merged ticket info and details
"""

import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, List, Any, Optional
import sqlite3
from datetime import datetime
from pathlib import Path
import time
import re
import argparse

class SessionTicketScraper:
    """Ticket scraper that uses existing session cookies"""
    
    def __init__(self, session_cookies: Optional[Dict[str, str]] = None, base_url="https://secure.123.net"):
        self.base_url = base_url
        self.session = requests.Session()
        
        if session_cookies:
            for name, value in session_cookies.items():
                self.session.cookies.set(name, value)
        
        print(f"✅ Session initialized with {len(self.session.cookies)} cookies")
    
    def set_cookie(self, name: str, value: str):
        """Add a cookie to the session"""
        self.session.cookies.set(name, value)
    
    def test_authentication(self):
        """
        Test if the session is authenticated by accessing a protected page.
        Returns True if authenticated, False otherwise.
        """
        test_url = f"{self.base_url}/cgi-bin/web_interface/admin/customers.cgi"
        response = self.session.get(test_url)
        # Check if redirected to login
        if 'login' in response.url.lower():
            print("❌ Session not authenticated - redirected to login")
            return False
        if response.status_code == 200:
            print("✅ Session authenticated successfully")
            return True
        else:
            print(f"⚠️  Unexpected response: {response.status_code}")
            return False
    
    def get_customer_tickets(self, customer_handle):
        """Get all tickets for a customer using existing session"""
        tickets_url = f"{self.base_url}/cgi-bin/web_interface/admin/customers.cgi"
        
        params = {
            'customer_handle': customer_handle,
            'action': 'view_tickets'
        }
        
        response = self.session.get(tickets_url, params=params)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch tickets: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        tickets = []
        
        # Find the table with "Ticket ID" header
        table = None
        for t in soup.find_all('table'):
            headers = t.find_all('th')
            if any('Ticket ID' in h.get_text() for h in headers):
                table = t
                break
        
        if not table:
            print("⚠️  No ticket table found")
            return []
        
        # Parse tickets
        rows = table.find_all('tr')[1:]  # Skip header
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 5:
                # Find ticket link
                link = cells[0].find('a')
                if link and link.get('href'):
                    ticket_url = link['href']
                    ticket_id = link.get_text().strip()
                    
                    tickets.append({
                        'ticket_id': ticket_id,
                        'ticket_url': ticket_url,
                        'subject': cells[1].get_text().strip(),
                        'status': cells[2].get_text().strip(),
                        'priority': cells[3].get_text().strip(),
                        'created': cells[4].get_text().strip()
                    })
        
        print(f"📥 Found {len(tickets)} tickets for {customer_handle}")
        return tickets
    
    def get_ticket_details(self, ticket_id, ticket_url=''):
        """Get full details for a specific ticket"""
        if not ticket_url:
            ticket_url = f"{self.base_url}/cgi-bin/web_interface/new_tickets.cgi?id=ticket/{ticket_id}"
        elif not ticket_url.startswith('http'):
            ticket_url = f"{self.base_url}{ticket_url}"
        
        response = self.session.get(ticket_url)
        
        if response.status_code != 200:
            print(f"⚠️  Failed to fetch ticket {ticket_id}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        details = {
            'ticket_id': ticket_id,
            'subject': '',
            'status': '',
            'priority': '',
            'created_date': '',
            'resolved_date': '',
            'messages': [],
            'resolution': ''
        }
        
        # Extract metadata from tables
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    label = cells[0].get_text().strip().lower()
                    value = cells[1].get_text().strip()
                    
                    if 'subject' in label:
                        details['subject'] = value
                    elif 'status' in label:
                        details['status'] = value
                    elif 'priority' in label:
                        details['priority'] = value
                    elif 'created' in label:
                        details['created_date'] = value
                    elif 'resolved' in label or 'closed' in label:
                        details['resolved_date'] = value
        
        # Extract messages/conversation
        message_divs = soup.find_all('div', class_='message')
        if not message_divs:
            message_divs = soup.find_all('div', class_='ticket-message')
        
        for msg in message_divs:
            author_elem = msg.find('span', class_='author')
            timestamp_elem = msg.find('span', class_='timestamp')
            content_elem = msg.find('div', class_='content')
            
            message = {
                'author': author_elem.text if author_elem else 'Unknown',
                'timestamp': timestamp_elem.text if timestamp_elem else '',
                'content': content_elem.text.strip() if content_elem else msg.get_text().strip()
            }
            
            details['messages'].append(message)
            
            # Check for resolution
            if 'resolved' in message['content'].lower() or 'fixed' in message['content'].lower():
                details['resolution'] = message['content']
        
        return details


def extract_cookies_from_browser():
    """
    Helper function to extract cookies from browser
    You'll need to provide cookies manually or use browser automation
    """
    print("\n" + "="*60)
    print("COOKIE EXTRACTION GUIDE")
    print("="*60)
    print("\n1. Open your browser and go to secure.123.net")
    print("2. Make sure you're logged in")
    print("3. Open Developer Tools (F12)")
    print("4. Go to Application/Storage tab")
    print("5. Click on Cookies -> secure.123.net")
    print("6. Copy the cookie values")
    print("\nCommon cookie names:")
    print("  - session_id")
    print("  - auth_token")
    print("  - PHPSESSID")
    print("  - remember_token")
    print("\n" + "="*60)
    
    cookies = {}
    
    print("\nEnter cookies (press Enter with empty name to finish):")
    while True:
        name = input("Cookie name: ").strip()
        if not name:
            break
        value = input("Cookie value: ").strip()
        if value:
            cookies[name] = value
    
    return cookies


def main():
    parser = argparse.ArgumentParser(
        description='Scrape 123.NET tickets using existing browser session'
    )
    parser.add_argument('--customer', required=True, help='Customer handle')
    parser.add_argument('--cookie-file', help='JSON file with cookies')
    parser.add_argument('--interactive', action='store_true', 
                       help='Manually enter cookies')
    parser.add_argument('--test-only', action='store_true',
                       help='Only test authentication, don\'t scrape')
    parser.add_argument('--output', default='knowledge_base', 
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Get cookies
    cookies = {}
    
    if args.cookie_file:
        # Load from file
        with open(args.cookie_file, 'r') as f:
            cookies = json.load(f)
        print(f"✅ Loaded {len(cookies)} cookies from {args.cookie_file}")
    
    elif args.interactive:
        # Interactive entry
        cookies = extract_cookies_from_browser()
    
    else:
        print("❌ Please provide cookies using --cookie-file or --interactive")
        print("\nTo create a cookie file:")
        print("  1. Export cookies from browser")
        print("  2. Save as JSON: {'cookie_name': 'cookie_value', ...}")
        print("  3. Use: --cookie-file cookies.json")
        return 1
    
    # Initialize scraper
    scraper = SessionTicketScraper(cookies)
    
    # Test authentication
    if not scraper.test_authentication():
        print("\n❌ Authentication failed!")
        print("\nTroubleshooting:")
        print("  1. Make sure you're logged in to secure.123.net in your browser")
        print("  2. Copy fresh cookies (they may expire)")
        print("  3. Check cookie names are correct")
        return 1
    
    if args.test_only:
        print("\n✅ Authentication test passed!")
        return 0
    
    # Scrape tickets
    print(f"\n📥 Fetching tickets for customer: {args.customer}")
    tickets = scraper.get_customer_tickets(args.customer)
    
    if not tickets:
        print("⚠️  No tickets found")
        return 0
    
    # Get full details for each ticket
    print("\n🔍 Fetching ticket details...")
    detailed_tickets = []
    
    for i, ticket in enumerate(tickets, 1):
        print(f"  [{i}/{len(tickets)}] Processing ticket {ticket['ticket_id']}...")
        details = scraper.get_ticket_details(
            ticket['ticket_id'],
            ticket.get('ticket_url', '')
        )
        
        # Merge basic info with details
        full_ticket = {**ticket, **details}
        detailed_tickets.append(full_ticket)
        
        time.sleep(0.5)  # Be polite
    
    # Save to JSON
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"{args.customer}_tickets_session.json"
    with open(output_file, 'w') as f:
        json.dump(detailed_tickets, f, indent=2, default=str)
    
    print(f"\n✅ Saved {len(detailed_tickets)} tickets to: {output_file}")
    print(f"\n💡 Next step: Import into knowledge base")
    print(f"   python ticket_scraper.py --customer {args.customer} ...")
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
