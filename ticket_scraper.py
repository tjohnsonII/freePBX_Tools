#!/usr/bin/env python3
"""
123NET Ticket Scraper and Knowledge Base Builder
Scrapes all tickets for a customer and creates a searchable knowledge base
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
    def __init__(self, username, password, base_url="https://secure.123.net"):
        self.username = username
        self.password = password
        self.base_url = base_url
        self.session = requests.Session()
        
    def login(self):
        """Login to 123NET admin interface"""
        login_url = f"{self.base_url}/cgi-bin/admin.cgi"
        
        payload = {
            'username': self.username,
            'password': self.password,
            'action': 'login'
        }
        
        try:
            response = self.session.post(login_url, data=payload, timeout=30)
            
            # Check if login was successful by looking for session cookies or redirect
            if response.status_code == 200:
                # Check if we got session cookies
                if len(self.session.cookies) > 0:
                    print(f"✅ Successfully logged in (got {len(self.session.cookies)} cookies)")
                    return True
                # Check if redirected (some systems redirect on success)
                elif 'admin' in response.url or 'dashboard' in response.url.lower():
                    print("✅ Successfully logged in")
                    return True
                else:
                    print("⚠️  Login response received but authentication unclear")
                    print(f"   URL: {response.url}")
                    print(f"   Cookies: {len(self.session.cookies)}")
                    # Try to proceed anyway
                    return True
            else:
                print(f"❌ Login failed with status code: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Login request timed out")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Login request failed: {e}")
            return False
    
    def get_customer_tickets(self, customer_handle):
        """Get all tickets for a customer"""
        tickets_url = f"{self.base_url}/cgi-bin/web_interface/admin/customers.cgi"
        
        params = {
            'customer_handle': customer_handle
        }
        
        try:
            response = self.session.get(tickets_url, params=params, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Failed to fetch tickets: HTTP {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            tickets = []
            
            # Find the ticket table - look for table with "Ticket ID" header
            tables = soup.find_all('table', {'border': '0'})
            ticket_table = None
            
            for table in tables:
                header_row = table.find('tr')
                if header_row and 'Ticket ID' in header_row.get_text():
                    ticket_table = table
                    break
            
            if not ticket_table:
                print("⚠️  No ticket table found on page")
                print(f"   This could mean:")
                print(f"   1. No tickets exist for customer '{customer_handle}'")
                print(f"   2. Customer handle is incorrect")
                print(f"   3. Not authenticated properly")
                return []
            
            rows = ticket_table.find_all('tr')[1:]  # Skip header row
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 5:
                    # Extract ticket ID from the link
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
            print("❌ Request timed out while fetching tickets")
            return []
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching tickets: {e}")
            return []
    
    def get_ticket_details(self, ticket_id, ticket_url=''):
        """Get full details and conversation for a specific ticket"""
        
        try:
            # Use the URL from the ticket list if provided, otherwise construct it
            if ticket_url and ticket_url.startswith('http'):
                full_url = ticket_url
            else:
                # Construct the URL - format from your screenshot
                full_url = f"{self.base_url}/cgi-bin/web_interface/new_tickets.cgi?id=ticket/{ticket_id}"
            
            response = self.session.get(full_url, timeout=30)
            
            if response.status_code != 200:
                print(f"⚠️  Failed to fetch ticket {ticket_id}: HTTP {response.status_code}")
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
            
            # Extract ticket details from the page
            # Look for the ticket metadata table
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
            
            # Find all messages/updates in the ticket
            # Messages are typically in divs or a separate table
            message_tables = soup.find_all('table')
            
            for table in message_tables:
                # Look for message-like content
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # Check if this looks like a message row
                        text = row.get_text(strip=True)
                        if len(text) > 50:  # Messages are usually longer
                            message_data = {
                                'author': 'System',  # Will try to extract if format is clear
                                'date': '',
                                'content': text
                            }
                            
                            # Try to extract date from content
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', text)
                            if date_match:
                                message_data['date'] = date_match.group()
                            
                            ticket_data['messages'].append(message_data)
            
            # Extract resolution if ticket is closed
            if ticket_data['status'].lower() in ['closed', 'resolved']:
                # Last message is usually the resolution
                if ticket_data['messages']:
                    ticket_data['resolution'] = ticket_data['messages'][-1]['content']
            
            return ticket_data
            
        except requests.exceptions.Timeout:
            print(f"⚠️  Timeout while fetching ticket {ticket_id}")
            return {}
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Error fetching ticket {ticket_id}: {e}")
            return {}
        except Exception as e:
            print(f"⚠️  Unexpected error processing ticket {ticket_id}: {e}")
            return {}
    
    def categorize_ticket(self, ticket):
        """Automatically categorize ticket based on subject and content"""
        subject_lower = ticket['subject'].lower()
        content = ' '.join([msg['content'] for msg in ticket.get('messages', [])])
        content_lower = content.lower()
        
        categories = []
        
        # Network/Connectivity issues
        if any(word in subject_lower or word in content_lower for word in 
               ['down', 'offline', 'connection', 'network', 'internet', 'circuit', 'outage']):
            categories.append('Network/Connectivity')
        
        # Phone/VoIP issues
        if any(word in subject_lower or word in content_lower for word in 
               ['phone', 'voip', 'sip', 'pbx', 'call', 'dial tone', 'extension', 'trunk']):
            categories.append('Phone/VoIP')
        
        # Hardware issues
        if any(word in subject_lower or word in content_lower for word in 
               ['hardware', 'device', 'router', 'switch', 'modem', 'firewall']):
            categories.append('Hardware')
        
        # Configuration/Setup
        if any(word in subject_lower or word in content_lower for word in 
               ['config', 'setup', 'install', 'provision', 'configure']):
            categories.append('Configuration')
        
        # Billing
        if any(word in subject_lower or word in content_lower for word in 
               ['billing', 'invoice', 'payment', 'charge']):
            categories.append('Billing')
        
        # Emergency/Critical
        if any(word in subject_lower or word in content_lower for word in 
               ['emergency', 'critical', 'urgent', 'down', 'outage']):
            categories.append('Critical')
        
        return categories if categories else ['General']
    
    def extract_keywords(self, ticket):
        """Extract important keywords from ticket"""
        text = ticket['subject'] + ' ' + ' '.join([msg['content'] for msg in ticket.get('messages', [])])
        
        # Common technical keywords
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
        
        # Extract error codes or specific identifiers
        error_codes = re.findall(r'error\s*\d+|code\s*\d+|\d{3}\s*error', text.lower())
        keywords.extend(error_codes)
        
        return list(set(keywords))

class KnowledgeBaseBuilder:
    def __init__(self, db_path: str = 'ticket_knowledge_base.db'):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.init_database()
    
    def init_database(self) -> None:
        """Initialize SQLite database for knowledge base"""
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
        print(f"✅ Database initialized: {self.db_path}")
    
    def add_ticket(self, ticket, customer_handle):
        """Add a ticket to the knowledge base"""
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
        """Analyze tickets to identify recurring issues"""
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
        """Generate comprehensive knowledge base report"""
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
        """Export knowledge base to markdown format"""
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
        
        print(f"✅ Knowledge base exported to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Scrape tickets and build knowledge base')
    parser.add_argument('--customer', required=True, help='Customer handle')
    parser.add_argument('--username', required=True, help='Admin username')
    parser.add_argument('--password', required=True, help='Admin password')
    parser.add_argument('--output', default='knowledge_base', help='Output directory')
    parser.add_argument('--export-md', action='store_true', help='Export to markdown')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Initialize scraper
    scraper = TicketScraper(args.username, args.password)
    
    if not scraper.login():
        print("❌ Failed to login")
        return
    
    # Get tickets
    print(f"\n📥 Fetching tickets for customer: {args.customer}")
    tickets = scraper.get_customer_tickets(args.customer)
    
    # Initialize knowledge base
    db_path = output_dir / f"{args.customer}_tickets.db"
    kb = KnowledgeBaseBuilder(str(db_path))
    
    # Process each ticket
    print("\n🔍 Processing tickets...")
    for i, ticket in enumerate(tickets, 1):
        print(f"  [{i}/{len(tickets)}] Processing ticket {ticket['ticket_id']}...")
        
        # Get full ticket details
        full_ticket = scraper.get_ticket_details(
            ticket['ticket_id'], 
            ticket.get('ticket_url', '')
        )
        
        # Merge basic ticket info with full details
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
        
        # Be polite - don't hammer the server
        time.sleep(0.5)
    
    # Analyze patterns
    print("\n📊 Analyzing patterns...")
    kb.analyze_patterns()
    
    # Generate report
    if args.export_md:
        md_file = output_dir / f"{args.customer}_knowledge_base.md"
        kb.export_to_markdown(args.customer, md_file)
    
    # Export to JSON
    json_file = output_dir / f"{args.customer}_tickets.json"
    report = kb.generate_knowledge_base_report(args.customer)
    with open(json_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n✅ Knowledge base created successfully!")
    print(f"   Database: {db_path}")
    print(f"   JSON: {json_file}")
    if args.export_md:
        print(f"   Markdown: {md_file}")

if __name__ == '__main__':
    main()
