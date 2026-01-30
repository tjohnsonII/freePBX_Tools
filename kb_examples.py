#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
example_search():
    Demonstrate searching the knowledge base for a query.
example_similar_issues():
    Show how to find similar issues in the knowledge base.
example_common_resolutions():
    Display common resolutions for a given issue type.
example_statistics():
    Print statistics about the knowledge base.
example_customer_overview():
    Show an overview of tickets for a specific customer.
example_create_knowledge_article():
    Demonstrate creating a new knowledge article.
example_practical_workflow():
    Walk through a practical support workflow using the KB.
main():
    Run all example functions for demonstration.
"""
"""
Example: Using the Unified Knowledge Base
Shows common use cases and query patterns
"""

from unified_knowledge_base import UnifiedKnowledgeBase
from pathlib import Path

def example_search():
    """Example: Search for phone issues across all customers"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Search for 'phone not registering'")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    results = kb.search_across_customers('phone not registering', limit=5)
    
    print(f"\nFound {len(results)} matching tickets:\n")
    for r in results:
        print(f"[{r['customer']}] Ticket #{r['ticket_id']}")
        print(f"  Subject: {r['subject']}")
        print(f"  Status: {r['status']} | Priority: {r['priority']}")
        if r['resolution']:
            print(f"  Resolution: {r['resolution'][:100]}...")
        print()
    
    kb.close()

def example_similar_issues():
    """Example: Find similar network issues"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Find similar network outage issues")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    
    # Search for tickets with these keywords
    keywords = ['network', 'outage', 'down', 'internet']
    results = kb.find_similar_issues_across_customers(keywords, limit=5)
    
    print(f"\nFound {len(results)} similar issues:\n")
    for r in results:
        print(f"[{r['customer']}] {r['subject']}")
        print(f"  Category: {r['category']} | Relevance Score: {r['relevance']}")
        if r['resolution']:
            print(f"  Resolution: {r['resolution'][:100]}...")
        print()
    
    kb.close()

def example_common_resolutions():
    """Example: Get common solutions for a category"""
    print("\n" + "="*60)
    print("EXAMPLE 3: Common solutions for Phone/VoIP issues")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    results = kb.get_common_resolutions_by_category('Phone/VoIP')
    
    print(f"\nTop {len(results)} solutions:\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['resolution'][:150]}")
        print(f"   Used {r['frequency']} times across {len(r['customers_affected'])} customer(s)")
        if r['avg_days_to_resolve']:
            print(f"   Average time to resolve: {r['avg_days_to_resolve']} days")
        print()
    
    kb.close()

def example_statistics():
    """Example: Global knowledge base statistics"""
    print("\n" + "="*60)
    print("EXAMPLE 4: Knowledge Base Statistics")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    stats = kb.get_global_statistics()
    
    print(f"\nTotal Tickets: {stats['total_tickets']:,}")
    print(f"Total Customers: {stats['total_customers']}")
    
    if stats['avg_resolution_days']:
        print(f"Average Resolution Time: {stats['avg_resolution_days']} days")
    
    print("\nTop 5 Categories:")
    for category, count in list(stats['by_category'].items())[:5]:
        print(f"  {category}: {count}")
    
    print("\nTop 10 Keywords:")
    for keyword, count in stats['top_keywords'][:10]:
        print(f"  {keyword}: {count} occurrences")
    
    kb.close()

def example_customer_overview():
    """Example: Customer health dashboard"""
    print("\n" + "="*60)
    print("EXAMPLE 5: Customer Health Overview")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    customers = kb.get_customer_overview()
    
    print(f"\nTracking {len(customers)} customers:\n")
    
    # Sort by open ticket percentage
    customers_sorted = sorted(
        customers, 
        key=lambda c: c['open_tickets'] / max(c['total_tickets'], 1), 
        reverse=True
    )
    
    print(f"{'Customer':<25} {'Total':<8} {'Open':<8} {'Resolved':<10} {'Avg Days':<10}")
    print("-" * 70)
    
    for c in customers_sorted[:10]:  # Top 10
        open_pct = (c['open_tickets'] / max(c['total_tickets'], 1)) * 100
        marker = "🚨" if open_pct > 50 else "⚠️" if open_pct > 25 else "✅"
        
        print(f"{marker} {c['customer']:<23} {c['total_tickets']:<8} {c['open_tickets']:<8} "
              f"{c['resolved_tickets']:<10} {c['avg_resolution_days']:<10.1f}")
    
    kb.close()

def example_create_knowledge_article():
    """Example: Create a knowledge article from patterns"""
    print("\n" + "="*60)
    print("EXAMPLE 6: Create Knowledge Article")
    print("="*60)
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    
    # Create an article about a common issue
    article_id = kb.create_knowledge_article(
        title="Phones Not Registering After Power Outage",
        category="Phone/VoIP",
        problem="""After a power outage or network interruption, IP phones 
        display 'no service' or 'unregistered' status. Users cannot make 
        or receive calls.""",
        solution="""
        1. Verify POE switch is powered on and all ports are active
        2. Check VLAN configuration - phones should be on voice VLAN
        3. Verify DHCP is assigning correct option 66 (TFTP server)
        4. Restart phones in sequence (not all at once)
        5. Check FreePBX extension status: asterisk -rx 'sip show peers'
        6. If still failing, check firewall rules for SIP ports (5060, 10000-20000)
        
        Common root causes:
        - POE switch lost config during power loss
        - VLAN mismatch after switch reboot
        - DHCP exhausted IP pool
        - Phones timing out during mass re-registration
        """,
        related_tickets=["202511100043", "202511090012", "202511080088"]
    )
    
    print(f"\n✅ Created knowledge article #{article_id}")
    print("   Title: Phones Not Registering After Power Outage")
    print("   Category: Phone/VoIP")
    print("   Related tickets: 3")
    
    kb.close()

def example_practical_workflow():
    """Example: Real-world troubleshooting workflow"""
    print("\n" + "="*60)
    print("EXAMPLE 7: Troubleshooting Workflow")
    print("="*60)
    
    print("\nScenario: Customer calls - 'Our phones are down'\n")
    
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    
    # Step 1: Find similar recent issues
    print("Step 1: Searching for similar recent issues...")
    results = kb.find_similar_issues_across_customers(['phone', 'down', 'not working'], limit=3)
    
    if results:
        print(f"   Found {len(results)} similar cases:\n")
        for r in results[:3]:
            print(f"   [{r['customer']}] {r['subject']}")
            if r['resolution']:
                print(f"   → Quick fix: {r['resolution'][:80]}...")
    
    # Step 2: Check common resolutions for this category
    print("\nStep 2: Checking common resolutions for Phone/VoIP...")
    resolutions = kb.get_common_resolutions_by_category('Phone/VoIP')
    
    if resolutions:
        print(f"   Top solution (used {resolutions[0]['frequency']} times):")
        print(f"   → {resolutions[0]['resolution'][:100]}...")
    
    # Step 3: Check if this customer has recurring issues
    print("\nStep 3: Checking customer history...")
    print("   (Would query specific customer's past tickets here)")
    
    kb.close()
    
    print("\n✅ Armed with historical data, you can resolve faster!")

def main():
    """Run all examples"""
    
    # Check if database exists
    if not Path('unified_knowledge_base.db').exists():
        print("\n❌ unified_knowledge_base.db not found!")
        print("\nPlease run these commands first:")
        print("  1. python webscraper/legacy/ticket_scraper.py --customer CUSTOMER_NAME --username admin --password pass")
        print("  2. python build_unified_kb.py --input-dir knowledge_base --stats")
        print("\nThen run this example script again.")
        return
    
    print("\n" + "="*60)
    print("UNIFIED KNOWLEDGE BASE - EXAMPLES")
    print("="*60)
    
    try:
        example_search()
        example_similar_issues()
        example_common_resolutions()
        example_statistics()
        example_customer_overview()
        example_create_knowledge_article()
        example_practical_workflow()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("   Make sure the database has data in it.")
    
    print("\n" + "="*60)
    print("For more examples, see: docs/KNOWLEDGE_BASE_GUIDE.md")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
