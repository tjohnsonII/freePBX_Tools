# 123.NET Ticket Knowledge Base System

## Overview

A comprehensive system for scraping, storing, and querying customer support tickets from 123.NET admin interface. Build a searchable knowledge base to identify patterns, find solutions faster, and improve customer support.

## What It Does

1. **Scrapes tickets** from 123.NET admin interface for each customer
2. **Stores in SQLite databases** - both per-customer and unified across all customers
3. **Auto-categorizes issues** - Network, Phone/VoIP, Hardware, Configuration, Billing, Critical
4. **Extracts keywords** for easy searching
5. **Finds patterns** - recurring issues, common resolutions, resolution times
6. **Cross-customer search** - "Has any customer had this issue before?"

## Quick Start

### Option 1: Interactive Quick Start (Easiest)

```bash
# Show guide and options
python kb_quickstart.py --guide

# Scrape one customer and build knowledge base
python kb_quickstart.py --full \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --stats
```

### Option 2: Step-by-Step

```bash
# Step 1: Scrape tickets for a customer
python ticket_scraper.py \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --output knowledge_base \
  --export-md

# Step 2: Build unified knowledge base
python build_unified_kb.py \
  --input-dir knowledge_base \
  --output-db unified_knowledge_base.db \
  --stats

# Step 3: Query the knowledge base
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phone not working"
```

## Files Created

### Per-Customer Databases (Individual Analysis)
```
knowledge_base/
├── ARBOR_NETWORKS_tickets.db       # SQLite database
├── ARBOR_NETWORKS_tickets.json     # JSON export
├── ARBOR_NETWORKS_knowledge_base.md # Markdown report
├── CUSTOMER2_tickets.db
└── ...
```

### Unified Knowledge Base (Cross-Customer Analysis)
```
unified_knowledge_base.db            # ALL customers in one database
```

## Key Features

### 🔍 Search Across All Customers
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phones not registering"
```
Find every ticket across all customers matching your query.

### 🎯 Find Similar Issues
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --similar "network,outage,down"
```
Find tickets with similar problems using keyword matching.

### 💡 Common Resolutions by Category
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --category "Phone/VoIP"
```
See what solutions work most often for specific issue types.

### 📊 Statistics & Patterns
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats
```
View global statistics: ticket counts, categories, resolution times, top keywords.

### 👥 Customer Health Overview
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --customers
```
See which customers have most open issues and average resolution times.

## Tools Included

| Tool | Purpose | Usage |
|------|---------|-------|
| `ticket_scraper.py` | Scrape tickets from 123.NET | Per-customer scraping |
| `build_unified_kb.py` | Build unified database | Combine all customers |
| `unified_knowledge_base.py` | Query unified database | Search & analyze |
| `query_ticket_kb.py` | Query per-customer database | Single customer focus |
| `kb_quickstart.py` | One-command workflows | Easy getting started |
| `kb_examples.py` | Example usage patterns | Learn by example |

## Database Schema

### Per-Customer Database
- **tickets** - Ticket metadata (ID, subject, status, priority, dates, resolution)
- **messages** - Full conversation history
- **incidents** - Identified issues/patterns

### Unified Database (Additional Tables)
- **customers** - Customer metadata (ticket counts, avg resolution time)
- **knowledge_articles** - Curated solutions from patterns

## Use Cases

### 1. Customer Calls with Issue
**Scenario**: "Our phones are down"

```bash
# Find similar recent issues
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --similar "phone,down,not working"

# Check common resolutions
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --category "Phone/VoIP"
```

**Result**: See what worked for other customers, resolve faster.

### 2. Identify Training Opportunities
```bash
# See most common issue categories
python unified_knowledge_base.py --db unified_knowledge_base.db --stats
```

**Result**: If "Configuration" issues are #1, team needs more training on setup.

### 3. Customer Health Monitoring
```bash
# See which customers need attention
python unified_knowledge_base.py --db unified_knowledge_base.db --customers
```

**Result**: Proactively reach out to customers with high open ticket counts.

### 4. Build Knowledge Articles
After identifying patterns, create articles:

```python
from unified_knowledge_base import UnifiedKnowledgeBase

kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
kb.create_knowledge_article(
    title="Phones Not Registering After Power Outage",
    category="Phone/VoIP",
    problem="After power loss, phones show 'no service'",
    solution="1. Verify POE switch\n2. Check VLAN\n3. Restart phones",
    related_tickets=["202511100043", "202511090012"]
)
```

## Advanced Usage

### Scrape Multiple Customers at Once
```bash
python kb_quickstart.py --scrape-all \
  --customers CUSTOMER1,CUSTOMER2,CUSTOMER3 \
  --username admin \
  --password your_password
```

### Automated Daily Updates
```bash
#!/bin/bash
# daily_kb_update.sh

# Scrape all customers
for customer in $(cat customer_list.txt); do
    python ticket_scraper.py --customer "$customer" \
      --username admin --password "$(cat password.txt)" \
      --output knowledge_base
done

# Rebuild unified database
python build_unified_kb.py --input-dir knowledge_base

# Export backup
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --export "backups/kb_$(date +%Y%m%d).json"
```

### SQL Queries (Advanced)
```bash
# Find tickets open longer than 7 days
sqlite3 unified_knowledge_base.db "
  SELECT customer_handle, ticket_id, subject,
         CAST(JULIANDAY('now') - JULIANDAY(created_date) AS INT) as days_open
  FROM tickets
  WHERE status NOT IN ('Resolved', 'Closed')
    AND JULIANDAY('now') - JULIANDAY(created_date) > 7
  ORDER BY days_open DESC;
"
```

## Storage Requirements

- **Per customer** (100 tickets): ~1-4 MB
- **Unified database** (100 customers × 100 tickets): ~50-200 MB
- **Backups**: ~20-100 MB per export

## Documentation

- **[Knowledge Base Guide](docs/KNOWLEDGE_BASE_GUIDE.md)** - Complete usage guide
- **[Storage Architecture](docs/STORAGE_ARCHITECTURE.md)** - How data is stored
- **`kb_examples.py`** - Working code examples

## Requirements

```bash
pip install -r requirements.txt
```

Required packages:
- `requests` - HTTP requests for scraping
- `beautifulsoup4` - HTML parsing
- `sqlite3` - Database (included with Python)

## Troubleshooting

### "No customer databases found"
**Solution**: Run `ticket_scraper.py` first to create customer databases.

### "Database not found"
**Solution**: Run `build_unified_kb.py` to create unified database.

### Search returns nothing
**Solution**: Use broader keywords. Search is case-insensitive and uses partial matching.

### Scraping fails
**Solution**: Check credentials, verify 123.NET admin access, check network connectivity.

## Examples

### Example 1: Search for Network Issues
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --search "network outage"
```

Output:
```
[ARBOR_NETWORKS] Ticket #202511100043
  Subject: Network intermittent - packet loss
  Status: Resolved | Priority: High
  Resolution: ISP issue - resolved by Comcast after 2 hours

[CUSTOMER2] Ticket #202511090088
  Subject: Complete network outage
  Status: Resolved | Priority: Critical
  Resolution: Router reboot resolved issue
```

### Example 2: Statistics
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db --stats
```

Output:
```
Total Tickets: 487
Total Customers: 12
Average Resolution Time: 2.3 days

By Category:
  Network/Connectivity: 123
  Phone/VoIP: 156
  Hardware: 89
  Configuration: 67

Top Keywords:
  phone: 156 occurrences
  network: 123 occurrences
  outage: 89 occurrences
```

## Integration

### Add to Web Dashboard
```python
from unified_knowledge_base import UnifiedKnowledgeBase

@app.route('/api/kb/search', methods=['POST'])
def kb_search():
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    results = kb.search_across_customers(request.json['query'])
    return jsonify(results)
```

### CLI Helper
```python
# Add to your shell profile
alias kbsearch='python unified_knowledge_base.py --db unified_knowledge_base.db --search'
alias kbstats='python unified_knowledge_base.py --db unified_knowledge_base.db --stats'
```

## Support

For questions or issues:
1. Check `docs/KNOWLEDGE_BASE_GUIDE.md`
2. Run example scripts: `python kb_examples.py`
3. View storage details: `docs/STORAGE_ARCHITECTURE.md`

## License

Part of the FreePBX Tools suite for 123.NET internal use.
