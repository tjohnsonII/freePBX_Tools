#!/usr/bin/env python3
"""
123NET Ticket Scraper and Knowledge Base Builder
------------------------------------------------
This script logs into the 123NET admin interface, scrapes all support tickets for a given customer,
and builds a structured, searchable knowledge base using SQLite. It can also export reports in JSON and Markdown.

Key Features:
- Authenticates to the admin portal
- Scrapes ticket lists and details for a customer
- Extracts ticket metadata and message history
- Categorizes and tags tickets automatically
- Stores all data in a normalized SQLite database
- Analyzes recurring issues and generates reports

Usage:
    python webscraper/legacy/ticket_scraper.py --customer <handle> --username <user> --password <pass> [--export-md]

Dependencies:
    - requests
    - beautifulsoup4
    - sqlite3 (standard library)
    - argparse (standard library)

Author: 123NET Team

====================================
Variable Map (Key Variables & Types)
====================================

Global/Script Arguments:
-----------------------
args.customer (str): Customer handle to fetch tickets for
args.username (str): Admin username for login
args.password (str): Admin password for login
args.output (str): Output directory for reports and database
args.export_md (bool): Whether to export Markdown report

TicketScraper Class:
--------------------
self.username (str): Username for authentication
self.password (str): Password for authentication
self.base_url (str): Base URL for 123NET admin portal
self.session (requests.Session): Persistent HTTP session

get_customer_tickets():
    customer_handle (str): Customer identifier
    tickets (list[dict]): List of ticket metadata dicts

get_ticket_details():
    ticket_id (str): Ticket identifier
    ticket_url (str): Optional direct URL to ticket
    ticket_data (dict): Full ticket details and messages

categorize_ticket():
    ticket (dict): Ticket data
    categories (list[str]): Assigned categories

extract_keywords():
    ticket (dict): Ticket data
    keywords (list[str]): Extracted keywords

KnowledgeBaseBuilder Class:
--------------------------
self.db_path (str): Path to SQLite database file
self.conn (sqlite3.Connection): Database connection

add_ticket():
    ticket (dict): Ticket data
    customer_handle (str): Customer identifier

analyze_patterns():
    patterns (list[tuple]): Recurring issue summary

generate_knowledge_base_report():
    customer_handle (str): Customer identifier
    report (dict): Summary report (counts, breakdowns)

export_to_markdown():
    customer_handle (str): Customer identifier
    output_file (str): Markdown file path

Other:
------
output_dir (Path): Output directory as pathlib.Path
db_path (Path): Path to SQLite DB file
tickets (list[dict]): List of tickets for customer
full_ticket (dict): Detailed ticket info
kb (KnowledgeBaseBuilder): Knowledge base manager instance
md_file (Path): Markdown report file path
json_file (Path): JSON report file path
report (dict): Final summary report
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
from typing import Dict, List, Any, Optional
import sqlite3
from datetime import datetime
from pathlib import Path
import time
import re
from collections import defaultdict
import argparse

class TicketScraper:
    """
    Handles authentication and scraping of ticket data from the 123NET admin portal.
    Provides methods to login, fetch ticket lists, fetch ticket details, categorize, and extract keywords.
    """
    def __init__(self, username, password, base_url="https://secure.123.net", cookie_file=None):
        self.username = username
        self.password = password
        self.base_url = base_url
        self.session = requests.Session()  # Maintains cookies/session state
        self.cookie_file = cookie_file

    def load_cookies(self, cookie_path: str) -> bool:
        """Load Selenium-exported cookies (list of dicts) into requests session."""
        try:
            import json
            from http.cookiejar import Cookie
            with open(cookie_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            jar = self.session.cookies
            for c in cookies:
                name = c.get("name"); value = c.get("value")
                domain = c.get("domain") or "secure.123.net"
                path = c.get("path") or "/"
                if name is None or value is None:
                    continue
                try:
                    jar.set(name, value, domain=domain, path=path)
                except Exception:
                    continue
            print(f"[OK] Loaded {len(cookies)} cookies from {cookie_path}")
            return True
        except Exception as e:
            print(f"[WARN] Could not load cookies from {cookie_path}: {e}")
            return False

    def login(self):
        """
        Login to 123NET admin interface using provided credentials.
        Returns True if login appears successful, False otherwise.
        """
        # If cookie file is provided, try cookie-based auth first
        if getattr(self, "cookie_file", None):
            try:
                if self.load_cookies(self.cookie_file):
                    # Test access to customers page
                    test_url = f"{self.base_url}/cgi-bin/web_interface/admin/customers.cgi"
                    r = self.session.get(test_url, timeout=30)
                    if r.status_code == 200 and ("Ticket" in r.text or "Customer" in r.text or "Search" in r.text):
                        print("[OK] Authenticated via injected cookies")
                        return True
                    else:
                        print(f"[WARN] Cookie auth test failed: HTTP {r.status_code}")
            except Exception as e:
                print(f"[WARN] Cookie auth error: {e}")

        login_url = f"{self.base_url}/cgi-bin/admin.cgi"
        payload = {
            'username': self.username,
            'password': self.password,
            'action': 'login'
        }
        try:
            response = self.session.post(login_url, data=payload, timeout=30)
            # Check for session cookies or redirect as evidence of successful login
            if response.status_code == 200:
                if len(self.session.cookies) > 0:
                    print(f"[OK] Successfully logged in (got {len(self.session.cookies)} cookies)")
                    return True
                elif 'admin' in response.url or 'dashboard' in response.url.lower():
                    print("[OK] Successfully logged in")
                    return True
                else:
                    print("[WARN] Login response received but authentication unclear")
                    print(f"   URL: {response.url}")
                    print(f"   Cookies: {len(self.session.cookies)}")
                    # Try to proceed anyway
                    return True
            else:
                print(f"[ERROR] Login failed with status code: {response.status_code}")
                return False
        except requests.exceptions.Timeout as e:
            print("[ERROR] Login request timed out")
            print(f"[ERROR] Login request failed: {e}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Login request failed: {e}")
            return False
    
    def get_customer_tickets(self, customer_handle):
        """
        Retrieve all tickets for a given customer handle.
        Returns a list of ticket metadata dicts (ticket_id, subject, status, etc).
        """
        tickets_url = f"{self.base_url}/cgi-bin/web_interface/admin/customers.cgi"
        params = {'customer_handle': customer_handle}
        try:
            response = self.session.get(tickets_url, params=params, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] Failed to fetch tickets: HTTP {response.status_code}")
                return []
            soup = BeautifulSoup(response.text, 'html.parser')
            tickets = []
            # Find the ticket table by searching for a table with 'Ticket ID' in the header
            tables = soup.find_all('table', {'border': '0'})
            ticket_table = None
            for table in tables:
                header_row = table.find('tr')
                if header_row and 'Ticket ID' in header_row.get_text():
                    ticket_table = table
                    break
            if not ticket_table:
                print("[WARN] No ticket table found on page")
                print(f"   This could mean:")
                print(f"   1. No tickets exist for customer '{customer_handle}'")
                print(f"   2. Customer handle is incorrect")
                print(f"   3. Not authenticated properly")
                return []
            rows = ticket_table.find_all('tr')[1:]  # Skip header row
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 5:
                    # Extract ticket ID and URL from the first column
                    ticket_link = cols[0].find('a')
                    if ticket_link:
                        ticket_id = ticket_link.text.strip()
                        ticket_url = ticket_link.get('href', '')
                    else:
                        ticket_id = cols[0].text.strip()
                        ticket_url = ''
                    subject = cols[1].text.strip()
                    status = cols[2].text.strip()
                    priority = cols[3].text.strip() if len(cols) > 3 else ''
                    created = cols[4].text.strip() if len(cols) > 4 else ''
                    tickets.append({
                        'ticket_id': ticket_id,
                        'ticket_url': ticket_url,
                        'subject': subject,
                        'status': status,
                        'priority': priority,
                        'created': created
                    })
            print(f"📋 Found {len(tickets)} tickets for customer {customer_handle}")
            return tickets
        except requests.exceptions.Timeout:
            print("[ERROR] Request timed out while fetching tickets")
            return []
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error fetching tickets: {e}")
            return []
    
    def get_ticket_details(self, ticket_id, ticket_url=''):
        """
        Fetch full details and conversation history for a specific ticket.
        Returns a dict with ticket metadata and a list of messages.
        """
        try:
            # Use the URL from the ticket list if provided, otherwise construct it
            if ticket_url and ticket_url.startswith('http'):
                full_url = ticket_url
            else:
                # Construct the URL for ticket details
                full_url = f"{self.base_url}/cgi-bin/web_interface/new_tickets.cgi?id=ticket/{ticket_id}"
            response = self.session.get(full_url, timeout=30)
            if response.status_code != 200:
                print(f"[WARN] Failed to fetch ticket {ticket_id}: HTTP {response.status_code}")
                return {}
            soup = BeautifulSoup(response.text, 'html.parser')
            ticket_data = {
                'ticket_id': ticket_id,
                'subject': '',
                'status': '',
                'priority': '',
                'created_date': '',
                'resolved_date': '',
                'customer': '',
                'messages': [],
                'resolution': '',
                'issue_category': '',
                'keywords': []
            }
            # Extract ticket metadata from tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        if 'subject' in label:
                            ticket_data['subject'] = value
                        elif 'status' in label:
                            ticket_data['status'] = value
                        elif 'priority' in label:
                            ticket_data['priority'] = value
                        elif 'created' in label:
                            ticket_data['created_date'] = value
                        elif 'resolved' in label or 'closed' in label:
                            ticket_data['resolved_date'] = value
            # Find all messages/updates in the ticket (usually in tables)
            message_tables = soup.find_all('table')
            for table in message_tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # Heuristic: if row text is long, treat as a message
                        text = row.get_text(strip=True)
                        if len(text) > 50:
                            message_data = {
                                'author': 'System',  # Could be improved with more parsing
                                'date': '',
                                'content': text
                            }
                            # Try to extract a date from the message
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', text)
                            if date_match:
                                message_data['date'] = date_match.group()
                            ticket_data['messages'].append(message_data)
            # If ticket is closed/resolved, treat last message as resolution
            if ticket_data['status'].lower() in ['closed', 'resolved']:
                if ticket_data['messages']:
                    ticket_data['resolution'] = ticket_data['messages'][-1]['content']
            return ticket_data
        except requests.exceptions.Timeout:
            print(f"[WARN] Timeout while fetching ticket {ticket_id}")
            return {}
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Error fetching ticket {ticket_id}: {e}")
            return {}
        except Exception as e:
            print(f"[WARN] Unexpected error processing ticket {ticket_id}: {e}")
            return {}
    
    def categorize_ticket(self, ticket):
        """
        Automatically assign one or more categories to a ticket based on its subject and message content.
        Returns a list of category strings.
        """
        subject_lower = ticket['subject'].lower()
        content = ' '.join([msg['content'] for msg in ticket.get('messages', [])])
        content_lower = content.lower()
        categories = []
        # Heuristic keyword matching for common support categories
        if any(word in subject_lower or word in content_lower for word in ['down', 'offline', 'connection', 'network', 'internet', 'circuit', 'outage']):
            categories.append('Network/Connectivity')
        if any(word in subject_lower or word in content_lower for word in ['phone', 'voip', 'sip', 'pbx', 'call', 'dial tone', 'extension', 'trunk']):
            categories.append('Phone/VoIP')
        if any(word in subject_lower or word in content_lower for word in ['hardware', 'device', 'router', 'switch', 'modem', 'firewall']):
            categories.append('Hardware')
        if any(word in subject_lower or word in content_lower for word in ['config', 'setup', 'install', 'provision', 'configure']):
            categories.append('Configuration')
        if any(word in subject_lower or word in content_lower for word in ['billing', 'invoice', 'payment', 'charge']):
            categories.append('Billing')
        if any(word in subject_lower or word in content_lower for word in ['emergency', 'critical', 'urgent', 'down', 'outage']):
            categories.append('Critical')
        return categories if categories else ['General']
    
    def extract_keywords(self, ticket):
        """
        Extract important technical keywords and error codes from the ticket's subject and messages.
        Returns a deduplicated list of keywords.
        """
        text = ticket['subject'] + ' ' + ' '.join([msg['content'] for msg in ticket.get('messages', [])])
        # List of technical keywords to search for
        tech_keywords = [
            'SIP', 'PBX', 'trunk', 'DID', 'extension', 'IVR', 'queue',
            'router', 'switch', 'firewall', 'VPN', 'VLAN',
            'IP address', 'DNS', 'DHCP', 'NAT', 'port',
            'bandwidth', 'latency', 'jitter', 'packet loss',
            'failover', 'redundancy', 'backup'
        ]
        keywords = []
        for keyword in tech_keywords:
            if keyword.lower() in text.lower():
                keywords.append(keyword)
        # Extract error codes or specific identifiers (e.g., "error 500")
        error_codes = re.findall(r'error\s*\d+|code\s*\d+|\d{3}\s*error', text.lower())
        keywords.extend(error_codes)
        return list(set(keywords))

class KnowledgeBaseBuilder:
    """
    Handles creation and management of the SQLite knowledge base for tickets.
    Provides methods to initialize the DB, add tickets/messages, analyze patterns, and export reports.
    """
    def __init__(self, db_path: str = 'ticket_knowledge_base.db'):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.init_database()
    
    def init_database(self) -> None:
        """
        Initialize SQLite database and create tables for tickets, messages, and incidents if not present.
        """
        self.conn = sqlite3.connect(self.db_path)
        if not self.conn:
            raise Exception("Failed to connect to database")
        cursor = self.conn.cursor()
        
        # Tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                customer_handle TEXT,
                subject TEXT,
                status TEXT,
                priority TEXT,
                created_date TEXT,
                resolved_date TEXT,
                resolution TEXT,
                category TEXT,
                keywords TEXT
            )
        ''')
        
        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                author TEXT,
                date TEXT,
                content TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
            )
        ''')
        
        # Incidents table (for recurring issues)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_type TEXT,
                description TEXT,
                frequency INTEGER,
                last_occurrence TEXT,
                typical_resolution TEXT
            )
        ''')
        
        self.conn.commit()
        print(f"[OK] Database initialized: {self.db_path}")
    
    def add_ticket(self, ticket, customer_handle):
        """
        Add a ticket and its messages to the knowledge base database.
        """
        if not self.conn:
            raise Exception("Database not initialized")
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO tickets 
            (ticket_id, customer_handle, subject, status, priority, created_date, 
             resolved_date, resolution, category, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticket['ticket_id'],
            customer_handle,
            ticket['subject'],
            ticket['status'],
            ticket['priority'],
            ticket['created_date'],
            ticket.get('resolved_date', ''),
            ticket.get('resolution', ''),
            ','.join(ticket.get('categories', [])),
            ','.join(ticket.get('keywords', []))
        ))
        
        # Add messages
        for msg in ticket.get('messages', []):
            cursor.execute('''
                INSERT INTO messages (ticket_id, author, date, content)
                VALUES (?, ?, ?, ?)
            ''', (
                ticket['ticket_id'],
                msg['author'],
                msg['date'],
                msg['content']
            ))
        
        self.conn.commit()
    
    def analyze_patterns(self):
        """
        Analyze tickets in the database to identify recurring issue categories and print a summary.
        """
        if not self.conn:
            raise Exception("Database not initialized")
        cursor = self.conn.cursor()
        
        # Find similar issues
        cursor.execute('''
            SELECT category, COUNT(*) as count, 
                   GROUP_CONCAT(ticket_id) as ticket_ids
            FROM tickets
            GROUP BY category
            HAVING count > 1
            ORDER BY count DESC
        ''')
        
        patterns = cursor.fetchall()
        
        print("\n📊 Recurring Issue Patterns:")
        for category, count, ticket_ids in patterns:
            print(f"  {category}: {count} occurrences")
            print(f"    Tickets: {ticket_ids[:100]}...")
        
        return patterns
    
    def generate_knowledge_base_report(self, customer_handle):
        """
        Generate a summary report for a customer's tickets, including counts by status, priority, and category.
        Returns a dictionary suitable for JSON export.
        """
        if not self.conn:
            raise Exception("Database not initialized")
        cursor = self.conn.cursor()
        
        # Get all tickets for customer
        cursor.execute('''
            SELECT * FROM tickets 
            WHERE customer_handle = ?
            ORDER BY created_date DESC
        ''', (customer_handle,))
        
        tickets = cursor.fetchall()
        
        report = {
            'customer_handle': customer_handle,
            'total_tickets': len(tickets),
            'by_status': defaultdict(int),
            'by_priority': defaultdict(int),
            'by_category': defaultdict(int),
            'common_issues': [],
            'resolutions': []
        }
        
        for ticket in tickets:
            status = ticket[3]
            priority = ticket[4]
            category = ticket[8]
            
            report['by_status'][status] += 1
            report['by_priority'][priority] += 1
            
            if category:
                for cat in category.split(','):
                    report['by_category'][cat] += 1
        
        return report
    
    def export_to_markdown(self, customer_handle, output_file):
        """
        Export the knowledge base for a customer to a Markdown file, including summary and ticket history.
        """
        if not self.conn:
            raise Exception("Database not initialized")
        report = self.generate_knowledge_base_report(customer_handle)
        cursor = self.conn.cursor()
        
        with open(output_file, 'w') as f:
            f.write(f"# Knowledge Base: {customer_handle}\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write(f"## Summary\n\n")
            f.write(f"- **Total Tickets:** {report['total_tickets']}\n")
            
            f.write(f"\n### By Status\n")
            for status, count in report['by_status'].items():
                f.write(f"- {status}: {count}\n")
            
            f.write(f"\n### By Priority\n")
            for priority, count in report['by_priority'].items():
                f.write(f"- {priority}: {count}\n")
            
            f.write(f"\n### By Category\n")
            for category, count in sorted(report['by_category'].items(), key=lambda x: x[1], reverse=True):
                f.write(f"- {category}: {count}\n")
            
            # Add detailed ticket history
            f.write(f"\n## Ticket History\n\n")
            
            cursor.execute('''
                SELECT ticket_id, subject, status, priority, created_date, resolution, category
                FROM tickets
                WHERE customer_handle = ?
                ORDER BY created_date DESC
            ''', (customer_handle,))
            
            tickets = cursor.fetchall()
            
            for ticket in tickets:
                f.write(f"### Ticket #{ticket[0]}\n")
                f.write(f"- **Subject:** {ticket[1]}\n")
                f.write(f"- **Status:** {ticket[2]}\n")
                f.write(f"- **Priority:** {ticket[3]}\n")
                f.write(f"- **Created:** {ticket[4]}\n")
                f.write(f"- **Category:** {ticket[6]}\n")
                
                if ticket[5]:
                    f.write(f"- **Resolution:** {ticket[5][:200]}...\n")
                
                f.write("\n")
        
        print(f"[OK] Knowledge base exported to: {output_file}")

def main():
    """
    Main entry point for the script. Parses arguments, runs the scraping and knowledge base build process,
    and exports reports as requested.
    """
    parser = argparse.ArgumentParser(description='Scrape tickets and build knowledge base')
    parser.add_argument('--customer', required=True, help='Customer handle')
    parser.add_argument('--username', required=True, help='Admin username')
    parser.add_argument('--password', required=True, help='Admin password')
    parser.add_argument('--cookie-file', help='Path to Selenium-exported cookies JSON (optional)')
    parser.add_argument('--output', default='knowledge_base', help='Output directory')
    parser.add_argument('--export-md', action='store_true', help='Export to markdown')
    args = parser.parse_args()
    # Create output directory if it doesn't exist
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    # Initialize scraper and login
    scraper = TicketScraper(args.username, args.password, cookie_file=args.cookie_file)
    if not scraper.login():
        print("[ERROR] Failed to login")
        return
    # Fetch all tickets for the customer
    print(f"\n[FETCH] Fetching tickets for customer: {args.customer}")
    tickets = scraper.get_customer_tickets(args.customer)
    # Initialize knowledge base database
    db_path = output_dir / f"{args.customer}_tickets.db"
    kb = KnowledgeBaseBuilder(str(db_path))
    # Process each ticket: fetch details, categorize, extract keywords, and store
    print("\n[PROCESS] Processing tickets...")
    for i, ticket in enumerate(tickets, 1):
        print(f"  [{i}/{len(tickets)}] Processing ticket {ticket['ticket_id']}...")
        full_ticket = scraper.get_ticket_details(ticket['ticket_id'], ticket.get('ticket_url', ''))
        # Merge basic ticket info with full details (prefer details if present)
        full_ticket.update({
            'subject': ticket['subject'] if not full_ticket['subject'] else full_ticket['subject'],
            'status': ticket['status'] if not full_ticket['status'] else full_ticket['status'],
            'priority': ticket['priority'] if not full_ticket['priority'] else full_ticket['priority'],
            'created_date': ticket['created'] if not full_ticket['created_date'] else full_ticket['created_date']
        })
        # Categorize and extract keywords
        full_ticket['categories'] = scraper.categorize_ticket(full_ticket)
        full_ticket['keywords'] = scraper.extract_keywords(full_ticket)
        # Add to knowledge base
        kb.add_ticket(full_ticket, args.customer)
        # Be polite to the server
        time.sleep(0.5)
    # Analyze recurring issue patterns
    print("\n[ANALYZE] Analyzing patterns...")
    kb.analyze_patterns()
    # Optionally export to Markdown
    if args.export_md:
        md_file = output_dir / f"{args.customer}_knowledge_base.md"
        kb.export_to_markdown(args.customer, md_file)
    # Always export summary report to JSON
    json_file = output_dir / f"{args.customer}_tickets.json"
    report = kb.generate_knowledge_base_report(args.customer)
    with open(json_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[OK] Knowledge base created successfully!")
    print(f"   Database: {db_path}")
    print(f"   JSON: {json_file}")
    if args.export_md:
        print(f"   Markdown: {md_file}")

if __name__ == '__main__':
    main()
