#!/usr/bin/env python3
"""
create_vpbx_database.py

Purpose:
    This script creates a normalized SQLite database (vpbx_data.db) from scraped VPBX (Virtual PBX) data, including company, device, and security information. It parses JSON and text files from scraping output, extracts structured data, and populates a relational schema for analysis and reporting.

Technical Overview:
    1. Defines a normalized schema with tables: sites, devices, security_issues.
    2. Extracts company and device info from scraped Details_*.txt files.
    3. Loads master site/device/security data from complete_analysis.json.
    4. Populates the database, handling duplicates and missing data.
    5. Generates a sample SQL query file for analysts.

Variable Legend:
    db_path: Path to the SQLite database file (default 'vpbx_data.db').
    conn: SQLite connection object.
    cursor: SQLite cursor for executing SQL commands.
    filepath: Path to a Details_*.txt file.
    content: Raw text content of a Details file.
    company_handle: Short code for company/reseller (from Details file).
    company_name: Human-readable company name (from Details file).
    site_id: Unique integer ID for a site (from Details file or JSON).
    devices: List of device dicts extracted from Details file.
    data: Parsed JSON from complete_analysis.json.
    company_info: Dict mapping site_id to (company_handle, company_name).
    sites_inserted: Counter for successfully inserted sites.

Script Flow:
    - create_database(): Defines schema, creates tables and indexes.
    - extract_company_info(): Regex parses company handle/name from Details file.
    - extract_device_info(): Regex parses device info (MAC, vendor, model, ext) from Details file.
    - populate_database():
        * Loads complete_analysis.json for master site/security data.
        * Extracts company/device info from Details_*.txt files.
        * Inserts all data into normalized tables, handling duplicates.
        * Prints summary statistics.
    - create_sample_queries(): Writes a .sql file with example queries for analysts.
    - main(): Orchestrates the above steps and prints usage instructions.

"""
import sqlite3
import json
import os
import re
from datetime import datetime

def create_database(db_path='vpbx_data.db'):
    """
    Create SQLite database with normalized schema for VPBX data.
    Drops any existing database at db_path, then creates tables:
      - sites: Company/site metadata
      - devices: Phone/device inventory
      - security_issues: Security findings per site
    Also creates indexes for query performance.
    Returns: sqlite3.Connection object
    """
    # Remove any existing database to ensure a clean slate
    if os.path.exists(db_path):
        print(f"Removing existing database: {db_path}")
        os.remove(db_path)
    print(f"Creating new database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Create main tables
    cursor.execute('''
        CREATE TABLE sites (
            site_id INTEGER PRIMARY KEY,           -- Unique site identifier
            company_handle TEXT,                   -- Short code for company/reseller
            company_name TEXT,                     -- Human-readable company name
            system_ip TEXT,                        -- Main system IP address
            deployment_id TEXT,                    -- Deployment identifier
            ftp_host TEXT,                         -- FTP host for configs
            ftp_user TEXT,                         -- FTP username
            ftp_pass TEXT,                         -- FTP password
            admin_url TEXT,                        -- Web admin URL
            ssh_command TEXT,                      -- SSH command for access
            freepbx_version TEXT,                  -- Full FreePBX version string
            freepbx_major TEXT,                    -- Major FreePBX version
            asterisk_version TEXT,                 -- Full Asterisk version string
            asterisk_major TEXT,                   -- Major Asterisk version
            platform TEXT,                         -- Hardware/software platform
            notes TEXT,                            -- Freeform notes
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Row creation time
        )
    ''')
    # Device inventory table
    cursor.execute('''
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique device row
            site_id INTEGER,                       -- Foreign key to sites
            mac_address TEXT,                      -- Device MAC address
            extension TEXT,                        -- Phone extension
            model TEXT,                            -- Phone model
            vendor TEXT,                           -- Phone vendor
            directory_name TEXT,                   -- Directory name (if any)
            cid TEXT,                              -- Caller ID (if any)
            FOREIGN KEY (site_id) REFERENCES sites(site_id)
        )
    ''')
    # Security issues table
    cursor.execute('''
        CREATE TABLE security_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique issue row
            site_id INTEGER,                       -- Foreign key to sites
            issue_type TEXT,                       -- Type of issue
            severity TEXT,                         -- Severity (CRITICAL/HIGH/etc)
            description TEXT,                      -- Details
            FOREIGN KEY (site_id) REFERENCES sites(site_id)
        )
    ''')
    # Indexes for fast lookups
    cursor.execute('CREATE INDEX idx_sites_company_name ON sites(company_name)')
    cursor.execute('CREATE INDEX idx_sites_company_handle ON sites(company_handle)')
    cursor.execute('CREATE INDEX idx_sites_ip ON sites(system_ip)')
    cursor.execute('CREATE INDEX idx_devices_site_id ON devices(site_id)')
    cursor.execute('CREATE INDEX idx_devices_vendor ON devices(vendor)')
    cursor.execute('CREATE INDEX idx_devices_model ON devices(model)')
    cursor.execute('CREATE INDEX idx_security_site_id ON security_issues(site_id)')
    conn.commit()
    print("✅ Database schema created")
    return conn

def extract_company_info(filepath):
    """
    Extract company handle and name from a Details_*.txt file.
    Uses regex to find 'Company Handle' and 'Company Name' fields.
    Returns: (company_handle, company_name) or (None, None) on error.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # Regex for 'Company Handle:'
        company_handle = None
        handle_match = re.search(r'Company Handle:\s*\n\s*([A-Z0-9\-]+)', content)
        if handle_match:
            company_handle = handle_match.group(1).strip()
        # Regex for 'Company Name:'
        company_name = None
        name_match = re.search(r'Company Name:\s*\n\s*(.+?)(?:\n|$)', content)
        if name_match:
            company_name = name_match.group(1).strip()
        return company_handle, company_name
    except Exception as e:
        # On error, return None for both fields
        return None, None

def extract_device_info(filepath):
    """
    Extract device inventory from a Details_*.txt file.
    Looks for MAC addresses, then parses nearby lines for vendor, model, extension.
    Returns: List of device dicts (site_id, mac_address, extension, model, vendor, directory_name, cid)
    """
    devices = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # Extract site ID from file
        site_id_match = re.search(r'id=(\d+)', content)
        if not site_id_match:
            return devices
        site_id = site_id_match.group(1)
        lines = content.split('\n')
        # Scan for MAC addresses (12 hex chars)
        for i, line in enumerate(lines):
            if re.match(r'^[0-9a-f]{12}$', line.strip().lower()):
                mac = line.strip().lower()
                vendor = None
                model = None
                extension = None
                directory_name = None
                # Look ahead for vendor/model/extension
                for j in range(1, 10):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        # Known vendors
                        if next_line.lower() in ['polycom', 'yealink', 'cisco', 'grandstream', 'sangoma', 'fanvil']:
                            vendor = next_line
                        # Model patterns (VVX, SIP-T, CP, etc)
                        elif re.match(r'(VVX|SIP-T|CP|W\d+P|\d+h Dect)', next_line, re.IGNORECASE):
                            model = next_line
                        # Extension (2-4 digits)
                        elif re.match(r'^\d{2,4}$', next_line):
                            if not extension:
                                extension = next_line
                        # Stop if next MAC or section break
                        if re.match(r'^[0-9a-f]{12}$', next_line.lower()) or next_line == 'Edit':
                            break
                # Only add if vendor or model found
                if vendor or model:
                    devices.append({
                        'site_id': site_id,
                        'mac_address': mac,
                        'extension': extension,
                        'model': model,
                        'vendor': vendor,
                        'directory_name': directory_name,
                        'cid': None
                    })
    except Exception as e:
        print(f"Error extracting devices from {filepath}: {e}")
    return devices

def populate_database(conn):
    """
    Populate the SQLite database from scraped JSON and Details files.
    - Loads master site/security data from complete_analysis.json
    - Extracts company/device info from Details_*.txt files
    - Inserts all data into normalized tables, handling duplicates
    - Prints summary statistics
    """
    cursor = conn.cursor()
    # Load master JSON data
    print("\nLoading complete_analysis.json...")
    with open('vpbx_ultimate_analysis/complete_analysis.json', 'r') as f:
        data = json.load(f)
    print(f"Found {len(data['sites'])} sites in analysis data")
    # Extract company info from Details files
    print("\nExtracting company names from scraped pages...")
    company_info = {}
    data_dir = 'test_scrape_output/vpbx_tables_all'
    if os.path.exists(data_dir):
        files = [f for f in os.listdir(data_dir) if f.startswith('Details_') and f.endswith('.txt')]
        for i, filename in enumerate(files):
            if i % 50 == 0:
                print(f"  Processed {i}/{len(files)} files...")
            filepath = os.path.join(data_dir, filename)
            # Extract site ID from first line
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                site_id_match = re.search(r'id=(\d+)', first_line)
                if site_id_match:
                    site_id = site_id_match.group(1)
                    handle, name = extract_company_info(filepath)
                    if handle or name:
                        company_info[site_id] = (handle, name)
                    # Extract and insert device inventory
                    devices = extract_device_info(filepath)
                    if devices:
                        for device in devices:
                            cursor.execute('''
                                INSERT INTO devices (site_id, mac_address, extension, model, vendor, directory_name, cid)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                device['site_id'],
                                device['mac_address'],
                                device['extension'],
                                device['model'],
                                device['vendor'],
                                device['directory_name'],
                                device['cid']
                            ))
        print(f"  ✅ Extracted company info for {len(company_info)} sites")
    # Insert sites data from JSON
    print("\nInserting site data...")
    sites_inserted = 0
    for site in data['sites']:
        site_id = site.get('site_id')
        if not site_id:
            continue
        # Get company info from Details scrape if available
        handle, name = company_info.get(site_id, (None, None))
        try:
            cursor.execute('''
                INSERT INTO sites (
                    site_id, company_handle, company_name, system_ip, deployment_id,
                    ftp_host, ftp_user, ftp_pass, admin_url, ssh_command,
                    freepbx_version, freepbx_major, asterisk_version, asterisk_major,
                    platform, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                site_id,
                handle,
                name,
                site.get('system_ip'),
                site.get('deployment_id'),
                site.get('ftp_host'),
                site.get('ftp_user'),
                site.get('ftp_pass'),
                site.get('admin_url'),
                site.get('ssh_command'),
                site.get('freepbx_version'),
                site.get('freepbx_major'),
                site.get('asterisk_version'),
                site.get('asterisk_major'),
                site.get('platform'),
                site.get('notes')
            ))
            sites_inserted += 1
        except sqlite3.IntegrityError:
            # Duplicate site_id, skip
            pass
        # Insert security issues for this site
        for issue in site.get('security', []):
            cursor.execute('''
                INSERT INTO security_issues (site_id, issue_type, severity, description)
                VALUES (?, ?, ?, ?)
            ''', (
                site_id,
                issue.get('type'),
                issue.get('severity'),
                issue.get('details')
            ))
    conn.commit()
    print(f"✅ Inserted {sites_inserted} sites")
    # Print summary statistics
    cursor.execute('SELECT COUNT(*) FROM sites')
    site_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM devices')
    device_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM security_issues')
    security_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM sites WHERE company_name IS NOT NULL')
    named_sites = cursor.fetchone()[0]
    print(f"\n📊 Database Statistics:")
    print(f"   Sites: {site_count}")
    print(f"   Sites with company names: {named_sites}")
    print(f"   Devices: {device_count}")
    print(f"   Security issues: {security_count}")

def create_sample_queries(db_path='vpbx_data.db'):
    """
    Write a file (vpbx_sample_queries.sql) with example SQL queries for analysts.
    These queries cover common reporting and analysis tasks for the VPBX database.
    """
    queries = """
-- Sample SQL Queries for VPBX Database
-- Database: vpbx_data.db
-- Generated: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """

-- ============================================================
-- BASIC QUERIES
-- ============================================================

-- 1. List all companies with Yealink phones
SELECT DISTINCT s.site_id, s.company_name, s.system_ip, s.freepbx_version
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name;

-- 2. Count sites by phone vendor
SELECT vendor, COUNT(DISTINCT site_id) as site_count
FROM devices
WHERE vendor IS NOT NULL
GROUP BY vendor
ORDER BY site_count DESC;

-- 3. List all Yealink models in use
SELECT model, COUNT(*) as count
FROM devices
WHERE vendor = 'yealink'
GROUP BY model
ORDER BY count DESC;

-- 4. Find sites with specific phone models
SELECT s.site_id, s.company_name, d.model, COUNT(*) as phone_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.model LIKE '%T46%'
GROUP BY s.site_id, s.company_name, d.model
ORDER BY phone_count DESC;

-- ============================================================
-- SECURITY QUERIES
-- ============================================================

-- 5. Sites with security issues
SELECT s.site_id, s.company_name, si.severity, COUNT(*) as issue_count
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
    issue_count DESC;

-- 6. All critical security issues
SELECT s.site_id, s.company_name, s.system_ip, si.issue_type, si.description
FROM sites s
JOIN security_issues si ON s.site_id = si.site_id
WHERE si.severity = 'CRITICAL'
ORDER BY s.company_name;

-- ============================================================
-- VERSION QUERIES
-- ============================================================

-- 7. FreePBX version distribution
SELECT freepbx_version, COUNT(*) as count
FROM sites
WHERE freepbx_version IS NOT NULL AND freepbx_version != ''
GROUP BY freepbx_version
ORDER BY count DESC;

-- 8. Sites running old FreePBX versions
SELECT site_id, company_name, system_ip, freepbx_version, asterisk_version
FROM sites
WHERE freepbx_major < '15'
ORDER BY freepbx_major, company_name;

-- 9. Sites by platform
SELECT platform, COUNT(*) as count
FROM sites
GROUP BY platform
ORDER BY count DESC;

-- ============================================================
-- DEVICE QUERIES
-- ============================================================

-- 10. Total devices per site
SELECT s.site_id, s.company_name, COUNT(d.id) as device_count
FROM sites s
LEFT JOIN devices d ON s.site_id = d.site_id
GROUP BY s.site_id, s.company_name
HAVING device_count > 0
ORDER BY device_count DESC
LIMIT 20;

-- 11. Sites with mixed vendor phones
SELECT s.site_id, s.company_name, 
       GROUP_CONCAT(DISTINCT d.vendor) as vendors,
       COUNT(DISTINCT d.vendor) as vendor_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor IS NOT NULL
GROUP BY s.site_id, s.company_name
HAVING vendor_count > 1
ORDER BY vendor_count DESC, s.company_name;

-- 12. Most common phone models across all sites
SELECT vendor, model, COUNT(*) as deployment_count
FROM devices
WHERE vendor IS NOT NULL AND model IS NOT NULL
GROUP BY vendor, model
ORDER BY deployment_count DESC
LIMIT 20;

-- ============================================================
-- COMPANY QUERIES
-- ============================================================

-- 13. Search for companies by name
SELECT site_id, company_name, system_ip, freepbx_version
FROM sites
WHERE company_name LIKE '%Medical%'
ORDER BY company_name;

-- 14. Sites by company handle (reseller/partner)
SELECT company_handle, COUNT(*) as site_count
FROM sites
WHERE company_handle IS NOT NULL
GROUP BY company_handle
ORDER BY site_count DESC;

-- 15. All information for a specific company
SELECT s.*, 
       (SELECT COUNT(*) FROM devices WHERE site_id = s.site_id) as device_count,
       (SELECT COUNT(*) FROM security_issues WHERE site_id = s.site_id) as security_issue_count
FROM sites s
WHERE s.company_name = '123.Net, LLC';

-- ============================================================
-- ADVANCED QUERIES
-- ============================================================

-- 16. Sites with Yealink AND security issues
SELECT s.site_id, s.company_name, s.system_ip,
       COUNT(DISTINCT d.id) as yealink_phones,
       COUNT(DISTINCT si.id) as security_issues
FROM sites s
JOIN devices d ON s.site_id = d.site_id
JOIN security_issues si ON s.site_id = si.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.site_id, s.company_name, s.system_ip
ORDER BY security_issues DESC, s.company_name;

-- 17. Sites missing FreePBX version info
SELECT site_id, company_name, system_ip, platform
FROM sites
WHERE (freepbx_version IS NULL OR freepbx_version = '')
  AND platform != 'Unknown'
ORDER BY company_name;

-- 18. Largest Yealink deployments
SELECT s.site_id, s.company_name, s.system_ip,
       COUNT(d.id) as yealink_count,
       GROUP_CONCAT(DISTINCT d.model) as models
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.site_id, s.company_name, s.system_ip
ORDER BY yealink_count DESC
LIMIT 20;

-- 19. Export Yealink sites to CSV format
SELECT s.site_id, s.company_name, s.system_ip, d.model, d.mac_address
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name, d.model;

-- 20. Sites with conference phones (CP models)
SELECT s.site_id, s.company_name, d.model, COUNT(*) as count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.model LIKE 'CP%'
GROUP BY s.site_id, s.company_name, d.model
ORDER BY count DESC, s.company_name;
"""
    
    with open('vpbx_sample_queries.sql', 'w') as f:
        f.write(queries)
    
    print(f"\n💾 Sample queries saved to: vpbx_sample_queries.sql")

def main():
    """
    Main entry point for the script.
    Orchestrates database creation, population, and sample query generation.
    Prints usage instructions for analysts.
    """
    print("=" * 80)
    print("VPBX SQLite Database Creator")
    print("=" * 80)
    # Step 1: Create database and schema
    conn = create_database()
    # Step 2: Populate with scraped data
    populate_database(conn)
    # Step 3: Write sample queries for analysts
    create_sample_queries()
    # Step 4: Close DB connection
    conn.close()
    print("\n" + "=" * 80)
    print("✅ Database created successfully!")
    print("=" * 80)
    print("\nTo query the database, use:")
    print("  sqlite3 vpbx_data.db")
    print("\nOr use Python:")
    print("  import sqlite3")
    print("  conn = sqlite3.connect('vpbx_data.db')")
    print("  cursor = conn.cursor()")
    print("  cursor.execute('SELECT * FROM sites WHERE company_name LIKE \"%Medical%\"')")
    print("  results = cursor.fetchall()")
    print("\nOr use a GUI tool like:")
    print("  - DB Browser for SQLite (https://sqlitebrowser.org/)")
    print("  - DBeaver (https://dbeaver.io/)")
    print("\nSample queries available in: vpbx_sample_queries.sql")

# Script entry point
if __name__ == '__main__':
    main()
