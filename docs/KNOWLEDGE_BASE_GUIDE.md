# Knowledge Base System - Quick Start Guide

## Overview

The ticket scraping system now has **two database strategies**:

1. **Per-Customer Databases** - Individual `.db` files for focused analysis
2. **Unified Knowledge Base** - Single database combining ALL customers for cross-customer insights

## Directory Structure

```
freepbx-tools/
├── ticket_scraper.py           # Scrapes tickets from 123.NET admin
├── query_ticket_kb.py          # Query individual customer databases
├── unified_knowledge_base.py   # Manage unified database
├── build_unified_kb.py         # Build unified DB from all customers
└── knowledge_base/             # Output directory
    ├── CUSTOMER1_tickets.db
    ├── CUSTOMER1_tickets.json
    ├── CUSTOMER1_knowledge_base.md
    ├── CUSTOMER2_tickets.db
    ├── CUSTOMER2_tickets.json
    └── unified_knowledge_base.db  # ⭐ ALL customers combined
```

## Workflow

### Step 1: Scrape Individual Customers

```bash
# Scrape tickets for one customer
python ticket_scraper.py \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --output knowledge_base \
  --export-md

# Result: Creates knowledge_base/ARBOR_NETWORKS_tickets.db
```

### Step 2: Build Unified Knowledge Base

```bash
# Automatically import ALL customer databases
python build_unified_kb.py \
  --input-dir knowledge_base \
  --output-db unified_knowledge_base.db \
  --stats

# Result: Creates unified_knowledge_base.db with all customers
```

### Step 3: Query the Knowledge Base

```bash
# Search across ALL customers
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phone not registering"

# Find similar issues across customers
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --similar "network,down,outage"

# Get common resolutions for a category
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --category "Phone/VoIP"

# View global statistics
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats

# View customer overview
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --customers

# Export to JSON
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --export kb_export.json
```

## Database Schema

### Unified Database Tables

**tickets** - All tickets from all customers
- `customer_handle` - Which customer this belongs to
- `ticket_id` - Original ticket number
- `subject`, `status`, `priority`
- `created_date`, `resolved_date`
- `resolution` - How it was fixed
- `category` - Auto-categorized (Network, Phone, etc.)
- `keywords` - Extracted keywords for searching
- `message_count` - Number of messages in conversation

**messages** - Full ticket conversation history
- `ticket_id` - Reference to tickets table
- `customer_handle` - Customer identifier
- `author` - Who wrote the message
- `timestamp` - When it was sent
- `content` - Full message text

**incidents** - Identified patterns/issues
- `customer_handle`, `original_ticket_id`
- `incident_type` - Type of issue
- `description`, `severity`
- `discovered_date`

**customers** - Customer metadata
- `customer_handle` - Customer identifier
- `total_tickets`, `open_tickets`, `resolved_tickets`
- `avg_resolution_days` - How fast issues get resolved
- `common_issues` - Most frequent categories
- `last_scrape_date` - When data was last updated

**knowledge_articles** - Curated solutions
- `title`, `category`
- `problem_description` - What the issue is
- `solution` - How to fix it
- `related_ticket_ids` - Evidence/examples
- `affected_customers` - Who has seen this
- `usefulness_score` - Helpfulness rating

## Use Cases

### 1. Find Similar Issues Across Customers

**Problem**: Customer reports "phones not registering"

```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --similar "phone,registration,sip,401"
```

**Result**: Shows all customers who had similar issues with resolutions

### 2. Identify Recurring Problems

**Problem**: Want to see which issues happen most often

```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats
```

**Result**: Top keywords show "network outage" appears 47 times across 12 customers

### 3. Common Resolutions by Category

**Problem**: Network issue - what usually fixes it?

```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --category "Network/Connectivity"
```

**Result**: 
- "Rebooted router" - 23 times, avg 0.5 days to resolve
- "ISP outage - waiting" - 18 times, avg 2.3 days
- "Replaced network cable" - 12 times, avg 1.1 days

### 4. Customer Health Check

**Problem**: Which customers have most open issues?

```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --customers
```

**Result**: Shows each customer's ticket counts and resolution times

### 5. Build Knowledge Articles

**Problem**: Want to document common solutions

```python
from unified_knowledge_base import UnifiedKnowledgeBase

kb = UnifiedKnowledgeBase('unified_knowledge_base.db')

# Create article from pattern
kb.create_knowledge_article(
    title="Phones Not Registering After Power Outage",
    category="Phone/VoIP",
    problem="After power loss, all phones show 'no service'",
    solution="1. Verify POE switch is online\n2. Check VLAN configuration\n3. Restart phones in sequence",
    related_tickets=["202511100043", "202511090012", "202511080088"]
)
```

## Automated Workflows

### Daily Knowledge Base Update

```bash
#!/bin/bash
# update_kb_daily.sh

# Scrape all customers (assuming credentials file)
for customer in $(cat customer_list.txt); do
    python ticket_scraper.py \
      --customer "$customer" \
      --username admin \
      --password "$(cat admin_password.txt)" \
      --output knowledge_base
done

# Rebuild unified database
python build_unified_kb.py \
  --input-dir knowledge_base \
  --output-db unified_knowledge_base.db

# Export reports
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --export "kb_export_$(date +%Y%m%d).json"

echo "✅ Knowledge base updated"
```

### Alert on New Critical Issues

```python
# monitor_critical.py
from unified_knowledge_base import UnifiedKnowledgeBase

kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
results = kb.search_across_customers('critical')

for ticket in results:
    if ticket['status'] == 'Open':
        print(f"🚨 CRITICAL: [{ticket['customer']}] {ticket['subject']}")
```

## Integration with Existing Tools

### Query from Web Dashboard

```python
# In web_manager.py
from unified_knowledge_base import UnifiedKnowledgeBase

@app.route('/api/kb/search', methods=['POST'])
def kb_search():
    data = request.json
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    results = kb.search_across_customers(data['query'])
    return jsonify(results)
```

### CLI Helper Function

```python
# kb_helper.py
def quick_search(query: str):
    """Quick knowledge base search"""
    from unified_knowledge_base import UnifiedKnowledgeBase
    kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
    results = kb.search_across_customers(query, limit=5)
    for r in results:
        print(f"[{r['customer']}] {r['subject']}")
        if r['resolution']:
            print(f"  → {r['resolution'][:100]}")
    kb.close()
```

## Maintenance

### Rebuild From Scratch

```bash
# Delete old unified database
rm unified_knowledge_base.db

# Rebuild
python build_unified_kb.py --input-dir knowledge_base --stats
```

### Export for Backup

```bash
# Export to JSON
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --export kb_backup_$(date +%Y%m%d).json

# SQLite backup
sqlite3 unified_knowledge_base.db ".backup unified_kb_backup_$(date +%Y%m%d).db"
```

### Vacuum Database

```bash
# Optimize database size
sqlite3 unified_knowledge_base.db "VACUUM;"
```

## Advanced Queries (SQL)

### Find Customers with High Open Ticket Counts

```bash
sqlite3 unified_knowledge_base.db "
  SELECT customer_handle, open_tickets, total_tickets,
         ROUND(100.0 * open_tickets / total_tickets, 1) as open_pct
  FROM customers
  WHERE open_tickets > 5
  ORDER BY open_pct DESC;
"
```

### Most Valuable Keywords (Resolution Rate)

```bash
sqlite3 unified_knowledge_base.db "
  SELECT keywords, 
         COUNT(*) as total,
         SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END) as resolved,
         ROUND(100.0 * SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END) / COUNT(*), 1) as resolve_rate
  FROM tickets
  WHERE keywords IS NOT NULL
  GROUP BY keywords
  HAVING total > 3
  ORDER BY resolve_rate DESC
  LIMIT 20;
"
```

### Tickets Open Longer Than 7 Days

```bash
sqlite3 unified_knowledge_base.db "
  SELECT customer_handle, ticket_id, subject, 
         CAST(JULIANDAY('now') - JULIANDAY(created_date) AS INTEGER) as days_open
  FROM tickets
  WHERE status NOT IN ('Resolved', 'Closed')
    AND JULIANDAY('now') - JULIANDAY(created_date) > 7
  ORDER BY days_open DESC;
"
```

## Tips & Best Practices

1. **Regular Scraping**: Run `ticket_scraper.py` daily to keep data fresh
2. **Rebuild Unified DB**: Run `build_unified_kb.py` after scraping new customers
3. **Use Keywords**: The `--similar` search is more powerful than `--search`
4. **Category Analysis**: Focus on top 3 categories to identify training opportunities
5. **Resolution Times**: Track `avg_resolution_days` to measure improvement
6. **Export for Reports**: Use `--export` to generate management reports
7. **Backup**: Export to JSON daily for disaster recovery

## Troubleshooting

**Problem**: `No customer databases found`
- **Solution**: Run `ticket_scraper.py` first for at least one customer

**Problem**: `Database not initialized`
- **Solution**: Check file permissions, ensure directory exists

**Problem**: Search returns nothing
- **Solution**: Keywords are case-insensitive but need partial matches. Try broader terms.

**Problem**: Duplicate tickets
- **Solution**: Database uses `UNIQUE(customer_handle, ticket_id)` - safe to re-import

## Next Steps

1. **Test the system**:
   ```bash
   python ticket_scraper.py --customer TEST_CUSTOMER --username admin --password pass
   python build_unified_kb.py --input-dir knowledge_base --stats
   ```

2. **Create automated scraping** for all customers in `ProductionServers.txt`

3. **Build web interface** for easy knowledge base access

4. **Add ML categorization** for better auto-categorization

5. **Create knowledge articles** from top recurring issues
