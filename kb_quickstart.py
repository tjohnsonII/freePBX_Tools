#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
run_command(cmd: List[str], description: str) -> bool:
    Run a shell command and print its description and result.
quick_start_guide():
    Provide a step-by-step quick start guide for the knowledge base system.
main():
    Run the quick start guide from the command line.
"""
"""
Quick Start - Knowledge Base System
One command to scrape, build, and query
"""

import argparse
import sys
from pathlib import Path
import subprocess
from typing import List

def run_command(cmd: List[str], description: str) -> bool:
    """Run a command and show progress"""
    print(f"\n{'='*60}")
    print(f"📋 {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with error code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n❌ Command not found. Make sure Python is in your PATH.")
        return False

def quick_start_guide():
    """Show quick start guide"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                  KNOWLEDGE BASE - QUICK START                        ║
╚══════════════════════════════════════════════════════════════════════╝

This system creates a searchable knowledge base from 123.NET tickets.

🔄 WORKFLOW:
  1. Scrape tickets from individual customers → Creates per-customer DBs
  2. Build unified database from all customers → Creates unified_knowledge_base.db
  3. Query the knowledge base → Find solutions & patterns

📁 OUTPUT STRUCTURE:
  knowledge_base/
  ├── CUSTOMER1_tickets.db          # Individual customer databases
  ├── CUSTOMER1_tickets.json
  ├── CUSTOMER2_tickets.db
  └── ...
  
  unified_knowledge_base.db          # Combined database (all customers)

🚀 QUICK START OPTIONS:

  Option 1: Scrape Single Customer
    python kb_quickstart.py --scrape --customer ARBOR_NETWORKS \\
      --username admin --password your_password

  Option 2: Scrape Multiple Customers
    python kb_quickstart.py --scrape-all --username admin --password pass \\
      --customers CUSTOMER1,CUSTOMER2,CUSTOMER3

  Option 3: Build Unified Database (after scraping)
    python kb_quickstart.py --build

  Option 4: Query the Database
    python kb_quickstart.py --search "phone not working"
    python kb_quickstart.py --stats

  Option 5: Full Workflow (scrape + build + query)
    python kb_quickstart.py --full --customer ARBOR_NETWORKS \\
      --username admin --password pass --stats

📖 DOCUMENTATION:
  - Full guide: docs/KNOWLEDGE_BASE_GUIDE.md
  - Storage details: docs/STORAGE_ARCHITECTURE.md
  - Examples: kb_examples.py

❓ NEED HELP?
  python kb_quickstart.py --help
    """)

def main():
    parser = argparse.ArgumentParser(
        description='Knowledge Base Quick Start - One-command setup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape single customer
  python kb_quickstart.py --scrape --customer ARBOR_NETWORKS --username admin --password pass
  
  # Build unified database
  python kb_quickstart.py --build --stats
  
  # Search across all customers
  python kb_quickstart.py --search "phone not registering"
  
  # Full workflow
  python kb_quickstart.py --full --customer TEST_CUSTOMER --username admin --password pass --stats
        """
    )
    
    # Scraping options
    scrape_group = parser.add_argument_group('Scraping Options')
    scrape_group.add_argument('--scrape', action='store_true',
                             help='Scrape tickets for a customer')
    scrape_group.add_argument('--scrape-all', action='store_true',
                             help='Scrape tickets for multiple customers')
    scrape_group.add_argument('--customer', help='Customer handle (for --scrape)')
    scrape_group.add_argument('--customers', help='Comma-separated customer handles (for --scrape-all)')
    scrape_group.add_argument('--username', help='Admin username')
    scrape_group.add_argument('--password', help='Admin password')
    scrape_group.add_argument('--output', default='knowledge_base',
                             help='Output directory (default: knowledge_base)')
    scrape_group.add_argument('--export-md', action='store_true',
                             help='Export markdown reports')
    
    # Build options
    build_group = parser.add_argument_group('Build Options')
    build_group.add_argument('--build', action='store_true',
                            help='Build unified database from scraped data')
    build_group.add_argument('--input-dir', default='knowledge_base',
                            help='Input directory with customer databases')
    build_group.add_argument('--output-db', default='unified_knowledge_base.db',
                            help='Output unified database path')
    
    # Query options
    query_group = parser.add_argument_group('Query Options')
    query_group.add_argument('--search', help='Search for tickets')
    query_group.add_argument('--similar', help='Find similar issues (comma-separated keywords)')
    query_group.add_argument('--category', help='Get resolutions for category')
    query_group.add_argument('--stats', action='store_true',
                            help='Show statistics')
    query_group.add_argument('--customers-list', action='store_true',
                            help='Show customer overview')
    
    # Workflow options
    workflow_group = parser.add_argument_group('Workflow Options')
    workflow_group.add_argument('--full', action='store_true',
                               help='Full workflow: scrape + build + query')
    workflow_group.add_argument('--guide', action='store_true',
                               help='Show quick start guide')
    
    args = parser.parse_args()
    
    # Show guide if no arguments or --guide
    if len(sys.argv) == 1 or args.guide:
        quick_start_guide()
        return 0
    
    success = True
    
    # Full workflow
    if args.full:
        if not args.customer or not args.username or not args.password:
            print("❌ --full requires --customer, --username, and --password")
            return 1
        
        # Step 1: Scrape
        cmd = [
            'python', 'ticket_scraper.py',
            '--customer', args.customer,
            '--username', args.username,
            '--password', args.password,
            '--output', args.output
        ]
        if args.export_md:
            cmd.append('--export-md')
        
        if not run_command(cmd, f"Scraping tickets for {args.customer}"):
            return 1
        
        # Step 2: Build
        cmd = [
            'python', 'build_unified_kb.py',
            '--input-dir', args.input_dir,
            '--output-db', args.output_db
        ]
        if args.stats:
            cmd.append('--stats')
        
        if not run_command(cmd, "Building unified knowledge base"):
            return 1
        
        # Step 3: Query (if stats requested)
        if args.stats:
            cmd = [
                'python', 'unified_knowledge_base.py',
                '--db', args.output_db,
                '--stats'
            ]
            run_command(cmd, "Showing statistics")
        
        print("\n" + "="*60)
        print("✅ FULL WORKFLOW COMPLETED!")
        print("="*60)
        print(f"\n📊 Knowledge base ready: {args.output_db}")
        print("\n💡 Try these queries:")
        print(f"  python unified_knowledge_base.py --db {args.output_db} --search 'phone'")
        print(f"  python unified_knowledge_base.py --db {args.output_db} --stats")
        print(f"  python unified_knowledge_base.py --db {args.output_db} --customers")
        
        return 0
    
    # Individual operations
    
    # Scrape single customer
    if args.scrape:
        if not args.customer or not args.username or not args.password:
            print("❌ --scrape requires --customer, --username, and --password")
            return 1
        
        cmd = [
            'python', 'ticket_scraper.py',
            '--customer', args.customer,
            '--username', args.username,
            '--password', args.password,
            '--output', args.output
        ]
        if args.export_md:
            cmd.append('--export-md')
        
        success = run_command(cmd, f"Scraping tickets for {args.customer}")
    
    # Scrape multiple customers
    elif args.scrape_all:
        if not args.customers or not args.username or not args.password:
            print("❌ --scrape-all requires --customers, --username, and --password")
            return 1
        
        customer_list = [c.strip() for c in args.customers.split(',')]
        
        for i, customer in enumerate(customer_list, 1):
            print(f"\n[{i}/{len(customer_list)}] Processing {customer}")
            
            cmd = [
                'python', 'ticket_scraper.py',
                '--customer', customer,
                '--username', args.username,
                '--password', args.password,
                '--output', args.output
            ]
            if args.export_md:
                cmd.append('--export-md')
            
            if not run_command(cmd, f"Scraping {customer}"):
                print(f"⚠️  Failed to scrape {customer}, continuing...")
                continue
        
        print(f"\n✅ Scraped {len(customer_list)} customers")
    
    # Build unified database
    elif args.build:
        cmd = [
            'python', 'build_unified_kb.py',
            '--input-dir', args.input_dir,
            '--output-db', args.output_db
        ]
        if args.stats:
            cmd.append('--stats')
        
        success = run_command(cmd, "Building unified knowledge base")
    
    # Query operations
    elif args.search or args.similar or args.category or args.stats or args.customers_list:
        if not Path(args.output_db).exists():
            print(f"❌ Database not found: {args.output_db}")
            print(f"\n💡 Run these commands first:")
            print(f"  1. python kb_quickstart.py --scrape --customer CUSTOMER --username admin --password pass")
            print(f"  2. python kb_quickstart.py --build")
            return 1
        
        cmd = ['python', 'unified_knowledge_base.py', '--db', args.output_db]
        
        if args.search:
            cmd.extend(['--search', args.search])
            success = run_command(cmd, f"Searching for: {args.search}")
        elif args.similar:
            cmd.extend(['--similar', args.similar])
            success = run_command(cmd, f"Finding similar issues: {args.similar}")
        elif args.category:
            cmd.extend(['--category', args.category])
            success = run_command(cmd, f"Getting resolutions for: {args.category}")
        elif args.stats:
            cmd.append('--stats')
            success = run_command(cmd, "Getting statistics")
        elif args.customers_list:
            cmd.append('--customers')
            success = run_command(cmd, "Getting customer overview")
    
    else:
        print("❌ No operation specified. Use --help for options or --guide for quick start.")
        return 1
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
