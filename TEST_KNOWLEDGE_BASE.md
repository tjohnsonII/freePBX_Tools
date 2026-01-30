# Testing the Knowledge Base Scraper

## How to run webscraper

Prefer module execution from the repo root:

```powershell
python -m webscraper.ultimate_scraper --help
python -m webscraper.run_discovery --help
```

Legacy scripts remain under `webscraper/legacy/`:

```powershell
python webscraper/legacy/ticket_scraper.py --help
```

Store cookies and local outputs in `.local/` (gitignored), e.g. `.local/cookies.json`.

## Prerequisites

Before testing, ensure you have:
- [ ] Admin credentials for 123.NET admin interface
- [ ] At least one customer handle to test with
- [ ] Python 3.6+ installed
- [ ] Required packages installed

### Install Dependencies

```powershell
# Install required packages
pip install requests beautifulsoup4
```

## Test Plan

### Phase 1: Test Single Customer Scraping (5-10 minutes)

#### Step 1: Scrape One Customer

```powershell
# Basic scrape (minimal output)
python webscraper/legacy/ticket_scraper.py `
  --customer ARBOR_NETWORKS `
  --username admin `
  --password your_password `
  --output knowledge_base
```

**Expected Output**:
```
✅ Logged in successfully
📥 Fetching tickets for customer: ARBOR_NETWORKS
🔍 Processing tickets...
  [1/47] Processing ticket 202511100043...
  [2/47] Processing ticket 202511090088...
  ...
📊 Analyzing patterns...
✅ Knowledge base created successfully!
   Database: knowledge_base\ARBOR_NETWORKS_tickets.db
   JSON: knowledge_base\ARBOR_NETWORKS_tickets.json
```

**Verify Files Created**:
```powershell
# Check that files were created
dir knowledge_base\ARBOR_NETWORKS*

# Expected files:
# - ARBOR_NETWORKS_tickets.db     (SQLite database)
# - ARBOR_NETWORKS_tickets.json   (JSON export)
```

#### Step 2: Add Markdown Export (Optional)

```powershell
# Scrape with markdown report
python webscraper/legacy/ticket_scraper.py `
  --customer ARBOR_NETWORKS `
  --username admin `
  --password your_password `
  --output knowledge_base `
  --export-md
```

**Expected Additional File**:
```
knowledge_base\ARBOR_NETWORKS_knowledge_base.md
```

#### Step 3: Verify Database Contents

```powershell
# Install sqlite3 command-line tool (if not already installed)
# Or use Python to check

# Check with Python
python -c "import sqlite3; conn = sqlite3.connect('knowledge_base/ARBOR_NETWORKS_tickets.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM tickets'); print(f'Tickets: {cursor.fetchone()[0]}'); cursor.execute('SELECT COUNT(*) FROM messages'); print(f'Messages: {cursor.fetchone()[0]}'); conn.close()"
```

**Expected Output**:
```
Tickets: 47
Messages: 312
```

### Phase 2: Test Database Queries (5 minutes)

#### Step 1: Query Single Customer Database

```powershell
# Search for specific term
python query_ticket_kb.py `
  --db knowledge_base\ARBOR_NETWORKS_tickets.db `
  --search "phone"
```

**Expected Output**:
```
🔍 Searching for: phone

Ticket #202511100043: Phones not registering
  Status: Resolved | Priority: High
  Category: Phone/VoIP
  Keywords: phone,registration,sip
  Resolution: Rebooted POE switch...
```

#### Step 2: Get Statistics

```powershell
# Get customer statistics
python query_ticket_kb.py `
  --db knowledge_base\ARBOR_NETWORKS_tickets.db `
  --stats
```

**Expected Output**:
```
📊 Ticket Statistics

Total Tickets: 47
By Status:
  Resolved: 42
  Open: 5

By Category:
  Phone/VoIP: 18
  Network/Connectivity: 12
  Hardware: 9
  Configuration: 8

Top Keywords:
  phone: 18
  network: 12
  outage: 8
```

### Phase 3: Test Unified Database (10 minutes)

#### Step 1: Scrape Multiple Customers (if available)

```powershell
# Scrape additional customers
python webscraper/legacy/ticket_scraper.py `
  --customer CUSTOMER2 `
  --username admin `
  --password your_password `
  --output knowledge_base

python webscraper/legacy/ticket_scraper.py `
  --customer CUSTOMER3 `
  --username admin `
  --password your_password `
  --output knowledge_base
```

#### Step 2: Build Unified Database

```powershell
# Build unified database from all customers
python build_unified_kb.py `
  --input-dir knowledge_base `
  --output-db unified_knowledge_base.db `
  --stats
```

**Expected Output**:
```
📦 Found 3 customer database(s)
🎯 Building unified knowledge base: unified_knowledge_base.db

📥 Importing ARBOR_NETWORKS...
   ✅ Imported 47 tickets from ARBOR_NETWORKS
📥 Importing CUSTOMER2...
   ✅ Imported 83 tickets from CUSTOMER2
📥 Importing CUSTOMER3...
   ✅ Imported 52 tickets from CUSTOMER3

✅ Unified knowledge base created successfully!
   Database: unified_knowledge_base.db

============================================================
📊 KNOWLEDGE BASE STATISTICS
============================================================

Total Tickets: 182
Total Customers: 3
Average Resolution Time: 2.1 days

Status               Count     
------------------------------
Resolved             158       
Open                 18        
Closed               6         
```

#### Step 3: Query Unified Database

```powershell
# Search across ALL customers
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --search "phone not working"
```

**Expected Output**:
```
🔍 Searching for: phone not working

[ARBOR_NETWORKS] Ticket #202511100043: Phones not registering
  Status: Resolved | Priority: High | Category: Phone/VoIP
  Resolution: Rebooted POE switch, all phones came back online

[CUSTOMER2] Ticket #202511090088: Phone system down
  Status: Resolved | Priority: Critical | Category: Phone/VoIP
  Resolution: FreePBX service was stopped, restarted via systemctl

[CUSTOMER3] Ticket #202511080055: Cannot make outbound calls
  Status: Open | Priority: Medium | Category: Phone/VoIP
```

### Phase 4: Test Advanced Features (5 minutes)

#### Test Similar Issues Search

```powershell
# Find similar issues using keywords
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --similar "network,outage,down"
```

#### Test Category Resolutions

```powershell
# Get common resolutions for a category
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --category "Phone/VoIP"
```

**Expected Output**:
```
📊 Common resolutions for category: Phone/VoIP

1. Rebooted POE switch, phones registered successfully
   Frequency: 8 tickets
   Customers affected: 5
   Avg resolution time: 0.3 days

2. Restarted FreePBX service via systemctl
   Frequency: 5 tickets
   Customers affected: 3
   Avg resolution time: 0.1 days
```

#### Test Customer Overview

```powershell
# View customer health
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --customers
```

**Expected Output**:
```
👥 Customer Overview

ARBOR_NETWORKS
  Total: 47 | Open: 2 | Resolved: 45
  Avg resolution: 1.8 days
  Common issues: Phone/VoIP, Network/Connectivity, Hardware

CUSTOMER2
  Total: 83 | Open: 5 | Resolved: 78
  Avg resolution: 2.3 days
  Common issues: Network/Connectivity, Configuration, Phone/VoIP
```

### Phase 5: Quick Start Test (2 minutes)

#### Test Full Workflow in One Command

```powershell
# Full workflow: scrape + build + query
python kb_quickstart.py --full `
  --customer TEST_CUSTOMER `
  --username admin `
  --password your_password `
  --stats
```

**Expected Output**:
```
============================================================
📋 Scraping tickets for TEST_CUSTOMER
============================================================
Command: python webscraper/legacy/ticket_scraper.py --customer TEST_CUSTOMER ...

✅ Scraping tickets for TEST_CUSTOMER completed successfully!

============================================================
📋 Building unified knowledge base
============================================================
Command: python build_unified_kb.py --input-dir knowledge_base ...

✅ Building unified knowledge base completed successfully!

============================================================
📋 Showing statistics
============================================================
Command: python unified_knowledge_base.py --db unified_knowledge_base.db --stats

✅ Showing statistics completed successfully!

============================================================
✅ FULL WORKFLOW COMPLETED!
============================================================

📊 Knowledge base ready: unified_knowledge_base.db
```

## Troubleshooting Common Issues

### Issue 1: Login Failed

**Symptoms**:
```
❌ Failed to login
```

**Solutions**:
1. Verify credentials are correct
2. Check network connectivity to secure.123.net
3. Verify admin user has access to customer portal
4. Try logging in manually via browser first

**Debug**:
```powershell
# Test with verbose output (add to webscraper/legacy/ticket_scraper.py temporarily)
# Or check if URL is accessible
curl https://secure.123.net/cgi-bin/web_interface/admin/login.cgi
```

### Issue 2: No Tickets Found

**Symptoms**:
```
Found 0 tickets
```

**Solutions**:
1. Verify customer handle is correct (case-sensitive)
2. Check if customer actually has tickets in the system
3. Verify URL structure matches actual 123.NET interface
4. Check HTML parsing - page structure may have changed

**Debug**:
```powershell
# Check what the scraper is seeing (add print statements)
# Look at the HTML structure manually in browser DevTools
```

### Issue 3: HTML Parsing Errors

**Symptoms**:
```
AttributeError: 'NoneType' object has no attribute 'text'
```

**Solutions**:
1. 123.NET may have changed their HTML structure
2. Check the HTML selectors in `webscraper/legacy/ticket_scraper.py`
3. Compare with actual page structure in browser DevTools
4. Update selectors if needed

**Debug**:
```python
# Add debug output to webscraper/legacy/ticket_scraper.py
print(f"HTML: {soup.prettify()}")
```

### Issue 4: Database Already Exists

**Symptoms**:
```
sqlite3.IntegrityError: UNIQUE constraint failed
```

**Solution**:
```powershell
# Delete existing database and re-scrape
rm knowledge_base\CUSTOMER_tickets.db
python webscraper/legacy/ticket_scraper.py --customer CUSTOMER ...
```

### Issue 5: Import Errors

**Symptoms**:
```
ModuleNotFoundError: No module named 'requests'
```

**Solution**:
```powershell
# Install missing dependencies
pip install requests beautifulsoup4
```

## Validation Checklist

After testing, verify:

- [ ] Tickets are scraped successfully
- [ ] Database files are created in `knowledge_base/` directory
- [ ] SQLite database contains tickets, messages, incidents tables
- [ ] JSON export is valid JSON format
- [ ] Markdown report is human-readable (if --export-md used)
- [ ] Query tools can search the database
- [ ] Statistics are calculated correctly
- [ ] Unified database combines multiple customers
- [ ] Cross-customer search works
- [ ] Category-based resolution lookup works
- [ ] Customer overview shows correct stats

## Performance Benchmarks

Expected performance:
- **Scraping**: ~50-100 tickets in 1-2 minutes
- **Building unified DB**: ~1000 tickets in 5-10 seconds
- **Queries**: <1 second for most queries
- **Statistics**: <2 seconds even with 10,000+ tickets

## Sample Test Data

If you want to test without real data first, you can create sample data:

```powershell
# Create a test script (test_sample_data.py)
python -c "
import sqlite3
conn = sqlite3.connect('knowledge_base/TEST_CUSTOMER_tickets.db')
cursor = conn.cursor()

# Create tables
cursor.execute('''CREATE TABLE tickets (
    id INTEGER PRIMARY KEY, ticket_id TEXT, subject TEXT, 
    status TEXT, priority TEXT, created_date TEXT, 
    resolved_date TEXT, resolution TEXT, category TEXT, keywords TEXT
)''')

# Insert sample ticket
cursor.execute('''INSERT INTO tickets VALUES 
    (1, '202511100001', 'Test phone issue', 'Resolved', 'High', 
     '2025-11-10', '2025-11-10', 'Rebooted device', 'Phone/VoIP', 'phone,test')
''')

conn.commit()
conn.close()
print('✅ Test database created')
"
```

## Next Steps After Testing

Once testing is successful:

1. **Create customer list**: Make a file with all customer handles
2. **Automate scraping**: Create script to scrape all customers
3. **Schedule daily runs**: Set up Windows Task Scheduler
4. **Build web interface**: Add knowledge base queries to web dashboard
5. **Create alerts**: Monitor for critical issues
6. **Train team**: Show support team how to query the knowledge base

## Quick Reference Commands

```powershell
# Scrape single customer
python webscraper/legacy/ticket_scraper.py --customer CUSTOMER --username admin --password pass --output knowledge_base

# Build unified database
python build_unified_kb.py --input-dir knowledge_base --stats

# Search unified database
python unified_knowledge_base.py --db unified_knowledge_base.db --search "query"

# Get statistics
python unified_knowledge_base.py --db unified_knowledge_base.db --stats

# Full workflow
python kb_quickstart.py --full --customer CUSTOMER --username admin --password pass --stats
```

## Support

If you encounter issues not covered here:
1. Check `docs/KNOWLEDGE_BASE_GUIDE.md` for detailed documentation
2. Run `python kb_examples.py` to see working examples
3. Check `docs/FAQ_KNOWLEDGE_BASE.md` for common questions
