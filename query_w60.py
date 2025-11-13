#!/usr/bin/env python3
"""Quick query for W60P phones"""
import sqlite3

conn = sqlite3.connect('vpbx_data.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT s.company_name, s.system_ip, COUNT(d.id) as phone_count
    FROM sites s
    JOIN devices d ON s.site_id = d.site_id
    WHERE d.model LIKE '%W60%'
    GROUP BY s.company_name, s.system_ip
    ORDER BY phone_count DESC
""")

results = cursor.fetchall()

print('Companies with Yealink W60P Phones:\n')
print(f'{"Company Name":<50} {"System IP":<20} {"Count":>5}')
print('-' * 77)

for row in results:
    print(f'{row[0]:<50} {row[1]:<20} {row[2]:>5}')

print(f'\nTotal: {len(results)} companies')
conn.close()
