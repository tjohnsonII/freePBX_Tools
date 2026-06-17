
#!/usr/bin/env python3
"""
Ticket Knowledge Base Query Tool
--------------------------------
This script provides a command-line interface to search, analyze, and summarize
ticket history from a SQLite knowledge base. It supports keyword search, stats,
recurring issue detection, resolution time analysis, and more.
"""


# Import required modules
import sqlite3
import argparse
from collections import Counter
import re


# Main class for querying the ticket knowledge base
class KnowledgeBaseQuery:
    def __init__(self, db_path):
        # Initialize with path to SQLite DB
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
    

    def search_tickets(self, query):
        """Search tickets by keyword in subject, resolution, or keywords fields"""
        cursor = self.conn.cursor()
        # Search for tickets matching the query in subject, resolution, or keywords
        cursor.execute('''
            SELECT t.*, 
                   (SELECT COUNT(*) FROM messages m WHERE m.ticket_id = t.ticket_id) as message_count
            FROM tickets t
            WHERE t.subject LIKE ? OR t.resolution LIKE ? OR t.keywords LIKE ?
            ORDER BY t.created_date DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        return cursor.fetchall()
    

    def get_similar_issues(self, ticket_id):
        """Find tickets with similar issues (by category or keywords)"""
        cursor = self.conn.cursor()
        # Get the ticket's categories and keywords
        cursor.execute('SELECT category, keywords FROM tickets WHERE ticket_id = ?', (ticket_id,))
        ticket = cursor.fetchone()
        if not ticket:
            return []
        category = ticket['category']
        keywords = ticket['keywords']
        # Find other tickets with similar category or keywords
        cursor.execute('''
            SELECT *, 
                   (SELECT COUNT(*) FROM messages m WHERE m.ticket_id = t.ticket_id) as message_count
            FROM tickets t
            WHERE t.ticket_id != ?
              AND (t.category LIKE ? OR t.keywords LIKE ?)
            ORDER BY t.created_date DESC
            LIMIT 10
        ''', (ticket_id, f'%{category}%', f'%{keywords}%'))
        return cursor.fetchall()

    def get_resolution_by_category(self, category):
        """Get common resolutions for a given category (closed/resolved tickets only)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ticket_id, subject, resolution, created_date
            FROM tickets
            WHERE category LIKE ?
                AND status IN ('Closed', 'Resolved')
                AND resolution IS NOT NULL
                AND resolution != ''
            ORDER BY created_date DESC
        ''', (f'%{category}%',))
        return cursor.fetchall()
    

    def get_ticket_timeline(self, ticket_id):
        """Get full timeline (ticket and all messages) for a ticket"""
        cursor = self.conn.cursor()
        # Get ticket details
        cursor.execute('''
            SELECT * FROM tickets WHERE ticket_id = ?
        ''', (ticket_id,))
        ticket = cursor.fetchone()
        # Get all messages for the ticket
        cursor.execute('''
            SELECT * FROM messages 
            WHERE ticket_id = ?
            ORDER BY date ASC
        ''', (ticket_id,))
        messages = cursor.fetchall()
        return ticket, messages
    

    def get_stats(self, customer_handle=None):
        """Get ticket statistics (optionally filtered by customer handle)"""
        cursor = self.conn.cursor()
        # Build WHERE clause if filtering by customer
        where_clause = 'WHERE customer_handle = ?' if customer_handle else ''
        params = (customer_handle,) if customer_handle else ()
        # Total tickets
        cursor.execute(f'SELECT COUNT(*) FROM tickets {where_clause}', params)
        total = cursor.fetchone()[0]
        # Tickets by status
        cursor.execute(f'''
            SELECT status, COUNT(*) as count
            FROM tickets {where_clause}
            GROUP BY status
        ''', params)
        by_status = cursor.fetchall()
        # Tickets by priority
        cursor.execute(f'''
            SELECT priority, COUNT(*) as count
            FROM tickets {where_clause}
            GROUP BY priority
        ''', params)
        by_priority = cursor.fetchall()
        # Tickets by category
        cursor.execute(f'''
            SELECT category, COUNT(*) as count
            FROM tickets {where_clause}
            GROUP BY category
            ORDER BY count DESC
        ''', params)
        by_category = cursor.fetchall()
        # Most common keywords
        cursor.execute(f'SELECT keywords FROM tickets {where_clause}', params)
        all_keywords = []
        for row in cursor.fetchall():
            if row['keywords']:
                all_keywords.extend(row['keywords'].split(','))
        keyword_counts = Counter(all_keywords)
        # Return all stats as a dictionary
        return {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'by_category': by_category,
            'top_keywords': keyword_counts.most_common(10)
        }
    

    def find_recurring_issues(self):
        """Identify recurring issues (categories with >2 tickets)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT category, COUNT(*) as count,
                   GROUP_CONCAT(ticket_id, ', ') as ticket_ids,
                   MAX(created_date) as last_occurrence
            FROM tickets
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
            HAVING count > 2
            ORDER BY count DESC
        ''')
        return cursor.fetchall()
    

    def get_resolution_time_stats(self):
        """Calculate average resolution times (in days) by category"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 
                category,
                COUNT(*) as count,
                AVG(julianday(resolved_date) - julianday(created_date)) as avg_days
            FROM tickets
            WHERE resolved_date IS NOT NULL 
              AND resolved_date != ''
              AND status IN ('Closed', 'Resolved')
            GROUP BY category
            ORDER BY avg_days DESC
        ''')
        return cursor.fetchall()


# Main entry point: parse arguments and run the appropriate query/action
def main():
    parser = argparse.ArgumentParser(description='Query ticket knowledge base')
    parser.add_argument('--db', required=True, help='Database file path')
    parser.add_argument('--search', help='Search for keyword')
    parser.add_argument('--similar', help='Find similar issues to ticket ID')
    parser.add_argument('--category', help='Get resolutions for category')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--recurring', action='store_true', help='Show recurring issues')
    parser.add_argument('--timeline', help='Show timeline for ticket ID')
    parser.add_argument('--customer', help='Filter by customer handle')
    args = parser.parse_args()

    # Create the query object
    kb = KnowledgeBaseQuery(args.db)

    # Handle each command-line option
    if args.search:
        print(f"\n🔍 Searching for: {args.search}\n")
        results = kb.search_tickets(args.search)
        for row in results:
            print(f"Ticket #{row['ticket_id']}")
            print(f"  Subject: {row['subject']}")
            print(f"  Status: {row['status']} | Priority: {row['priority']}")
            print(f"  Created: {row['created_date']}")
            print(f"  Category: {row['category']}")
            print(f"  Messages: {row['message_count']}")
            if row['resolution']:
                print(f"  Resolution: {row['resolution'][:100]}...")
            print()

    elif args.similar:
        print(f"\n🔗 Finding similar issues to ticket #{args.similar}\n")
        results = kb.get_similar_issues(args.similar)
        for row in results:
            print(f"Ticket #{row['ticket_id']}")
            print(f"  Subject: {row['subject']}")
            print(f"  Status: {row['status']} | Created: {row['created_date']}")
            print(f"  Category: {row['category']}")
            print()

    elif args.category:
        print(f"\n📋 Resolutions for category: {args.category}\n")
        results = kb.get_resolution_by_category(args.category)
        for row in results:
            print(f"Ticket #{row['ticket_id']} - {row['created_date']}")
            print(f"  Subject: {row['subject']}")
            print(f"  Resolution: {row['resolution'][:200]}...")
            print()

    elif args.stats:
        print("\n📊 Knowledge Base Statistics\n")
        stats = kb.get_stats(args.customer)
        print(f"Total Tickets: {stats['total']}\n")
        print("By Status:")
        for row in stats['by_status']:
            print(f"  {row['status']}: {row['count']}")
        print("\nBy Priority:")
        for row in stats['by_priority']:
            print(f"  {row['priority']}: {row['count']}")
        print("\nBy Category:")
        for row in stats['by_category']:
            print(f"  {row['category']}: {row['count']}")
        print("\nTop Keywords:")
        for keyword, count in stats['top_keywords']:
            print(f"  {keyword}: {count}")
        print("\nAverage Resolution Time by Category:")
        res_times = kb.get_resolution_time_stats()
        for row in res_times:
            print(f"  {row['category']}: {row['avg_days']:.1f} days ({row['count']} tickets)")

    elif args.recurring:
        print("\n🔁 Recurring Issues\n")
        results = kb.find_recurring_issues()
        for row in results:
            print(f"{row['category']}: {row['count']} occurrences")
            print(f"  Last: {row['last_occurrence']}")
            print(f"  Tickets: {row['ticket_ids'][:100]}...")
            print()

    elif args.timeline:
        print(f"\n📅 Timeline for Ticket #{args.timeline}\n")
        ticket, messages = kb.get_ticket_timeline(args.timeline)
        if ticket:
            print(f"Subject: {ticket['subject']}")
            print(f"Status: {ticket['status']} | Priority: {ticket['priority']}")
            print(f"Created: {ticket['created_date']}")
            print(f"Category: {ticket['category']}")
            print(f"\nTimeline:")
            for msg in messages:
                print(f"\n[{msg['date']}] {msg['author']}" )
                print(f"  {msg['content'][:200]}...")
        else:
            print("Ticket not found")

# Run main if executed as a script
if __name__ == '__main__':
    main()
