# VPBX SQLite Database

## Overview
This SQLite database contains all scraped VPBX data including:
- **556 sites** with company names and system information
- **10,408 devices** (phones) with vendor, model, MAC address
- **52 security issues** tracked by site
- FreePBX and Asterisk version information

## Database Files

| File | Description |
|------|-------------|
| `vpbx_data.db` | Main SQLite database |
| `create_vpbx_database.py` | Script to rebuild database from scraped data |
| `query_vpbx.py` | Quick example queries |
| `vpbx_query_interactive.py` | Interactive query menu |
| `vpbx_sample_queries.sql` | 20+ sample SQL queries |

## Quick Start

### 1. Run Interactive Query Tool
```bash
python vpbx_query_interactive.py
```

This gives you a menu with 10 common queries:
- List Yealink companies
- Show vendor distribution
- Search by company name
- Find security issues
- And more...

### 2. Run Example Queries
```bash
python query_vpbx.py
```

Shows 7 pre-defined useful queries with formatted output.

### 3. Use Python Directly
```python
import sqlite3

conn = sqlite3.connect('vpbx_data.db')
cursor = conn.cursor()

# Find all Yealink sites
cursor.execute('''
    SELECT company_name, COUNT(*) as phones
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    WHERE d.vendor = 'yealink'
    GROUP BY company_name
    ORDER BY phones DESC
''')

for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]} phones")

conn.close()
```

## Database Schema

### Table: `sites`
Stores site/customer information
```sql
site_id             INTEGER PRIMARY KEY
company_handle      TEXT        -- Partner/reseller code
company_name        TEXT        -- Company name
system_ip           TEXT        -- FreePBX IP address
deployment_id       TEXT
ftp_host            TEXT
ftp_user            TEXT
ftp_pass            TEXT
admin_url           TEXT        -- Web admin URL
ssh_command         TEXT        -- SSH connection string
freepbx_version     TEXT        -- Full version (e.g., "15.0.17.12")
freepbx_major       TEXT        -- Major version (e.g., "15")
asterisk_version    TEXT        -- Full version
asterisk_major      TEXT        -- Major version
platform            TEXT        -- "FreePBX" or "Unknown"
notes               TEXT
created_at          TIMESTAMP
```

### Table: `devices`
Stores phone/device information
```sql
id                  INTEGER PRIMARY KEY AUTOINCREMENT
site_id             INTEGER     -- FK to sites.site_id
mac_address         TEXT        -- Device MAC address
extension           TEXT        -- Phone extension number
model               TEXT        -- Phone model (e.g., "SIP-T46S")
vendor              TEXT        -- Vendor (polycom, yealink, cisco, etc.)
directory_name      TEXT        -- Display name
cid                 TEXT        -- Caller ID
```

### Table: `security_issues`
Stores security problems found
```sql
id                  INTEGER PRIMARY KEY AUTOINCREMENT
site_id             INTEGER     -- FK to sites.site_id
issue_type          TEXT        -- Type of issue
severity            TEXT        -- CRITICAL, HIGH, MEDIUM, LOW
description         TEXT        -- Details
```

## Common Queries

### Find All Yealink Customers
```sql
SELECT DISTINCT s.company_name, COUNT(d.id) as phone_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.company_name
ORDER BY phone_count DESC;
```

### Phone Vendor Distribution
```sql
SELECT vendor, COUNT(DISTINCT site_id) as sites, COUNT(*) as phones
FROM devices
WHERE vendor IS NOT NULL
GROUP BY vendor
ORDER BY phones DESC;
```

### Search Companies by Name
```sql
SELECT site_id, company_name, system_ip, freepbx_version
FROM sites
WHERE company_name LIKE '%Medical%'
ORDER BY company_name;
```

### Sites with Security Issues
```sql
SELECT s.company_name, si.severity, COUNT(*) as issues
FROM sites s
JOIN security_issues si ON s.site_id = si.site_id
GROUP BY s.company_name, si.severity
ORDER BY issues DESC;
```

### Old FreePBX Versions (Need Upgrade)
```sql
SELECT site_id, company_name, freepbx_version, asterisk_version
FROM sites
WHERE freepbx_major < '15'
ORDER BY freepbx_major;
```

### Largest Yealink Deployments
```sql
SELECT s.company_name, COUNT(d.id) as yealink_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.company_name
ORDER BY yealink_count DESC
LIMIT 20;
```

### All Devices for a Specific Company
```sql
SELECT s.company_name, d.vendor, d.model, d.mac_address, d.extension
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE s.company_name = 'Jack Demmer Ford'
ORDER BY d.vendor, d.model;
```

## Export Data

### To CSV
```python
import sqlite3
import csv

conn = sqlite3.connect('vpbx_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT s.company_name, d.vendor, d.model, COUNT(*) as count
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    GROUP BY s.company_name, d.vendor, d.model
''')

with open('phone_inventory.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Company', 'Vendor', 'Model', 'Count'])
    writer.writerows(cursor.fetchall())
```

### To JSON
```python
import sqlite3
import json

conn = sqlite3.connect('vpbx_data.db')
cursor = conn.cursor()

cursor.execute('SELECT * FROM sites WHERE company_name LIKE "%Medical%"')
columns = [desc[0] for desc in cursor.description]
results = [dict(zip(columns, row)) for row in cursor.fetchall()]

with open('medical_sites.json', 'w') as f:
    json.dump(results, f, indent=2)
```

## Rebuilding Database

If you need to rebuild from scratch:

```bash
python create_vpbx_database.py
```

This will:
1. Delete existing database
2. Create fresh schema
3. Import data from `vpbx_ultimate_analysis/complete_analysis.json`
4. Extract company names from scraped pages
5. Extract device information
6. Create indexes for performance

## GUI Tools

For visual database browsing:

- **DB Browser for SQLite** (Free): https://sqlitebrowser.org/
- **DBeaver** (Free): https://dbeaver.io/
- **DataGrip** (Paid): https://www.jetbrains.com/datagrip/

## Statistics

Current database contents:
- **556 total sites**
- **556 sites with company names** (100%)
- **10,408 total devices**
- **191 sites with Yealink phones**
- **1,809 Yealink phones** deployed
- **52 security issues** found

### Vendor Breakdown
- Polycom: 354 sites, 8,497 phones
- Yealink: 191 sites, 1,809 phones  
- Cisco: 38 sites, 63 phones
- Grandstream: 30 sites, 31 phones
- Fanvil: 2 sites, 8 phones

### Top Yealink Models
1. SIP-T46S: 587 units
2. SIP-T46U: 195 units
3. W60P: 99 units
4. SIP-T48S: 67 units
5. 56h Dect Handset: 66 units

## Tips

1. **Always use parameterized queries** to prevent SQL injection
2. **Use indexes** - already created on common query fields
3. **Check query performance** with `EXPLAIN QUERY PLAN`
4. **Backup regularly** - copy `vpbx_data.db` file
5. **Keep in sync** - rebuild when new data is scraped

## Troubleshooting

**Database locked error**
- Close other connections to the database
- Only one write operation at a time

**No results found**
- Check spelling (searches are case-sensitive in SQLite by default)
- Use `LIKE '%term%'` for partial matches
- Use `COLLATE NOCASE` for case-insensitive searches

**Slow queries**
- Indexes exist on commonly queried fields
- Use `EXPLAIN QUERY PLAN` to analyze
- Consider adding more indexes if needed

## More Examples

See `vpbx_sample_queries.sql` for 20+ example queries including:
- Complex joins
- Aggregations
- Subqueries
- Search patterns
- Export formats
