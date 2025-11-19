#!/usr/bin/env python3
"""
Knowledge Base System - Self Test
---------------------------------
This script performs a comprehensive self-test of the knowledge base system.
It checks Python version, dependencies, required files, documentation, module imports,
database creation, and the UnifiedKnowledgeBase class. It provides a summary and next steps.

====================================
Variable Map Legend (Key Variables)
====================================

results (list[tuple]): List of (test_name, result) for all self-tests
version (sys.version_info): Python version info
required_packages (dict): Required Python packages and their descriptions
required_files (list[str]): List of required KB system source files
doc_files (list[str]): List of documentation files (optional)
modules (dict): Module names and descriptions for import tests
test_db, test_unified_kb.db (Path): Temporary SQLite database files for tests
conn, cursor: SQLite connection and cursor objects
tables, indexes (list[str]): List of table/index names in test databases
missing (list[str]): List of missing required tables
kb (UnifiedKnowledgeBase): Instance of the knowledge base class
count (int): Row count for DB test
test_name (str): Name of each test in summary
passed, total (int): Number of tests passed/total

"""

import sys
from pathlib import Path
import subprocess

def check_python_version():
    """
    Check that the Python version is 3.6 or higher.
    Prints the version and returns True if compatible, False otherwise.
    """
    print("\n" + "="*60)
    print("1. Checking Python Version")
    print("="*60)
    
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major >= 3 and version.minor >= 6:
        print("✅ Python version is compatible (3.6+)")
        return True
    else:
        print("❌ Python 3.6+ required")
        return False

def check_dependencies():
    """
    Check that all required Python packages are installed.
    Prints status for each and returns True if all are present.
    """
    print("\n" + "="*60)
    print("2. Checking Dependencies")
    print("="*60)
    
    required_packages = {
        'requests': 'HTTP requests',
        'bs4': 'BeautifulSoup HTML parsing',
        'sqlite3': 'SQLite database'
    }
    
    all_ok = True
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"✅ {package:<15} - {description}")
        except ImportError:
            print(f"❌ {package:<15} - {description} (MISSING)")
            all_ok = False
    
    if not all_ok:
        print("\n💡 Install missing packages:")
        print("   pip install requests beautifulsoup4")
    
    return all_ok

def check_files():
    """
    Check that all required source files for the KB system exist.
    Prints status for each and returns True if all are present.
    """
    print("\n" + "="*60)
    print("3. Checking Required Files")
    print("="*60)
    
    required_files = [
        'ticket_scraper.py',
        'unified_knowledge_base.py',
        'build_unified_kb.py',
        'query_ticket_kb.py',
        'kb_quickstart.py',
        'kb_examples.py'
    ]
    
    all_ok = True
    for filename in required_files:
        filepath = Path(filename)
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"✅ {filename:<30} ({size:,} bytes)")
        else:
            print(f"❌ {filename:<30} (MISSING)")
            all_ok = False
    
    return all_ok

def check_documentation():
    """
    Check that documentation files exist (optional, not required to pass).
    Prints status for each file.
    """
    print("\n" + "="*60)
    print("4. Checking Documentation")
    print("="*60)
    
    doc_files = [
        'docs/KNOWLEDGE_BASE_GUIDE.md',
        'docs/STORAGE_ARCHITECTURE.md',
        'docs/KNOWLEDGE_BASE_README.md',
        'docs/KB_STORAGE_VISUAL.md',
        'docs/FAQ_KNOWLEDGE_BASE.md',
        'TEST_KNOWLEDGE_BASE.md'
    ]
    
    all_ok = True
    for filename in doc_files:
        filepath = Path(filename)
        if filepath.exists():
            print(f"✅ {filename}")
        else:
            print(f"⚠️  {filename} (optional)")
    
    return True  # Documentation is optional

def test_imports():
    """
    Attempt to import all major KB modules to verify they are importable.
    Prints status for each and returns True if all imports succeed.
    """
    print("\n" + "="*60)
    print("5. Testing Module Imports")
    print("="*60)
    
    modules = {
        'unified_knowledge_base': 'UnifiedKnowledgeBase',
        'build_unified_kb': 'build script',
        'kb_quickstart': 'quickstart tool',
        'kb_examples': 'examples'
    }
    
    all_ok = True
    for module_name, description in modules.items():
        try:
            __import__(module_name)
            print(f"✅ {module_name:<30} ({description})")
        except Exception as e:
            print(f"❌ {module_name:<30} - {str(e)}")
            all_ok = False
    
    return all_ok

def test_database_creation():
    """
    Test that a SQLite database can be created, written to, and queried.
    Returns True if all steps succeed.
    """
    print("\n" + "="*60)
    print("6. Testing Database Creation")
    print("="*60)
    
    try:
        import sqlite3
        
        # Create test database
        test_db = Path('test_kb.db')
        if test_db.exists():
            test_db.unlink()
        
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        
        # Create test table
        cursor.execute('''
            CREATE TABLE test_tickets (
                id INTEGER PRIMARY KEY,
                ticket_id TEXT,
                subject TEXT
            )
        ''')
        
        # Insert test data
        cursor.execute('''
            INSERT INTO test_tickets (ticket_id, subject)
            VALUES ('TEST001', 'Test Ticket')
        ''')
        
        conn.commit()
        
        # Verify data
        cursor.execute('SELECT COUNT(*) FROM test_tickets')
        count = cursor.fetchone()[0]
        
        conn.close()
        
        # Cleanup
        test_db.unlink()
        
        if count == 1:
            print("✅ Database creation and queries work correctly")
            return True
        else:
            print("❌ Database test failed - unexpected count")
            return False
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_unified_kb_class():
    """
    Test the UnifiedKnowledgeBase class for correct DB/table creation and connection.
    Returns True if all checks pass.
    """
    print("\n" + "="*60)
    print("7. Testing UnifiedKnowledgeBase Class")
    print("="*60)
    
    try:
        from unified_knowledge_base import UnifiedKnowledgeBase
        
        # Create test database
        test_db = Path('test_unified_kb.db')
        if test_db.exists():
            test_db.unlink()
        
        # Initialize
        kb = UnifiedKnowledgeBase(str(test_db))
        print("✅ UnifiedKnowledgeBase initialized")
        
        # Check tables exist
        if not kb.conn:
            print("❌ Database connection failed")
            return False
        
        cursor = kb.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['tickets', 'messages', 'incidents', 'customers', 'knowledge_articles']
        missing = [t for t in required_tables if t not in tables]
        
        if not missing:
            print(f"✅ All required tables created: {', '.join(required_tables)}")
        else:
            print(f"❌ Missing tables: {', '.join(missing)}")
            kb.close()
            return False
        
        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        if indexes:
            print(f"✅ Indexes created: {len(indexes)} indexes")
        else:
            print("⚠️  No indexes found (may affect query performance)")
        
        kb.close()
        
        # Cleanup
        test_db.unlink()
        
        print("✅ UnifiedKnowledgeBase class works correctly")
        return True
        
    except Exception as e:
        print(f"❌ UnifiedKnowledgeBase test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_next_steps():
    """
    Print next steps and usage instructions for the knowledge base system after a successful self-test.
    """
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    
    print("\n✅ System self-test completed!")
    print("\n📋 To test with real data:")
    print("\n1. Get your 123.NET admin credentials")
    print("2. Choose a customer to test with")
    print("3. Run the scraper:")
    print("\n   python ticket_scraper.py \\")
    print("     --customer CUSTOMER_HANDLE \\")
    print("     --username admin \\")
    print("     --password your_password \\")
    print("     --output knowledge_base")
    
    print("\n4. Build unified database:")
    print("\n   python build_unified_kb.py \\")
    print("     --input-dir knowledge_base \\")
    print("     --stats")
    
    print("\n5. Query the knowledge base:")
    print("\n   python unified_knowledge_base.py \\")
    print("     --db unified_knowledge_base.db \\")
    print("     --search 'phone not working'")
    
    print("\n📖 Documentation:")
    print("   - TEST_KNOWLEDGE_BASE.md - Complete test guide")
    print("   - docs/KNOWLEDGE_BASE_GUIDE.md - Full usage guide")
    print("   - docs/FAQ_KNOWLEDGE_BASE.md - Common questions")
    
    print("\n💡 Quick start (all in one command):")
    print("\n   python kb_quickstart.py --full \\")
    print("     --customer CUSTOMER_HANDLE \\")
    print("     --username admin \\")
    print("     --password your_password \\")
    print("     --stats")
    
    print("\n" + "="*60)

def main():
    """
    Run all self-tests for the knowledge base system, print a summary, and show next steps.
    Returns 0 if all tests pass, 1 otherwise.
    """
    print("\n" + "="*70)
    print(" "*15 + "KNOWLEDGE BASE SYSTEM - SELF TEST")
    print("="*70)
    
    results = []
    
    # Run all tests
    results.append(("Python Version", check_python_version()))
    results.append(("Dependencies", check_dependencies()))
    results.append(("Required Files", check_files()))
    results.append(("Documentation", check_documentation()))
    results.append(("Module Imports", test_imports()))
    results.append(("Database Creation", test_database_creation()))
    results.append(("UnifiedKnowledgeBase Class", test_unified_kb_class()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<10} {test_name}")
    
    print("\n" + "-"*70)
    print(f"Results: {passed}/{total} tests passed")
    print("-"*70)
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        show_next_steps()
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("\n💡 Common fixes:")
        print("   - Install dependencies: pip install requests beautifulsoup4")
        print("   - Check Python version: python --version")
        print("   - Verify all files are present")
        return 1

if __name__ == '__main__':
    sys.exit(main())
