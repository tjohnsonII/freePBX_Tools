# Knowledge Base Scraper - Quick Test Guide

## Step 1: Run Self-Test (1 minute)

```powershell
python test_kb_system.py
```

This checks:
- ✅ Python version compatible
- ✅ Dependencies installed
- ✅ All files present
- ✅ Code imports correctly
- ✅ Database operations work

**Expected Output**: `🎉 All tests passed! System is ready to use.`

---

## Step 2: Test with Real Customer (5 minutes)

### Option A: Full Workflow (Easiest)

```powershell
python kb_quickstart.py --full `
  --customer ARBOR_NETWORKS `
  --username admin `
  --password your_password `
  --stats
```

This does everything:
1. Scrapes tickets ✅
2. Builds unified database ✅
3. Shows statistics ✅

### Option B: Step-by-Step

```powershell
# Step 1: Scrape tickets
python webscraper/legacy/ticket_scraper.py `
  --customer ARBOR_NETWORKS `
  --username admin `
  --password your_password `
  --output knowledge_base `
  --export-md

# Step 2: Build unified database
python build_unified_kb.py `
  --input-dir knowledge_base `
  --output-db unified_knowledge_base.db `
  --stats

# Step 3: Query it
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --search "phone"
```

---

## Step 3: Verify Output (2 minutes)

### Check Files Created

```powershell
# Should see these files
dir knowledge_base\ARBOR_NETWORKS*

# Expected:
# - ARBOR_NETWORKS_tickets.db       (Database)
# - ARBOR_NETWORKS_tickets.json     (JSON export)
# - ARBOR_NETWORKS_knowledge_base.md (Report)
```

### Check Database Contents

```powershell
# Quick check using Python
python -c "import sqlite3; conn = sqlite3.connect('knowledge_base/ARBOR_NETWORKS_tickets.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM tickets'); print(f'Tickets: {cursor.fetchone()[0]}'); conn.close()"
```

---

## Step 4: Test Queries (3 minutes)

### Search

```powershell
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --search "phone not working"
```

### Find Similar Issues

```powershell
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --similar "network,outage,down"
```

### Get Common Solutions

```powershell
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --category "Phone/VoIP"
```

### View Statistics

```powershell
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --stats
```

### Customer Overview

```powershell
python unified_knowledge_base.py `
  --db unified_knowledge_base.db `
  --customers
```

---

## Common Issues & Fixes

### ❌ "No module named 'requests'"
```powershell
pip install requests beautifulsoup4
```

### ❌ "Failed to login"
- Check credentials
- Verify network access to secure.123.net
- Try logging in via browser first

### ❌ "No customer databases found"
```powershell
# Run scraper first
python webscraper/legacy/ticket_scraper.py --customer CUSTOMER --username admin --password pass
```

### ❌ "Database not found"
```powershell
# Build unified database
python build_unified_kb.py --input-dir knowledge_base
```

---

## Success Criteria

You should see:

✅ **After Scraping**:
- Files created in `knowledge_base/` directory
- Database contains tickets (check with query)
- No error messages

✅ **After Building Unified DB**:
- `unified_knowledge_base.db` file created
- Statistics show correct ticket counts
- Multiple customers combined

✅ **After Querying**:
- Search returns relevant tickets
- Statistics show breakdowns
- Customer overview displays all customers

---

## What to Test

| Test | Command | Expected Result |
|------|---------|-----------------|
| **Self-test** | `python test_kb_system.py` | All tests pass |
| **Scrape** | `python webscraper/legacy/ticket_scraper.py ...` | Database created |
| **Build** | `python build_unified_kb.py ...` | Unified DB created |
| **Search** | `python unified_knowledge_base.py --search` | Tickets found |
| **Stats** | `python unified_knowledge_base.py --stats` | Statistics shown |

---

## Full Documentation

- **Complete Test Guide**: `TEST_KNOWLEDGE_BASE.md`
- **Usage Guide**: `docs/KNOWLEDGE_BASE_GUIDE.md`
- **FAQ**: `docs/FAQ_KNOWLEDGE_BASE.md`
- **Storage Details**: `docs/STORAGE_ARCHITECTURE.md`

---

## Quick Commands Cheat Sheet

```powershell
# Self-test
python test_kb_system.py

# Scrape one customer
python webscraper/legacy/ticket_scraper.py --customer CUSTOMER --username admin --password pass --output knowledge_base

# Build unified DB
python build_unified_kb.py --input-dir knowledge_base --stats

# Search
python unified_knowledge_base.py --db unified_knowledge_base.db --search "query"

# Statistics
python unified_knowledge_base.py --db unified_knowledge_base.db --stats

# Full workflow
python kb_quickstart.py --full --customer CUSTOMER --username admin --password pass --stats
```

---

## Time Estimate

- ⏱️ Self-test: 1 minute
- ⏱️ Scrape one customer: 2-5 minutes (depends on ticket count)
- ⏱️ Build unified database: <30 seconds
- ⏱️ Query database: <5 seconds
- **Total**: ~10-15 minutes for complete test

---

## Next Steps After Testing

1. ✅ Test passes → Scrape all customers
2. ✅ Build unified database with all data
3. ✅ Integrate into web dashboard
4. ✅ Schedule daily automated scraping
5. ✅ Train support team on querying
