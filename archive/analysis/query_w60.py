

#!/usr/bin/env python3
"""
VARIABLE MAP LEGEND
-------------------
conn    : sqlite3.Connection
    Connection object to the local VPBX SQLite database
cursor  : sqlite3.Cursor
    Cursor object for executing SQL queries
results : list of tuples
    Query results: (company_name, system_ip, phone_count)
sqlite3 : module
    SQLite3 database library
"""
"""
Quick query for Yealink W60P phones by company/site.
This script connects to the local vpbx_data.db SQLite database,
finds all sites with W60P phones, and prints a summary table.
"""

# Import the SQLite3 library for database access
import sqlite3


# Connect to the local VPBX SQLite database
conn = sqlite3.connect('vpbx_data.db')
# Create a cursor object for executing SQL queries
cursor = conn.cursor()


# Run a SQL query to find all companies/sites with Yealink W60P phones
# - Joins 'sites' and 'devices' tables
# - Filters for device models containing 'W60'
# - Groups by company and system IP, counts phones per site
# - Orders by count descending
cursor.execute("""
    SELECT s.company_name, s.system_ip, COUNT(d.id) as phone_count
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    WHERE d.model LIKE '%W60%'
    GROUP BY s.company_name, s.system_ip
    ORDER BY phone_count DESC
""")


# Fetch all results from the query
results = cursor.fetchall()


# Print header for the output table
print('Companies with Yealink W60P Phones:\n')
print(f'{"Company Name":<50} {"System IP":<20} {"Count":>5}')
print('-' * 77)


# Print each row: company name, system IP, and phone count
for row in results:
    print(f'{row[0]:<50} {row[1]:<20} {row[2]:>5}')


# Print total number of companies/sites found
print(f'\nTotal: {len(results)} companies')

# Close the database connection
conn.close()
