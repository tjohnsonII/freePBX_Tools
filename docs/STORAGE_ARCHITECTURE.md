# Knowledge Base Storage - Complete Overview

## Storage Locations

### 📁 Per-Customer Databases (Individual Analysis)

**Location**: `knowledge_base/`

**Files Created Per Customer**:
```
knowledge_base/
├── ARBOR_NETWORKS_tickets.db          # SQLite database
├── ARBOR_NETWORKS_tickets.json        # JSON export
├── ARBOR_NETWORKS_knowledge_base.md   # Markdown report (optional)
├── CUSTOMER2_tickets.db
├── CUSTOMER2_tickets.json
└── ...
```

**What's Inside Each Database**:
- `tickets` table - All tickets with metadata
- `messages` table - Full conversation history
- `incidents` table - Identified issues/patterns

**Best For**:
- Single customer deep-dive
- Customer-specific reports
- Detailed conversation history
- Individual customer trends

### 📊 Unified Knowledge Base (Cross-Customer Analysis)

**Location**: `unified_knowledge_base.db` (root directory)

**Single Database Contains**:
- ALL customers combined
- Cross-customer search capability
- Global statistics and trends
- Common resolution patterns

**Tables**:
1. **tickets** - All tickets from all customers (with `customer_handle` field)
2. **messages** - All conversations (linked to tickets)
3. **incidents** - All identified patterns
4. **customers** - Customer metadata (ticket counts, avg resolution time)
5. **knowledge_articles** - Curated solutions from patterns

**Best For**:
- Finding similar issues across customers
- Identifying recurring patterns
- Building knowledge articles
- Global statistics and reporting
- "Have we seen this before?" queries

## Visual Storage Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TICKET SCRAPING WORKFLOW                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────┐
        │    ticket_scraper.py                     │
        │    Scrapes tickets from 123.NET admin    │
        └──────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────┐
        │         Per-Customer Databases            │
        │    knowledge_base/CUSTOMER_tickets.db     │
        │    - Tickets                              │
        │    - Messages                             │
        │    - Incidents                            │
        └──────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────┐
        │    build_unified_kb.py                   │
        │    Imports all customer databases        │
        └──────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────┐
        │       Unified Knowledge Base              │
        │    unified_knowledge_base.db              │
        │    - ALL customers                        │
        │    - Cross-customer search                │
        │    - Global patterns                      │
        │    - Knowledge articles                   │
        └──────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────┐
        │    Query & Analysis Tools                 │
        │    - unified_knowledge_base.py            │
        │    - query_ticket_kb.py                   │
        │    - kb_examples.py                       │
        └──────────────────────────────────────────┘
```

## What Gets Stored Where

### Per-Customer Database Schema

**`knowledge_base/CUSTOMER_tickets.db`**

```sql
-- tickets table
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY,
    ticket_id TEXT UNIQUE,
    subject TEXT,
    status TEXT,
    priority TEXT,
    created_date TEXT,
    resolved_date TEXT,
    resolution TEXT,
    category TEXT,
    keywords TEXT,
    message_count INTEGER
);

-- messages table
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    ticket_id TEXT,
    author TEXT,
    timestamp TEXT,
    content TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
);

-- incidents table
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    ticket_id TEXT,
    incident_type TEXT,
    description TEXT,
    severity TEXT,
    discovered_date TEXT
);
```

### Unified Database Schema

**`unified_knowledge_base.db`**

```sql
-- tickets table (with customer field)
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY,
    customer_handle TEXT NOT NULL,     -- ⭐ Which customer
    ticket_id TEXT NOT NULL,
    subject TEXT,
    status TEXT,
    priority TEXT,
    created_date TEXT,
    resolved_date TEXT,
    resolution TEXT,
    category TEXT,
    keywords TEXT,
    message_count INTEGER,
    last_updated TEXT,
    UNIQUE(customer_handle, ticket_id)
);

-- messages table (with customer field)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    customer_handle TEXT NOT NULL,     -- ⭐ Which customer
    original_ticket_id TEXT NOT NULL,
    author TEXT,
    timestamp TEXT,
    content TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

-- incidents table (with customer field)
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    customer_handle TEXT NOT NULL,     -- ⭐ Which customer
    original_ticket_id TEXT NOT NULL,
    incident_type TEXT,
    description TEXT,
    severity TEXT,
    discovered_date TEXT
);

-- customers table (metadata)
CREATE TABLE customers (
    customer_handle TEXT PRIMARY KEY,
    total_tickets INTEGER,
    open_tickets INTEGER,
    resolved_tickets INTEGER,
    avg_resolution_days REAL,
    common_issues TEXT,
    last_scrape_date TEXT
);

-- knowledge_articles table (curated solutions)
CREATE TABLE knowledge_articles (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT,
    problem_description TEXT,
    solution TEXT,
    related_ticket_ids TEXT,        -- Comma-separated
    affected_customers TEXT,        -- Comma-separated
    created_date TEXT,
    usefulness_score INTEGER
);
```

## Data Flow Example

### Scraping Single Customer

```bash
python ticket_scraper.py \
  --customer ARBOR_NETWORKS \
  --username admin \
  --password your_password \
  --output knowledge_base \
  --export-md
```

**Creates**:
1. `knowledge_base/ARBOR_NETWORKS_tickets.db` (SQLite)
2. `knowledge_base/ARBOR_NETWORKS_tickets.json` (JSON summary)
3. `knowledge_base/ARBOR_NETWORKS_knowledge_base.md` (Markdown report)

**Database Contents**:
- 47 tickets scraped
- 312 messages (conversation history)
- 8 incidents identified
- Auto-categorized: 12 Network, 18 Phone, 9 Hardware, 8 Config

### Building Unified Database

```bash
python build_unified_kb.py \
  --input-dir knowledge_base \
  --output-db unified_knowledge_base.db \
  --stats
```

**Creates**:
- `unified_knowledge_base.db` (single database)

**Imports**:
- All tickets from all `*_tickets.db` files in `knowledge_base/`
- Adds `customer_handle` field to track which customer
- Updates `customers` table with statistics
- Creates indexes for fast searching

**Result**:
```
Database: unified_knowledge_base.db
Total Tickets: 487 (from 12 customers)
Total Customers: 12
Average Resolution Time: 2.3 days

By Category:
  Network/Connectivity: 123
  Phone/VoIP: 156
  Hardware: 89
  Configuration: 67
  Billing: 34
  Critical: 18
```

## Query Examples

### Query Per-Customer Database

```bash
# Search single customer
python query_ticket_kb.py \
  --db knowledge_base/ARBOR_NETWORKS_tickets.db \
  --search "phone"

# Show statistics for single customer
python query_ticket_kb.py \
  --db knowledge_base/ARBOR_NETWORKS_tickets.db \
  --stats
```

### Query Unified Database

```bash
# Search ALL customers
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --search "phone not working"

# Find similar issues across ALL customers
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --similar "network,outage,down"

# Global statistics
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --stats
```

## Storage Recommendations

### Development/Testing
```
knowledge_base/           # Per-customer databases (testing)
unified_knowledge_base.db # Unified database (development)
```

### Production
```
/var/123net/knowledge_base/
├── customers/
│   ├── ARBOR_NETWORKS_tickets.db
│   ├── CUSTOMER2_tickets.db
│   └── ...
├── unified_knowledge_base.db        # Main database
├── backups/
│   ├── unified_kb_20251110.db
│   ├── unified_kb_20251109.db
│   └── ...
└── exports/
    ├── kb_export_20251110.json
    └── ...
```

## Backup Strategy

### Per-Customer Databases
```bash
# Backup individual customer
cp knowledge_base/ARBOR_NETWORKS_tickets.db backups/
```

### Unified Database
```bash
# SQLite backup
sqlite3 unified_knowledge_base.db ".backup unified_kb_backup_$(date +%Y%m%d).db"

# JSON export backup
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --export backups/kb_export_$(date +%Y%m%d).json
```

## Disk Space Estimates

**Per Customer** (assuming 100 tickets):
- SQLite database: ~500 KB - 2 MB
- JSON export: ~200 KB - 1 MB
- Markdown report: ~100 KB - 500 KB
- **Total per customer**: ~1-4 MB

**Unified Database** (100 customers × 100 tickets = 10,000 tickets):
- SQLite database: ~50-200 MB
- JSON export: ~20-100 MB
- **Total**: ~70-300 MB

**Indexes** add ~10-20% overhead but make queries 100x faster.

## Migration Path

### From Individual to Unified

```bash
# 1. Scrape all customers
for customer in ARBOR_NETWORKS CUSTOMER2 CUSTOMER3; do
    python ticket_scraper.py --customer $customer ...
done

# 2. Build unified database
python build_unified_kb.py --input-dir knowledge_base

# 3. Verify
python unified_knowledge_base.py --db unified_knowledge_base.db --stats
```

### Re-importing After Updates

```bash
# Scrape latest tickets
python ticket_scraper.py --customer ARBOR_NETWORKS ...

# Re-import (REPLACE existing data for this customer)
python unified_knowledge_base.py \
  --db unified_knowledge_base.db \
  --import-customer knowledge_base/ARBOR_NETWORKS_tickets.db \
  --customer-handle ARBOR_NETWORKS
```

## Summary

| Aspect | Per-Customer DBs | Unified Database |
|--------|------------------|------------------|
| **Location** | `knowledge_base/*.db` | `unified_knowledge_base.db` |
| **Scope** | Single customer | ALL customers |
| **Size** | 1-4 MB each | 50-200 MB total |
| **Best For** | Deep-dive analysis | Pattern detection |
| **Queries** | Customer-specific | Cross-customer |
| **Updates** | Independent | Batch re-import |
| **Backup** | Individual files | Single file |

**Recommendation**: Keep BOTH!
- Use per-customer databases for detailed customer analysis
- Use unified database for knowledge base queries and pattern detection
- Build unified database nightly from per-customer databases
