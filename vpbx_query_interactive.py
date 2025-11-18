#!/usr/bin/env python3
"""
Interactive VPBX database query tool
This script provides a command-line menu for running common and custom SQL queries
against the VPBX (Virtual PBX) SQLite database (vpbx_data.db). It is designed for
analysts and admins to quickly explore, audit, and troubleshoot the phone system data.
"""
import sqlite3
import sys

def run_query(query, conn):
    """
    Execute a SQL query and display results in a formatted table.
    Args:
        query (str): The SQL query to execute.
        conn (sqlite3.Connection): The open database connection.
    """
    try:
        cursor = conn.cursor()  # Create a cursor for executing SQL
        cursor.execute(query)   # Execute the provided query
        # Get column names from cursor description
        columns = [desc[0] for desc in cursor.description]
        # Fetch all results
        results = cursor.fetchall()
        if not results:
            print("No results found.")
            return
        # Calculate column widths for pretty printing
        col_widths = [len(col) for col in columns]
        for row in results:
            for i, val in enumerate(row):
                val_str = str(val) if val is not None else ''
                col_widths[i] = max(col_widths[i], len(val_str))
        # Print header row
        header = ' | '.join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
        print(header)
        print('-' * len(header))
        # Print each result row
        for row in results:
            row_str = ' | '.join(
                str(val).ljust(col_widths[i]) if val is not None else ''.ljust(col_widths[i])
                for i, val in enumerate(row)
            )
            print(row_str)
        print(f"\n({len(results)} rows)")
    except sqlite3.Error as e:
        print(f"❌ SQL Error: {e}")

def show_menu():
    """
    Print the interactive menu of available queries and options.
    """
    print("\n" + "=" * 80)
    print("VPBX Database - Quick Queries")
    print("=" * 80)
    print()
    print("1.  List all companies with Yealink phones")
    print("2.  Show phone vendor distribution")
    print("3.  Top 10 Yealink models")
    print("4.  Sites with security issues")
    print("5.  Search companies by name")
    print("6.  FreePBX version distribution")
    print("7.  Sites running old FreePBX (< v15)")
    print("8.  Largest phone deployments")
    print("9.  Sites with multiple phone vendors")
    print("10. Show all Yealink phones for a company")
    print()
    print("c.  Custom SQL query")
    print("h.  Show sample queries file")
    print("q.  Quit")
    print()

    # Connect to the VPBX SQLite database
    try:
        conn = sqlite3.connect('vpbx_data.db')
        print("✅ Connected to vpbx_data.db")
    except sqlite3.Error as e:
        print(f"❌ Cannot connect to database: {e}")
        sys.exit(1)
    # Main interactive loop
    while True:
        show_menu()  # Print menu
        choice = input("Enter your choice: ").strip().lower()
        print()
        # Handle quit
        if choice == 'q':
            print("Goodbye!")
            break
        # Show sample queries file
        elif choice == 'h':
            print("Sample queries file: vpbx_sample_queries.sql")
            print("Open it in a text editor to see 20+ example queries")
            input("\nPress Enter to continue...")
            continue
        # Custom SQL query
        elif choice == 'c':
            print("Enter your SQL query (end with semicolon):")
            query_lines = []
            while True:
                line = input()
                query_lines.append(line)
                if ';' in line:
                    break
            query = '\n'.join(query_lines)
            run_query(query, conn)
            input("\nPress Enter to continue...")
            continue
        # Predefined queries
        elif choice == '1':
            # List all companies with Yealink phones
            query = '''
                SELECT s.company_name, s.system_ip, COUNT(d.id) as phone_count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor = 'yealink'
                GROUP BY s.company_name, s.system_ip
                ORDER BY phone_count DESC
            '''
        elif choice == '2':
            # Show phone vendor distribution
            query = '''
                SELECT vendor, 
                       COUNT(DISTINCT site_id) as sites, 
                       COUNT(*) as phones
                FROM devices
                WHERE vendor IS NOT NULL
                GROUP BY vendor
                ORDER BY phones DESC
            '''
        elif choice == '3':
            # Top 10 Yealink models
            query = '''
                SELECT model, COUNT(*) as count
                FROM devices
                WHERE vendor = 'yealink' AND model IS NOT NULL
                GROUP BY model
                ORDER BY count DESC
                LIMIT 10
            '''
        elif choice == '4':
            # Sites with security issues
            query = '''
                SELECT s.site_id, s.company_name, s.system_ip,
                       si.severity, COUNT(*) as issue_count
                FROM sites s
                JOIN security_issues si ON s.site_id = si.site_id
                GROUP BY s.site_id, s.company_name, si.severity
                ORDER BY 
                    CASE si.severity 
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END,
                    issue_count DESC
            '''
        elif choice == '5':
            # Search companies by name
            search_term = input("Enter company name search term: ").strip()
            query = f'''
                SELECT site_id, company_name, system_ip, freepbx_version
                FROM sites
                WHERE company_name LIKE '%{search_term}%'
                ORDER BY company_name
            '''
        elif choice == '6':
            # FreePBX version distribution
            query = '''
                SELECT freepbx_major as version, COUNT(*) as sites
                FROM sites
                WHERE freepbx_major IS NOT NULL AND freepbx_major != ''
                GROUP BY freepbx_major
                ORDER BY freepbx_major DESC
            '''
        elif choice == '7':
            # Sites running old FreePBX (< v15)
            query = '''
                SELECT site_id, company_name, system_ip, 
                       freepbx_version, asterisk_version
                FROM sites
                WHERE freepbx_major < '15' AND freepbx_major IS NOT NULL
                ORDER BY freepbx_major, company_name
            '''
        elif choice == '8':
            # Largest phone deployments
            query = '''
                SELECT s.site_id, s.company_name, 
                       COUNT(d.id) as device_count,
                       GROUP_CONCAT(DISTINCT d.vendor) as vendors
                FROM sites s
                LEFT JOIN devices d ON s.site_id = d.site_id
                GROUP BY s.site_id, s.company_name
                HAVING device_count > 0
                ORDER BY device_count DESC
                LIMIT 20
            '''
        elif choice == '9':
            # Sites with multiple phone vendors
            query = '''
                SELECT s.site_id, s.company_name,
                       GROUP_CONCAT(DISTINCT d.vendor) as vendors,
                       COUNT(DISTINCT d.vendor) as vendor_count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor IS NOT NULL
                GROUP BY s.site_id, s.company_name
                HAVING vendor_count > 1
                ORDER BY vendor_count DESC, s.company_name
            '''
        elif choice == '10':
            # Show all Yealink phones for a company
            company = input("Enter company name (or partial name): ").strip()
            query = f'''
                SELECT s.company_name, d.model, d.mac_address, d.extension
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor = 'yealink' 
                  AND s.company_name LIKE '%{company}%'
                ORDER BY s.company_name, d.model
            '''
        else:
            print("❌ Invalid choice. Please try again.")
            input("\nPress Enter to continue...")
            continue
        # Run the query and display results
        run_query(query, conn)
        input("\nPress Enter to continue...")
    # Close the database connection on exit
    conn.close()


# Main function encapsulating the interactive menu and DB connection
def main():
    try:
        conn = sqlite3.connect('vpbx_data.db')
        print("✅ Connected to vpbx_data.db")
    except sqlite3.Error as e:
        print(f"❌ Cannot connect to database: {e}")
        sys.exit(1)
    while True:
        # Show menu options
        print("""
VPBX Query Menu:
  1. List all companies with Yealink phones
  2. Show phone vendor distribution
  3. Top 10 Yealink models
  4. Sites with security issues
  5. Search companies by name
  6. FreePBX version distribution
  7. Sites running old FreePBX (< v15)
  8. Largest phone deployments
  9. Sites with multiple phone vendors
 10. Show all Yealink phones for a company
  c. Custom SQL query
  h. Help (sample queries)
  q. Quit
""")
        choice = input("Enter your choice: ").strip().lower()
        print()
        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == 'h':
            print("Sample queries file: vpbx_sample_queries.sql")
            print("Open it in a text editor to see 20+ example queries")
            input("\nPress Enter to continue...")
            continue
        elif choice == 'c':
            print("Enter your SQL query (end with semicolon):")
            query_lines = []
            while True:
                line = input()
                query_lines.append(line)
                if ';' in line:
                    break
            query = '\n'.join(query_lines)
            run_query(query, conn)
            input("\nPress Enter to continue...")
            continue
        elif choice == '1':
            query = '''
                SELECT s.company_name, s.system_ip, COUNT(d.id) as phone_count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor = 'yealink'
                GROUP BY s.company_name, s.system_ip
                ORDER BY phone_count DESC
            '''
        elif choice == '2':
            query = '''
                SELECT vendor, 
                       COUNT(DISTINCT site_id) as sites, 
                       COUNT(*) as phones
                FROM devices
                WHERE vendor IS NOT NULL
                GROUP BY vendor
                ORDER BY phones DESC
            '''
        elif choice == '3':
            query = '''
                SELECT model, COUNT(*) as count
                FROM devices
                WHERE vendor = 'yealink' AND model IS NOT NULL
                GROUP BY model
                ORDER BY count DESC
                LIMIT 10
            '''
        elif choice == '4':
            query = '''
                SELECT s.site_id, s.company_name, s.system_ip,
                       si.severity, COUNT(*) as issue_count
                FROM sites s
                JOIN security_issues si ON s.site_id = si.site_id
                GROUP BY s.site_id, s.company_name, si.severity
                ORDER BY 
                    CASE si.severity 
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END,
                    issue_count DESC
            '''
        elif choice == '5':
            search_term = input("Enter company name search term: ").strip()
            query = f'''
                SELECT site_id, company_name, system_ip, freepbx_version
                FROM sites
                WHERE company_name LIKE '%{search_term}%'
                ORDER BY company_name
            '''
        elif choice == '6':
            query = '''
                SELECT freepbx_major as version, COUNT(*) as sites
                FROM sites
                WHERE freepbx_major IS NOT NULL AND freepbx_major != ''
                GROUP BY freepbx_major
                ORDER BY freepbx_major DESC
            '''
        elif choice == '7':
            query = '''
                SELECT site_id, company_name, system_ip, 
                       freepbx_version, asterisk_version
                FROM sites
                WHERE freepbx_major < '15' AND freepbx_major IS NOT NULL
                ORDER BY freepbx_major, company_name
            '''
        elif choice == '8':
            query = '''
                SELECT s.site_id, s.company_name, 
                       COUNT(d.id) as device_count,
                       GROUP_CONCAT(DISTINCT d.vendor) as vendors
                FROM sites s
                LEFT JOIN devices d ON s.site_id = d.site_id
                GROUP BY s.site_id, s.company_name
                HAVING device_count > 0
                ORDER BY device_count DESC
                LIMIT 20
            '''
        elif choice == '9':
            query = '''
                SELECT s.site_id, s.company_name,
                       GROUP_CONCAT(DISTINCT d.vendor) as vendors,
                       COUNT(DISTINCT d.vendor) as vendor_count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor IS NOT NULL
                GROUP BY s.site_id, s.company_name
                HAVING vendor_count > 1
                ORDER BY vendor_count DESC, s.company_name
            '''
        elif choice == '10':
            company = input("Enter company name (or partial name): ").strip()
            query = f'''
                SELECT s.company_name, d.model, d.mac_address, d.extension
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor = 'yealink' 
                  AND s.company_name LIKE '%{company}%'
                ORDER BY s.company_name, d.model
            '''
        else:
            print("❌ Invalid choice. Please try again.")
            input("\nPress Enter to continue...")
            continue
        # Run the query and display results
        run_query(query, conn)
        input("\nPress Enter to continue...")
    # Close the database connection on exit
    conn.close()

# Entry point: run main() if script is executed directly
if __name__ == '__main__':
    main()
