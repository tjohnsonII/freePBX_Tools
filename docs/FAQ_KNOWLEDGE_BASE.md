# Your Questions Answered - Knowledge Base Storage

## Q: Where are we storing the output?

### Short Answer
**Two places**:
1. **Per-Customer Databases**: `knowledge_base/CUSTOMER_tickets.db` (one per customer)
2. **Unified Database**: `unified_knowledge_base.db` (all customers combined)

### Detailed Answer

#### Storage Location #1: Per-Customer (Individual Analysis)
```
knowledge_base/
├── ARBOR_NETWORKS_tickets.db       ← SQLite database (all tickets for this customer)
├── ARBOR_NETWORKS_tickets.json     ← JSON export (summary)
├── ARBOR_NETWORKS_knowledge_base.md ← Markdown report (human-readable)
├── CUSTOMER2_tickets.db
├── CUSTOMER2_tickets.json
├── CUSTOMER2_knowledge_base.md
└── ... (one set per customer)
```

**What's in each customer database?**
- `tickets` table - All ticket metadata (ID, subject, status, priority, dates, resolution, category, keywords)
- `messages` table - Full conversation history for each ticket
- `incidents` table - Identified patterns and issues

**Size**: 1-4 MB per customer (for ~100 tickets)

**Created by**: `python ticket_scraper.py --customer CUSTOMER_NAME ...`

#### Storage Location #2: Unified (Cross-Customer Search)
```
unified_knowledge_base.db            ← ONE database with ALL customers
```

**What's in the unified database?**
- All tickets from all customers (with `customer_handle` field to identify which customer)
- All messages from all customers
- `customers` table with metadata (ticket counts, avg resolution time, common issues)
- `knowledge_articles` table for curated solutions

**Size**: 50-200 MB (for 100 customers × 100 tickets each = 10,000 tickets)

**Created by**: `python build_unified_kb.py --input-dir knowledge_base`

---

## Q: Is it possible to create another database so querying this info is easy?

### Short Answer
**Yes - already done!** The unified database (`unified_knowledge_base.db`) IS that "another database" you're asking about.

### Why We Need Both Databases

#### Per-Customer Databases (knowledge_base/*.db)
**Purpose**: Deep dive into individual customer
**Good for**:
- Viewing all tickets for one customer
- Analyzing customer-specific trends
- Detailed conversation history
- Customer reports

**Query with**: `query_ticket_kb.py`

```bash
# Example: All tickets for one customer
python query_ticket_kb.py \
  --db knowledge_base/ARBOR_NETWORKS_tickets.db \
  --stats
```

#### Unified Database (unified_knowledge_base.db)
**Purpose**: Search and analyze across ALL customers
**Good for**:
- "Has ANY customer had this issue before?"
- Finding patterns across customers
- Building knowledge base articles
- Identifying recurring problems
- Comparing customer health

**Query with**: `unified_knowledge_base.py`

```bash
# Example: Search ALL customers at once
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phone not working"
```

---

## Why This Design is Perfect for Your Use Case

### The Problem You're Solving
**Scenario**: Customer calls with issue → Tech needs to know:
1. Has this customer had this issue before?
2. Have OTHER customers had this issue?
3. What solutions worked?

### The Solution (Two-Database Strategy)

```
Customer Calls: "Our phones are down!"
         │
         ▼
┌────────────────────────────────────────────┐
│ Step 1: Search UNIFIED DATABASE            │
│ "Has anyone had this before?"              │
│                                            │
│ $ python unified_knowledge_base.py \       │
│     --similar "phone,down"                 │
│                                            │
│ Result: 12 tickets across 5 customers      │
│ Common solution: "Reboot POE switch"       │
└────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│ Step 2: Check THIS CUSTOMER's history     │
│ "Does this customer have recurring issues?"│
│                                            │
│ $ python query_ticket_kb.py \              │
│     --db knowledge_base/CUSTOMER_tickets.db│
│     --recurring                            │
│                                            │
│ Result: 3 similar issues in past 6 months  │
│ May need hardware replacement              │
└────────────────────────────────────────────┘
         │
         ▼
    Fix issue faster!
```

---

## Easy Query Examples

### Example 1: Search All Customers for Similar Issue
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phones not registering"
```

**Returns**: All tickets from all customers matching query

### Example 2: Find What Works for This Type of Issue
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --category "Phone/VoIP"
```

**Returns**: 
- Most common solutions
- How many times each solution worked
- Average time to resolve

### Example 3: Customer Health Check
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --customers
```

**Returns**:
- All customers
- Total tickets, open tickets, resolved tickets
- Average resolution time
- Most common issue types

### Example 4: Global Statistics
```bash
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats
```

**Returns**:
- Total tickets across all customers
- Breakdown by status (open, resolved, closed)
- Breakdown by category (Network, Phone, Hardware, etc.)
- Top 20 keywords
- Average resolution time

---

## How to Use the System

### Step 1: Scrape Tickets (Creates Per-Customer Databases)

```bash
# Scrape one customer
python ticket_scraper.py \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --output knowledge_base
```

**Creates**: `knowledge_base/ARBOR_NETWORKS_tickets.db`

### Step 2: Build Unified Database (Combines All Customers)

```bash
# Build unified database from ALL customer databases
python build_unified_kb.py \
  --input-dir knowledge_base \
  --output-db unified_knowledge_base.db \
  --stats
```

**Creates**: `unified_knowledge_base.db` with ALL customers

### Step 3: Query the Knowledge Base

```bash
# Search across all customers
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "your search term"

# Find similar issues
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --similar "keyword1,keyword2,keyword3"

# Get statistics
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats
```

---

## Quick Start (Easiest Way)

Use the quick start script:

```bash
# One command to do everything
python kb_quickstart.py --full \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --stats
```

This will:
1. Scrape tickets ✅
2. Create customer database ✅
3. Build unified database ✅
4. Show statistics ✅

---

## Database Schema Comparison

### Per-Customer Database Schema
```sql
-- Simple: Just this customer's data
tickets (id, ticket_id, subject, status, priority, ...)
messages (id, ticket_id, author, timestamp, content)
incidents (id, ticket_id, incident_type, severity, ...)
```

### Unified Database Schema
```sql
-- Complex: All customers with customer_handle field
tickets (id, customer_handle, ticket_id, subject, status, priority, ...)
messages (id, customer_handle, ticket_id, author, timestamp, content)
incidents (id, customer_handle, ticket_id, incident_type, severity, ...)

-- Extra tables for insights
customers (customer_handle, total_tickets, avg_resolution_days, ...)
knowledge_articles (id, title, category, problem, solution, ...)
```

**Key Difference**: Unified database has `customer_handle` field on every record so you know which customer each ticket belongs to.

---

## Real-World Use Cases

### Use Case 1: Customer Calls with Issue
**Problem**: "Our phones aren't working"

**Step 1**: Search unified database for similar issues
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --similar "phone,not,working,registration"
```

**Result**: See what worked for other customers, try those solutions first

### Use Case 2: Build Training Materials
**Problem**: New tech needs to learn common issues

**Step 1**: Get statistics on most common categories
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db --stats
```

**Result**: Focus training on top 3 issue types

### Use Case 3: Proactive Customer Management
**Problem**: Want to know which customers need attention

**Step 1**: Get customer health overview
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db --customers
```

**Result**: See which customers have high open ticket counts, reach out proactively

### Use Case 4: Create Knowledge Base Articles
**Problem**: Document common solutions

**Step 1**: Find common resolutions for a category
```bash
python unified_knowledge_base.py --db unified_knowledge_base.db \
  --category "Phone/VoIP"
```

**Step 2**: Create article from pattern
```python
from unified_knowledge_base import UnifiedKnowledgeBase
kb = UnifiedKnowledgeBase('unified_knowledge_base.db')
kb.create_knowledge_article(
    title="Phones Not Registering After Power Outage",
    category="Phone/VoIP",
    problem="After power loss, phones show no service",
    solution="1. Verify POE switch\n2. Check VLAN\n3. Restart phones",
    related_tickets=["202511100043", "202511090012"]
)
```

---

## Summary Table

| Question | Answer |
|----------|--------|
| **Where is output stored?** | 1. `knowledge_base/*.db` (per customer)<br>2. `unified_knowledge_base.db` (all customers) |
| **Can we query it easily?** | Yes! Use `unified_knowledge_base.py` for cross-customer queries |
| **What's the file size?** | ~1-4 MB per customer<br>~50-200 MB for unified database |
| **How do I search?** | `python unified_knowledge_base.py --db unified_knowledge_base.db --search "query"` |
| **How do I find patterns?** | `python unified_knowledge_base.py --db unified_knowledge_base.db --stats` |
| **Can I see all customers?** | `python unified_knowledge_base.py --db unified_knowledge_base.db --customers` |
| **How do I update it?** | Re-run scraper, then re-run `build_unified_kb.py` |

---

## Next Steps

1. **Test with one customer**:
   ```bash
   python kb_quickstart.py --full --customer TEST_CUSTOMER \
     --username admin --password pass --stats
   ```

2. **Scrape all customers** (create script to loop through customer list)

3. **Query the knowledge base** to find patterns

4. **Build knowledge articles** from common issues

5. **Integrate into web dashboard** for easy access

---

## Documentation References

- **Complete Guide**: `docs/KNOWLEDGE_BASE_GUIDE.md`
- **Storage Details**: `docs/STORAGE_ARCHITECTURE.md`
- **Visual Diagrams**: `docs/KB_STORAGE_VISUAL.md`
- **Quick Start**: `docs/KNOWLEDGE_BASE_README.md`
- **Examples**: Run `python kb_examples.py`

---

## Bottom Line

**Yes, the unified database IS the "another database" you need for easy querying.**

- Per-customer databases = Deep dive into individual customers
- Unified database = Search across everyone, find patterns, build knowledge base

Both databases work together perfectly for your use case! 🎯
