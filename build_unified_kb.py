
#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
main():
    Entry point for building the unified knowledge base.
    - Parses CLI arguments
    - Finds all *_tickets.db files in the input directory
    - Imports each customer DB into a unified SQLite DB
    - Optionally prints statistics about the unified KB
    - Provides CLI usage instructions for querying the KB
"""

"""
Build Unified Knowledge Base from All Customer Databases
-------------------------------------------------------
This script automatically finds and imports all customer ticket databases
to build a unified knowledge base for analytics and search.

HOW IT WORKS:
    1. Scans the input directory for all *_tickets.db SQLite databases.
    2. Imports each customer database into a unified SQLite DB.
    3. Optionally prints statistics about the unified knowledge base.
    4. Provides CLI instructions for querying the resulting database.
"""

import argparse
import sys
from pathlib import Path
from unified_knowledge_base import UnifiedKnowledgeBase


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Build unified knowledge base from all customer databases'
    )
    parser.add_argument('--input-dir', default='knowledge_base',
                       help='Directory containing customer databases')
    parser.add_argument('--output-db', default='unified_knowledge_base.db',
                       help='Output unified database path')
    parser.add_argument('--stats', action='store_true',
                       help='Show statistics after building')
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    
    # Check if input directory exists
    if not input_dir.exists():
        print(f"❌ Input directory not found: {input_dir}")
        print(f"   Run ticket_scraper.py first to create customer databases")
        return 1
    
    # Find all customer ticket databases (*.db)
    customer_dbs = list(input_dir.glob('*_tickets.db'))
    
    if not customer_dbs:
        print(f"❌ No customer databases found in {input_dir}")
        print(f"   Expected files like: CUSTOMER_NAME_tickets.db")
        return 1
    
    print(f"📦 Found {len(customer_dbs)} customer database(s)")
    print(f"🎯 Building unified knowledge base: {args.output_db}\n")
    
    # Initialize the unified knowledge base (creates or opens output DB)
    kb = UnifiedKnowledgeBase(args.output_db)
    
    try:
        # Import each customer database into the unified KB
        for db_file in customer_dbs:
            customer_handle = db_file.stem.replace('_tickets', '')
            print(f"📥 Importing {customer_handle}...")
            
            try:
                kb.import_customer_database(str(db_file), customer_handle)
            except Exception as e:
                print(f"   ⚠️  Error importing {customer_handle}: {e}")
                continue
        
        print(f"\n✅ Unified knowledge base created successfully!")
        print(f"   Database: {args.output_db}")
        
        # Show statistics if requested
        if args.stats:
            print("\n" + "="*60)
            print("📊 KNOWLEDGE BASE STATISTICS")
            print("="*60 + "\n")
            
            # Get global statistics from the KB
            stats = kb.get_global_statistics()
            
            print(f"Total Tickets: {stats['total_tickets']:,}")
            print(f"Total Customers: {stats['total_customers']}")
            
            if stats['avg_resolution_days']:
                print(f"Average Resolution Time: {stats['avg_resolution_days']} days")
            
            # Print ticket status breakdown
            print(f"\n{'Status':<20} {'Count':<10}")
            print("-" * 30)
            for status, count in sorted(stats['by_status'].items(), 
                                       key=lambda x: x[1], reverse=True):
                print(f"{status:<20} {count:<10,}")
            
            # Print ticket category breakdown
            print(f"\n{'Category':<25} {'Count':<10}")
            print("-" * 35)
            for category, count in sorted(stats['by_category'].items(), 
                                         key=lambda x: x[1], reverse=True):
                print(f"{category:<25} {count:<10,}")
            
            # Print ticket priority breakdown
            print(f"\n{'Priority':<20} {'Count':<10}")
            print("-" * 30)
            for priority, count in sorted(stats['by_priority'].items(), 
                                         key=lambda x: x[1], reverse=True):
                print(f"{priority:<20} {count:<10,}")
            
            # Print top 10 keywords
            print(f"\nTop 10 Keywords:")
            print("-" * 40)
            for keyword, count in stats['top_keywords'][:10]:
                print(f"  {keyword:<30} {count:>5,} occurrences")
            
            print("\n" + "="*60)
            print("\n💡 Query the knowledge base with:")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --search 'phone not working'" )
            print(f"   python unified_knowledge_base.py --db {args.output_db} --similar 'network,outage'")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --category 'Network/Connectivity'")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --customers")
            
    finally:
        kb.close()  # Always close the database connection
    
    return 0



# Standard Python entry point
if __name__ == '__main__':
    sys.exit(main())
