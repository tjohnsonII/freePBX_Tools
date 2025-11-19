
#!/usr/bin/env python3
"""
Quick database query examples for VPBX data.
This script connects to the local vpbx_data.db SQLite database and runs a series of example queries
to demonstrate how to extract useful information about phones, sites, vendors, and security issues.
"""

# Import the SQLite3 library for database access
import sqlite3


# Connect to the local VPBX SQLite database
conn = sqlite3.connect('vpbx_data.db')
# Create a cursor object for executing SQL queries
cursor = conn.cursor()


# Print banner
print("=" * 80)
print("VPBX Database Query Examples")
print("=" * 80)


# Query 1: List companies with Yealink phones (showing phone counts)
print("\n1️⃣  Companies with Yealink phones (showing phone counts):")
print("-" * 80)
cursor.execute('''
    SELECT s.company_name, COUNT(d.id) as phone_count
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    WHERE d.vendor = 'yealink'
    GROUP BY s.company_name
    ORDER BY phone_count DESC
    LIMIT 10
''')

# Print each company and their Yealink phone count
for row in cursor.fetchall():
    print(f"  {row[0]:50s} {row[1]:3d} phones")


# Query 2: Show phone vendor distribution (number of sites and phones per vendor)
print("\n2️⃣  Phone vendor distribution:")
print("-" * 80)
cursor.execute('''
    SELECT vendor, COUNT(DISTINCT site_id) as sites, COUNT(*) as phones
    FROM devices
    WHERE vendor IS NOT NULL
    GROUP BY vendor
    ORDER BY phones DESC
''')

# Print each vendor, number of sites, and total phones
for row in cursor.fetchall():
    print(f"  {row[0]:15s} {row[1]:4d} sites, {row[2]:5d} phones")


# Query 3: List top Yealink phone models by count
print("\n3️⃣  Top Yealink models:")
print("-" * 80)
cursor.execute('''
    SELECT model, COUNT(*) as count
    FROM devices
    WHERE vendor = 'yealink' AND model IS NOT NULL
    GROUP BY model
    ORDER BY count DESC
    LIMIT 10
''')

# Print each model and its count
for row in cursor.fetchall():
    model = row[0] if row[0] else 'Unknown'
    print(f"  {model:30s} {row[1]:4d} units")


# Query 4: List sites with both Yealink phones and security issues
print("\n4️⃣  Sites with Yealink AND security issues:")
print("-" * 80)
cursor.execute('''
    SELECT DISTINCT s.company_name, s.system_ip,
           COUNT(DISTINCT d.id) as yealink_phones,
           COUNT(DISTINCT si.id) as issues
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    JOIN security_issues si ON s.site_id = si.site_id
    WHERE d.vendor = 'yealink'
    GROUP BY s.site_id
    ORDER BY issues DESC
    LIMIT 10
''')

# Print each site, number of Yealink phones, and number of issues
for row in cursor.fetchall():
    print(f"  {row[0]:40s} {row[2]:2d} phones, {row[3]:2d} issues")


# Query 5: Show FreePBX version distribution across sites
print("\n5️⃣  FreePBX version distribution:")
print("-" * 80)
cursor.execute('''
    SELECT freepbx_major, COUNT(*) as count
    FROM sites
    WHERE freepbx_major IS NOT NULL AND freepbx_major != ''
    GROUP BY freepbx_major
    ORDER BY freepbx_major DESC
''')

# Print each FreePBX version and number of sites
for row in cursor.fetchall():
    print(f"  FreePBX {row[0]:3s} {row[1]:4d} sites")


# Query 6: Search for companies with 'Medical' or 'Health' in their name
print("\n6️⃣  Companies with 'Medical' or 'Health' in name:")
print("-" * 80)
cursor.execute('''
    SELECT site_id, company_name, system_ip
    FROM sites
    WHERE company_name LIKE '%Medical%' OR company_name LIKE '%Health%'
    ORDER BY company_name
    LIMIT 10
''')

# Print each matching site
for row in cursor.fetchall():
    print(f"  Site {row[0]:<6} {row[1]:45s} {row[2]}")


# Query 7: Print total stats for the database
print("\n7️⃣  Database totals:")
print("-" * 80)
cursor.execute('SELECT COUNT(*) FROM sites')
print(f"  Total sites: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM sites WHERE company_name IS NOT NULL')
print(f"  Sites with names: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM devices')
print(f"  Total devices: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(DISTINCT site_id) FROM devices WHERE vendor = "yealink"')
print(f"  Sites with Yealink: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM devices WHERE vendor = "yealink"')
print(f"  Total Yealink phones: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM security_issues')
print(f"  Security issues: {cursor.fetchone()[0]}")

# Print usage tips
print("\n" + "=" * 80)
print("💡 To run your own queries:")
print("  python query_vpbx.py")
print("  sqlite3 vpbx_data.db")
print("  Or check vpbx_sample_queries.sql for more examples")
print("=" * 80)

# Close the database connection
conn.close()
