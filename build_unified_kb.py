#!/usr/bin/env python3
"""
Build Unified Knowledge Base from All Customer Databases
Automatically finds and imports all customer ticket databases
"""

import argparse
import sys
from pathlib import Path
from unified_knowledge_base import UnifiedKnowledgeBase

def main():
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
    
    if not input_dir.exists():
        print(f"❌ Input directory not found: {input_dir}")
        print(f"   Run ticket_scraper.py first to create customer databases")
        return 1
    
    # Find all customer databases
    customer_dbs = list(input_dir.glob('*_tickets.db'))
    
    if not customer_dbs:
        print(f"❌ No customer databases found in {input_dir}")
        print(f"   Expected files like: CUSTOMER_NAME_tickets.db")
        return 1
    
    print(f"📦 Found {len(customer_dbs)} customer database(s)")
    print(f"🎯 Building unified knowledge base: {args.output_db}\n")
    
    # Initialize unified KB
    kb = UnifiedKnowledgeBase(args.output_db)
    
    try:
        # Import each customer database
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
            
            stats = kb.get_global_statistics()
            
            print(f"Total Tickets: {stats['total_tickets']:,}")
            print(f"Total Customers: {stats['total_customers']}")
            
            if stats['avg_resolution_days']:
                print(f"Average Resolution Time: {stats['avg_resolution_days']} days")
            
            print(f"\n{'Status':<20} {'Count':<10}")
            print("-" * 30)
            for status, count in sorted(stats['by_status'].items(), 
                                       key=lambda x: x[1], reverse=True):
                print(f"{status:<20} {count:<10,}")
            
            print(f"\n{'Category':<25} {'Count':<10}")
            print("-" * 35)
            for category, count in sorted(stats['by_category'].items(), 
                                         key=lambda x: x[1], reverse=True):
                print(f"{category:<25} {count:<10,}")
            
            print(f"\n{'Priority':<20} {'Count':<10}")
            print("-" * 30)
            for priority, count in sorted(stats['by_priority'].items(), 
                                         key=lambda x: x[1], reverse=True):
                print(f"{priority:<20} {count:<10,}")
            
            print(f"\nTop 10 Keywords:")
            print("-" * 40)
            for keyword, count in stats['top_keywords'][:10]:
                print(f"  {keyword:<30} {count:>5,} occurrences")
            
            print("\n" + "="*60)
            print("\n💡 Query the knowledge base with:")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --search 'phone not working'")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --similar 'network,outage'")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --category 'Network/Connectivity'")
            print(f"   python unified_knowledge_base.py --db {args.output_db} --customers")
            
    finally:
        kb.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
