# Knowledge Base Storage - Visual Reference

## File System Layout

```
freepbx-tools/
│
├── 📄 webscraper/legacy/ticket_scraper.py                  ← Scrapes tickets from 123.NET
├── 📄 build_unified_kb.py                ← Builds unified database
├── 📄 unified_knowledge_base.py          ← Query tool for unified DB
├── 📄 query_ticket_kb.py                 ← Query tool for per-customer DB
├── 📄 kb_quickstart.py                   ← One-command workflows
├── 📄 kb_examples.py                     ← Example code
│
├── 💾 unified_knowledge_base.db          ← ⭐ MAIN DATABASE (all customers)
│
├── 📁 knowledge_base/                    ← Per-customer databases
│   ├── 💾 ARBOR_NETWORKS_tickets.db      ← Customer 1 database
│   ├── 📋 ARBOR_NETWORKS_tickets.json    ← Customer 1 JSON export
│   ├── 📝 ARBOR_NETWORKS_knowledge_base.md ← Customer 1 report
│   │
│   ├── 💾 CUSTOMER2_tickets.db           ← Customer 2 database
│   ├── 📋 CUSTOMER2_tickets.json
│   ├── 📝 CUSTOMER2_knowledge_base.md
│   │
│   └── 💾 CUSTOMER3_tickets.db           ← Customer 3 database
│       ├── 📋 CUSTOMER3_tickets.json
│       └── 📝 CUSTOMER3_knowledge_base.md
│
└── 📁 docs/
    ├── 📖 KNOWLEDGE_BASE_GUIDE.md        ← Complete usage guide
    ├── 📖 STORAGE_ARCHITECTURE.md        ← Database schema details
    └── 📖 KNOWLEDGE_BASE_README.md       ← Quick start reference
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     123.NET ADMIN INTERFACE                         │
│              https://secure.123.net/cgi-bin/...                     │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTP Requests
                                 │ (BeautifulSoup scraping)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        webscraper/legacy/ticket_scraper.py                             │
│  • Logs in with admin credentials                                   │
│  • Fetches ticket list for customer                                 │
│  • Scrapes individual ticket details                                │
│  • Extracts conversation history                                    │
│  • Auto-categorizes issues                                          │
│  • Extracts keywords                                                │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Creates files
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              knowledge_base/CUSTOMER_tickets.db                     │
│                                                                      │
│  Tables:                                                            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ tickets                                             │            │
│  │  - ticket_id, subject, status, priority            │            │
│  │  - created_date, resolved_date                     │            │
│  │  - resolution, category, keywords                  │            │
│  └────────────────────────────────────────────────────┘            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ messages                                            │            │
│  │  - ticket_id, author, timestamp, content           │            │
│  │  - Full conversation history                       │            │
│  └────────────────────────────────────────────────────┘            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ incidents                                           │            │
│  │  - ticket_id, incident_type, severity              │            │
│  └────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Multiple customers...
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      build_unified_kb.py                             │
│  • Finds all *_tickets.db files in knowledge_base/                 │
│  • Imports each customer's data                                     │
│  • Adds customer_handle field to track origin                      │
│  • Updates customer statistics                                      │
│  • Creates indexes for fast searching                               │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Creates unified database
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  unified_knowledge_base.db                           │
│                                                                      │
│  Tables:                                                            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ tickets (with customer_handle)                     │            │
│  │  - ALL tickets from ALL customers                  │            │
│  │  - Indexed by: customer, status, category, keywords│            │
│  └────────────────────────────────────────────────────┘            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ messages (with customer_handle)                    │            │
│  │  - ALL conversations from ALL customers            │            │
│  └────────────────────────────────────────────────────┘            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ customers                                           │            │
│  │  - customer_handle, total_tickets                  │            │
│  │  - open_tickets, resolved_tickets                  │            │
│  │  - avg_resolution_days, common_issues              │            │
│  └────────────────────────────────────────────────────┘            │
│  ┌────────────────────────────────────────────────────┐            │
│  │ knowledge_articles                                  │            │
│  │  - Curated solutions from patterns                 │            │
│  │  - title, problem, solution, related_tickets       │            │
│  └────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Queried by
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 unified_knowledge_base.py                            │
│  Query Methods:                                                     │
│  • search_across_customers()     - Text search                     │
│  • find_similar_issues()         - Keyword matching                │
│  • get_common_resolutions()      - Solutions by category           │
│  • get_global_statistics()       - Overall stats                   │
│  • get_customer_overview()       - Customer health                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Database Comparison

### Per-Customer Database (CUSTOMER_tickets.db)

```
┌──────────────────────────────────────────┐
│ ARBOR_NETWORKS_tickets.db                │
├──────────────────────────────────────────┤
│ tickets                                  │
│  ├─ ticket_id: "202511100043"           │
│  ├─ subject: "Network intermittent"      │
│  ├─ status: "Resolved"                   │
│  ├─ priority: "High"                     │
│  ├─ created_date: "2025-11-10"          │
│  ├─ resolved_date: "2025-11-10"         │
│  ├─ resolution: "ISP issue"              │
│  ├─ category: "Network/Connectivity"     │
│  └─ keywords: "network,outage,isp"       │
├──────────────────────────────────────────┤
│ messages (47 messages)                   │
│  ├─ ticket_id: "202511100043"           │
│  ├─ author: "Support Agent"              │
│  ├─ timestamp: "2025-11-10 08:30"       │
│  └─ content: "Checking with ISP..."      │
├──────────────────────────────────────────┤
│ incidents                                │
│  ├─ ticket_id: "202511100043"           │
│  └─ incident_type: "ISP Outage"         │
└──────────────────────────────────────────┘

✅ Best for: Deep dive into single customer
✅ Size: 1-4 MB per customer
✅ Query with: query_ticket_kb.py
```

### Unified Database (unified_knowledge_base.db)

```
┌──────────────────────────────────────────────────────────────┐
│ unified_knowledge_base.db                                    │
├──────────────────────────────────────────────────────────────┤
│ tickets                                                      │
│  ├─ customer_handle: "ARBOR_NETWORKS" ──────────┐          │
│  │    ticket_id: "202511100043"                  │          │
│  │    subject: "Network intermittent"            │          │
│  │    category: "Network/Connectivity"           │          │
│  │                                               │          │
│  ├─ customer_handle: "CUSTOMER2" ────────────────┤          │
│  │    ticket_id: "202511090088"                  │          │
│  │    subject: "Phone not registering"           │          │
│  │    category: "Phone/VoIP"                     │          │
│  │                                               │          │
│  └─ customer_handle: "CUSTOMER3" ────────────────┘          │
│       ticket_id: "202511080055"                             │
│       subject: "Email not working"                          │
│       category: "Configuration"                             │
├──────────────────────────────────────────────────────────────┤
│ customers                                                    │
│  ├─ ARBOR_NETWORKS: 47 tickets, 2 open, 2.1 day avg        │
│  ├─ CUSTOMER2: 83 tickets, 5 open, 1.8 day avg             │
│  └─ CUSTOMER3: 52 tickets, 1 open, 3.2 day avg             │
├──────────────────────────────────────────────────────────────┤
│ knowledge_articles                                           │
│  ├─ Article #1: "Phones Not Registering After Power Outage"│
│  │    - Problem: After power loss...                        │
│  │    - Solution: 1. Verify POE...                          │
│  │    - Related: 202511100043, 202511090012                 │
│  └─ Article #2: "Network Intermittent Issues"               │
│       - Problem: Packet loss...                             │
│       - Solution: Check ISP...                              │
└──────────────────────────────────────────────────────────────┘

✅ Best for: Cross-customer patterns and search
✅ Size: 50-200 MB for all customers
✅ Query with: unified_knowledge_base.py
```

## Query Examples with Output

### Example 1: Search Across All Customers

```bash
$ python unified_knowledge_base.py --db unified_knowledge_base.db --search "phone"
```

Output:
```
🔍 Searching for: phone

[ARBOR_NETWORKS] Ticket #202511100043: Phones not registering
  Status: Resolved | Priority: High | Category: Phone/VoIP
  Resolution: Rebooted POE switch, all phones came back online

[CUSTOMER2] Ticket #202511090088: Phone system down
  Status: Resolved | Priority: Critical | Category: Phone/VoIP
  Resolution: FreePBX service was stopped, restarted via systemctl

[CUSTOMER3] Ticket #202511080055: Cannot make outbound calls
  Status: Open | Priority: Medium | Category: Phone/VoIP
```

### Example 2: Find Similar Issues

```bash
$ python unified_knowledge_base.py --db unified_knowledge_base.db --similar "network,down"
```

Output:
```
🔍 Finding similar issues for: network, down

[ARBOR_NETWORKS] Ticket #202511100043: Network intermittent
  Category: Network/Connectivity | Relevance: 2
  Resolution: ISP outage - resolved by provider

[CUSTOMER2] Ticket #202511050022: Complete network down
  Category: Network/Connectivity | Relevance: 2
  Resolution: Router replacement required

[CUSTOMER5] Ticket #202510280011: Internet not working
  Category: Network/Connectivity | Relevance: 1
  Resolution: DNS server misconfigured
```

### Example 3: Statistics

```bash
$ python unified_knowledge_base.py --db unified_knowledge_base.db --stats
```

Output:
```
📊 Global Knowledge Base Statistics

Total Tickets: 487
Total Customers: 12
Average Resolution Time: 2.3 days

By Status:
  Resolved: 423
  Open: 34
  Closed: 30

By Category:
  Phone/VoIP: 156
  Network/Connectivity: 123
  Hardware: 89
  Configuration: 67
  Billing: 34
  Critical: 18

Top 10 Keywords:
  phone: 156 occurrences
  network: 123 occurrences
  outage: 89 occurrences
  registration: 67 occurrences
  hardware: 56 occurrences
```

## Storage Decision Tree

```
Question: What do I need to do?
│
├─ Analyze SINGLE customer?
│  └─→ Use: knowledge_base/CUSTOMER_tickets.db
│      Tool: query_ticket_kb.py
│      Example: python query_ticket_kb.py --db knowledge_base/ARBOR_NETWORKS_tickets.db --stats
│
├─ Search ACROSS ALL customers?
│  └─→ Use: unified_knowledge_base.db
│      Tool: unified_knowledge_base.py
│      Example: python unified_knowledge_base.py --db unified_knowledge_base.db --search "phone"
│
├─ Find patterns/recurring issues?
│  └─→ Use: unified_knowledge_base.db
│      Tool: unified_knowledge_base.py
│      Example: python unified_knowledge_base.py --db unified_knowledge_base.db --stats
│
├─ Build knowledge articles?
│  └─→ Use: unified_knowledge_base.db
│      Tool: unified_knowledge_base.py (create_knowledge_article method)
│
└─ Customer health dashboard?
   └─→ Use: unified_knowledge_base.db
       Tool: unified_knowledge_base.py
       Example: python unified_knowledge_base.py --db unified_knowledge_base.db --customers
```

## Typical Daily Workflow

```
MORNING:
┌──────────────────────────────────────────┐
│ 1. Scrape new tickets                    │
│    for customer in $(cat customers.txt)  │
│      python webscraper/legacy/ticket_scraper.py ...        │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│ 2. Rebuild unified database              │
│    python build_unified_kb.py            │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│ 3. Check stats                           │
│    python unified_knowledge_base.py      │
│      --db unified_knowledge_base.db      │
│      --stats                             │
└──────────────────────────────────────────┘

WHEN CUSTOMER CALLS:
┌──────────────────────────────────────────┐
│ 4. Search for similar issues             │
│    python unified_knowledge_base.py      │
│      --db unified_knowledge_base.db      │
│      --similar "phone,not,working"       │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│ 5. Check common resolutions              │
│    python unified_knowledge_base.py      │
│      --db unified_knowledge_base.db      │
│      --category "Phone/VoIP"             │
└──────────────────────────────────────────┘

END OF WEEK:
┌──────────────────────────────────────────┐
│ 6. Export backup                         │
│    python unified_knowledge_base.py      │
│      --db unified_knowledge_base.db      │
│      --export backup_$(date +%Y%m%d).json│
└──────────────────────────────────────────┘
```

## Summary

| What | Where | Size | Purpose |
|------|-------|------|---------|
| **Scraped Data** | `knowledge_base/CUSTOMER_tickets.db` | 1-4 MB each | Single customer analysis |
| **Unified KB** | `unified_knowledge_base.db` | 50-200 MB | Cross-customer search |
| **JSON Exports** | `knowledge_base/CUSTOMER_tickets.json` | 200 KB-1 MB | Backup/reporting |
| **Markdown Reports** | `knowledge_base/CUSTOMER_knowledge_base.md` | 100-500 KB | Human-readable summaries |
| **Backups** | `backups/*.json` or `backups/*.db` | Varies | Disaster recovery |

**Key Insight**: Keep BOTH per-customer and unified databases. They serve different purposes and complement each other perfectly.
