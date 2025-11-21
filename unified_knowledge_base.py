#!/usr/bin/env python3

"""
Unified Knowledge Base for 123.NET Tickets
Aggregates tickets from all customers into a single searchable database

VARIABLE MAP LEGEND
-------------------
UnifiedKnowledgeBase attributes:
    db_path        : str, path to the unified SQLite database file
    conn           : sqlite3.Connection, active DB connection

Database tables:
    tickets        : Main table for ticket metadata (customer, subject, status, etc.)
    messages       : Table for ticket message history

Key method variables:
    cursor         : sqlite3.Cursor, used for DB operations
    ticket         : dict or sqlite3.Row, single ticket record
    message        : dict or sqlite3.Row, single message record
    results        : list of dicts or rows, query results
    data           : list/dict, loaded from JSON or API
    args           : argparse.Namespace, parsed CLI arguments
    filters        : dict, search or filter parameters
    row            : sqlite3.Row, result row from DB
    query          : str, SQL query string
    params         : tuple/list, SQL query parameters
"""

import sqlite3
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import re

class UnifiedKnowledgeBase:
    """Manages a unified knowledge base across all customers"""
    
    def __init__(self, db_path: str = "unified_knowledge_base.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.init_database()
    
    def init_database(self):
        """Initialize the unified database schema"""
        self.conn = sqlite3.connect(self.db_path)
        if not self.conn:
            raise Exception("Failed to initialize database")
            
        cursor = self.conn.cursor()
        
        # Main tickets table with customer info
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_handle TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                subject TEXT,
                status TEXT,
                priority TEXT,
                created_date TEXT,
                resolved_date TEXT,
                resolution TEXT,
                category TEXT,
                keywords TEXT,
                message_count INTEGER DEFAULT 0,
                last_updated TEXT,
                UNIQUE(customer_handle, ticket_id)
            )
        ''')
        
        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                customer_handle TEXT NOT NULL,
                original_ticket_id TEXT NOT NULL,
                author TEXT,
                timestamp TEXT,
                content TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            )
        ''')
        
        # Incidents/patterns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_handle TEXT NOT NULL,
                original_ticket_id TEXT NOT NULL,
                incident_type TEXT,
                description TEXT,
                severity TEXT,
                discovered_date TEXT
            )
        ''')
        
        # Customer metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customer_handle TEXT PRIMARY KEY,
                total_tickets INTEGER DEFAULT 0,
                open_tickets INTEGER DEFAULT 0,
                resolved_tickets INTEGER DEFAULT 0,
                avg_resolution_days REAL DEFAULT 0,
                common_issues TEXT,
                last_scrape_date TEXT
            )
        ''')
        
        # Knowledge articles table (derived insights)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT,
                problem_description TEXT,
                solution TEXT,
                related_ticket_ids TEXT,
                affected_customers TEXT,
                created_date TEXT,
                usefulness_score INTEGER DEFAULT 0
            )
        ''')
        
        # Create indexes for fast searching
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_customer ON tickets(customer_handle)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON tickets(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON tickets(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created ON tickets(created_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords ON tickets(keywords)')
        
        self.conn.commit()
        print(f"✅ Unified knowledge base initialized: {self.db_path}")
    
    def import_customer_database(self, customer_db_path: str, customer_handle: str):
        """Import tickets from a per-customer database"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        source_conn = sqlite3.connect(customer_db_path)
        source_cursor = source_conn.cursor()
        
        print(f"\n📥 Importing tickets from {customer_handle}...")
        
        # Import tickets
        source_cursor.execute('SELECT * FROM tickets')
        tickets = source_cursor.fetchall()
        
        cursor = self.conn.cursor()
        imported_count = 0
        
        for ticket in tickets:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO tickets 
                    (customer_handle, ticket_id, subject, status, priority, 
                     created_date, resolved_date, resolution, category, keywords, 
                     message_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    customer_handle,
                    ticket[1],  # ticket_id
                    ticket[2],  # subject
                    ticket[3],  # status
                    ticket[4],  # priority
                    ticket[5],  # created_date
                    ticket[6],  # resolved_date
                    ticket[7],  # resolution
                    ticket[8],  # category
                    ticket[9],  # keywords
                    ticket[10] if len(ticket) > 10 else 0,  # message_count
                    datetime.now().isoformat()
                ))
                imported_count += 1
            except sqlite3.IntegrityError:
                continue
        
        # Import messages
        try:
            source_cursor.execute('SELECT * FROM messages')
            messages = source_cursor.fetchall()
            
            for msg in messages:
                # Find the ticket_id in our unified database
                cursor.execute(
                    'SELECT id FROM tickets WHERE customer_handle = ? AND ticket_id = ?',
                    (customer_handle, msg[1])
                )
                result = cursor.fetchone()
                if result:
                    unified_ticket_id = result[0]
                    cursor.execute('''
                        INSERT OR IGNORE INTO messages 
                        (ticket_id, customer_handle, original_ticket_id, author, timestamp, content)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (unified_ticket_id, customer_handle, msg[1], msg[2], msg[3], msg[4]))
        except sqlite3.OperationalError:
            pass  # Messages table might not exist in old databases
        
        # Import incidents
        try:
            source_cursor.execute('SELECT * FROM incidents')
            incidents = source_cursor.fetchall()
            
            for inc in incidents:
                cursor.execute('''
                    INSERT OR IGNORE INTO incidents 
                    (customer_handle, original_ticket_id, incident_type, description, severity, discovered_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (customer_handle, inc[1], inc[2], inc[3], inc[4], inc[5]))
        except sqlite3.OperationalError:
            pass  # Incidents table might not exist
        
        self.conn.commit()
        source_conn.close()
        
        # Update customer metadata
        self.update_customer_stats(customer_handle)
        
        print(f"   ✅ Imported {imported_count} tickets from {customer_handle}")
    
    def update_customer_stats(self, customer_handle: str):
        """Update statistics for a customer"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        # Calculate stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status != 'Resolved' AND status != 'Closed' THEN 1 ELSE 0 END) as open,
                SUM(CASE WHEN status = 'Resolved' OR status = 'Closed' THEN 1 ELSE 0 END) as resolved,
                category
            FROM tickets 
            WHERE customer_handle = ?
        ''', (customer_handle,))
        
        stats = cursor.fetchone()
        total, open_count, resolved, _ = stats
        
        # Calculate average resolution time
        cursor.execute('''
            SELECT AVG(
                JULIANDAY(resolved_date) - JULIANDAY(created_date)
            ) as avg_days
            FROM tickets 
            WHERE customer_handle = ? AND resolved_date IS NOT NULL
        ''', (customer_handle,))
        
        avg_result = cursor.fetchone()
        avg_days = avg_result[0] if avg_result and avg_result[0] else 0
        
        # Get common issues (top 3 categories)
        cursor.execute('''
            SELECT category, COUNT(*) as cnt 
            FROM tickets 
            WHERE customer_handle = ? AND category IS NOT NULL
            GROUP BY category 
            ORDER BY cnt DESC 
            LIMIT 3
        ''', (customer_handle,))
        
        common_issues = ', '.join([row[0] for row in cursor.fetchall()])
        
        # Update customer record
        cursor.execute('''
            INSERT OR REPLACE INTO customers 
            (customer_handle, total_tickets, open_tickets, resolved_tickets, 
             avg_resolution_days, common_issues, last_scrape_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            customer_handle, total or 0, open_count or 0, resolved or 0,
            round(avg_days, 1), common_issues, datetime.now().isoformat()
        ))
        
        self.conn.commit()
    
    def search_across_customers(self, query: str, limit: int = 20) -> List[Dict]:
        """Search tickets across all customers"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        search_pattern = f"%{query}%"
        
        cursor.execute('''
            SELECT customer_handle, ticket_id, subject, status, priority, 
                   created_date, category, keywords, resolution
            FROM tickets 
            WHERE subject LIKE ? 
               OR keywords LIKE ? 
               OR resolution LIKE ?
            ORDER BY created_date DESC
            LIMIT ?
        ''', (search_pattern, search_pattern, search_pattern, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'customer': row[0],
                'ticket_id': row[1],
                'subject': row[2],
                'status': row[3],
                'priority': row[4],
                'created': row[5],
                'category': row[6],
                'keywords': row[7],
                'resolution': row[8]
            })
        
        return results
    
    def find_similar_issues_across_customers(self, keywords: List[str], limit: int = 10) -> List[Dict]:
        """Find similar issues across all customers"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        # Build query for keyword matching
        conditions = ' OR '.join(['keywords LIKE ?' for _ in keywords])
        params = [f"%{kw}%" for kw in keywords] + [limit]
        
        cursor.execute(f'''
            SELECT customer_handle, ticket_id, subject, status, category, 
                   keywords, resolution, COUNT(*) as relevance
            FROM tickets 
            WHERE {conditions}
            GROUP BY customer_handle, ticket_id
            ORDER BY relevance DESC, created_date DESC
            LIMIT ?
        ''', params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'customer': row[0],
                'ticket_id': row[1],
                'subject': row[2],
                'status': row[3],
                'category': row[4],
                'keywords': row[5],
                'resolution': row[6],
                'relevance': row[7]
            })
        
        return results
    
    def get_common_resolutions_by_category(self, category: str) -> List[Dict]:
        """Get common resolutions for a specific issue category"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT resolution, COUNT(*) as frequency, 
                   GROUP_CONCAT(DISTINCT customer_handle) as customers,
                   AVG(JULIANDAY(resolved_date) - JULIANDAY(created_date)) as avg_resolution_days
            FROM tickets 
            WHERE category = ? 
              AND resolution IS NOT NULL 
              AND resolution != ''
            GROUP BY resolution 
            ORDER BY frequency DESC
            LIMIT 10
        ''', (category,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'resolution': row[0],
                'frequency': row[1],
                'customers_affected': row[2].split(',') if row[2] else [],
                'avg_days_to_resolve': round(row[3], 1) if row[3] else None
            })
        
        return results
    
    def get_customer_overview(self) -> List[Dict]:
        """Get overview of all customers"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT customer_handle, total_tickets, open_tickets, resolved_tickets,
                   avg_resolution_days, common_issues, last_scrape_date
            FROM customers
            ORDER BY total_tickets DESC
        ''')
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'customer': row[0],
                'total_tickets': row[1],
                'open_tickets': row[2],
                'resolved_tickets': row[3],
                'avg_resolution_days': row[4],
                'common_issues': row[5],
                'last_scrape': row[6]
            })
        
        return results
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """Get overall statistics across all customers"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Total tickets
        cursor.execute('SELECT COUNT(*) FROM tickets')
        stats['total_tickets'] = cursor.fetchone()[0]
        
        # Total customers
        cursor.execute('SELECT COUNT(DISTINCT customer_handle) FROM tickets')
        stats['total_customers'] = cursor.fetchone()[0]
        
        # Status breakdown
        cursor.execute('''
            SELECT status, COUNT(*) as cnt 
            FROM tickets 
            GROUP BY status 
            ORDER BY cnt DESC
        ''')
        stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Category breakdown
        cursor.execute('''
            SELECT category, COUNT(*) as cnt 
            FROM tickets 
            WHERE category IS NOT NULL
            GROUP BY category 
            ORDER BY cnt DESC
        ''')
        stats['by_category'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Priority breakdown
        cursor.execute('''
            SELECT priority, COUNT(*) as cnt 
            FROM tickets 
            GROUP BY priority 
            ORDER BY cnt DESC
        ''')
        stats['by_priority'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Most common keywords
        cursor.execute('''
            SELECT keywords FROM tickets WHERE keywords IS NOT NULL AND keywords != ''
        ''')
        keyword_counts: Dict[str, int] = {}
        for row in cursor.fetchall():
            if row[0]:
                for kw in row[0].split(','):
                    kw = kw.strip()
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        stats['top_keywords'] = sorted(
            keyword_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20]
        
        # Average resolution time
        cursor.execute('''
            SELECT AVG(JULIANDAY(resolved_date) - JULIANDAY(created_date)) as avg_days
            FROM tickets 
            WHERE resolved_date IS NOT NULL
        ''')
        avg = cursor.fetchone()[0]
        stats['avg_resolution_days'] = round(avg, 1) if avg else None
        
        return stats
    
    def create_knowledge_article(self, title: str, category: str, 
                                problem: str, solution: str, 
                                related_tickets: List[str]) -> int:
        """Create a knowledge base article from common patterns"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT INTO knowledge_articles 
            (title, category, problem_description, solution, 
             related_ticket_ids, created_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            title, category, problem, solution,
            ','.join(related_tickets),
            datetime.now().isoformat()
        ))
        
        self.conn.commit()
        article_id = cursor.lastrowid
        if article_id is None:
            raise Exception("Failed to create knowledge article")
        return article_id
    
    def export_to_json(self, output_file: str):
        """Export entire knowledge base to JSON"""
        if not self.conn:
            raise Exception("Database not initialized")
            
        data = {
            'statistics': self.get_global_statistics(),
            'customers': self.get_customer_overview(),
            'export_date': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"✅ Knowledge base exported to: {output_file}")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='Unified Knowledge Base Manager')
    parser.add_argument('--db', default='unified_knowledge_base.db', 
                       help='Path to unified database')
    parser.add_argument('--import-dir', help='Import all customer databases from directory')
    parser.add_argument('--import-customer', help='Import specific customer database')
    parser.add_argument('--customer-handle', help='Customer handle for import')
    parser.add_argument('--search', help='Search across all tickets')
    parser.add_argument('--similar', help='Find similar issues (comma-separated keywords)')
    parser.add_argument('--category', help='Get common resolutions for category')
    parser.add_argument('--stats', action='store_true', help='Show global statistics')
    parser.add_argument('--customers', action='store_true', help='Show customer overview')
    parser.add_argument('--export', help='Export to JSON file')
    
    args = parser.parse_args()
    
    kb = UnifiedKnowledgeBase(args.db)
    
    try:
        # Import operations
        if args.import_dir:
            import_dir = Path(args.import_dir)
            for db_file in import_dir.glob('*_tickets.db'):
                customer = db_file.stem.replace('_tickets', '')
                kb.import_customer_database(str(db_file), customer)
        
        elif args.import_customer and args.customer_handle:
            kb.import_customer_database(args.import_customer, args.customer_handle)
        
        # Query operations
        elif args.search:
            print(f"\n🔍 Searching for: {args.search}\n")
            results = kb.search_across_customers(args.search)
            for r in results:
                print(f"[{r['customer']}] Ticket #{r['ticket_id']}: {r['subject']}")
                print(f"  Status: {r['status']} | Priority: {r['priority']} | Category: {r['category']}")
                if r['resolution']:
                    print(f"  Resolution: {r['resolution'][:100]}...")
                print()
        
        elif args.similar:
            keywords = [k.strip() for k in args.similar.split(',')]
            print(f"\n🔍 Finding similar issues for: {', '.join(keywords)}\n")
            results = kb.find_similar_issues_across_customers(keywords)
            for r in results:
                print(f"[{r['customer']}] Ticket #{r['ticket_id']}: {r['subject']}")
                print(f"  Category: {r['category']} | Relevance: {r['relevance']}")
                if r['resolution']:
                    print(f"  Resolution: {r['resolution'][:100]}...")
                print()
        
        elif args.category:
            print(f"\n📊 Common resolutions for category: {args.category}\n")
            results = kb.get_common_resolutions_by_category(args.category)
            for i, r in enumerate(results, 1):
                print(f"{i}. {r['resolution'][:200]}")
                print(f"   Frequency: {r['frequency']} tickets")
                print(f"   Customers affected: {len(r['customers_affected'])}")
                if r['avg_days_to_resolve']:
                    print(f"   Avg resolution time: {r['avg_days_to_resolve']} days")
                print()
        
        elif args.stats:
            print("\n📊 Global Knowledge Base Statistics\n")
            stats = kb.get_global_statistics()
            print(f"Total Tickets: {stats['total_tickets']}")
            print(f"Total Customers: {stats['total_customers']}")
            print(f"\nBy Status:")
            for status, count in stats['by_status'].items():
                print(f"  {status}: {count}")
            print(f"\nBy Category:")
            for category, count in stats['by_category'].items():
                print(f"  {category}: {count}")
            print(f"\nBy Priority:")
            for priority, count in stats['by_priority'].items():
                print(f"  {priority}: {count}")
            print(f"\nTop 10 Keywords:")
            for keyword, count in stats['top_keywords'][:10]:
                print(f"  {keyword}: {count}")
            if stats['avg_resolution_days']:
                print(f"\nAverage Resolution Time: {stats['avg_resolution_days']} days")
        
        elif args.customers:
            print("\n👥 Customer Overview\n")
            customers = kb.get_customer_overview()
            for c in customers:
                print(f"{c['customer']}")
                print(f"  Total: {c['total_tickets']} | Open: {c['open_tickets']} | Resolved: {c['resolved_tickets']}")
                print(f"  Avg resolution: {c['avg_resolution_days']} days")
                print(f"  Common issues: {c['common_issues']}")
                print()
        
        elif args.export:
            kb.export_to_json(args.export)
        
        else:
            parser.print_help()
    
    finally:
        kb.close()


if __name__ == '__main__':
    main()
