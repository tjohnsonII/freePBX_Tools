#!/usr/bin/env python3
"""
Extract company names from VPBX detail pages
"""
import os
import re
from collections import defaultdict

def extract_company_from_details(filepath):
    """Extract site ID, company handle, and company name from Details file"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Extract site ID from URL
        site_id_match = re.search(r'id=(\d+)', content)
        site_id = site_id_match.group(1) if site_id_match else None
        
        # Extract Company Handle
        company_handle = None
        handle_match = re.search(r'Company Handle:\s*\n\s*([A-Z0-9\-]+)', content)
        if handle_match:
            company_handle = handle_match.group(1).strip()
        
        # Extract Company Name (appears after "Company Name:" label)
        company_name = None
        name_match = re.search(r'Company Name:\s*\n\s*(.+?)(?:\n|$)', content)
        if name_match:
            company_name = name_match.group(1).strip()
            # Clean up if it captured extra text
            if company_name and '\n' in company_name:
                company_name = company_name.split('\n')[0].strip()
        
        # Check for Yealink
        has_yealink = 'yealink' in content.lower()
        
        return {
            'site_id': site_id,
            'company_handle': company_handle,
            'company_name': company_name,
            'has_yealink': has_yealink
        }
    
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return None

def main():
    data_dir = 'test_scrape_output/vpbx_tables_all'
    
    print("Extracting company information from all sites...")
    
    # Process all Details files
    all_sites = {}
    files = [f for f in os.listdir(data_dir) if f.startswith('Details_') and f.endswith('.txt')]
    
    for filename in files:
        filepath = os.path.join(data_dir, filename)
        site_info = extract_company_from_details(filepath)
        if site_info and site_info['site_id']:
            site_id = site_info['site_id']
            if site_id not in all_sites:
                all_sites[site_id] = site_info
            elif site_info['company_name']:
                # Update with better data if we found company name
                all_sites[site_id] = site_info
    
    # Filter for Yealink sites
    yealink_sites = [s for s in all_sites.values() if s['has_yealink']]
    
    # Sort by company name
    yealink_sites.sort(key=lambda x: (x['company_name'] or 'ZZZ').lower())
    
    print(f"\n✅ Found {len(yealink_sites)} sites with Yealink phones\n")
    print("=" * 100)
    print(f"{'Site ID':<10} {'Company Handle':<20} {'Company Name':<60}")
    print("=" * 100)
    
    for site in yealink_sites:
        site_id = site['site_id'] or 'N/A'
        handle = site['company_handle'] or 'N/A'
        name = site['company_name'] or 'Unknown'
        
        # Truncate long names
        if len(name) > 57:
            name = name[:57] + '...'
        
        print(f"{site_id:<10} {handle:<20} {name:<60}")
    
    print("=" * 100)
    print(f"\nTotal: {len(yealink_sites)} companies with Yealink phones")
    
    # Count sites with/without company names
    with_names = sum(1 for s in yealink_sites if s['company_name'])
    print(f"  - With company names: {with_names}")
    print(f"  - Without company names: {len(yealink_sites) - with_names}")
    
    # Count by company handle
    handle_counts = defaultdict(int)
    for site in yealink_sites:
        if site['company_handle']:
            handle_counts[site['company_handle']] += 1
    
    if handle_counts:
        print(f"\n📊 Top Partners/Resellers with Yealink deployments:")
        for handle, count in sorted(handle_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            # Try to find the full name from our data
            partner_name = None
            for site in yealink_sites:
                if site['company_handle'] == handle and site['company_name']:
                    partner_name = site['company_name']
                    break
            
            if count > 1:  # Only show if multiple sites
                print(f"   {handle:15s} : {count:3d} sites")
    
    # Save to CSV
    csv_file = 'yealink_companies_with_names.csv'
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("Site ID,Company Handle,Company Name\n")
        for site in yealink_sites:
            site_id = site['site_id'] or ''
            handle = site['company_handle'] or ''
            name = (site['company_name'] or '').replace('"', '""')  # Escape quotes
            f.write(f'"{site_id}","{handle}","{name}"\n')
    
    print(f"\n💾 Report saved to: {csv_file}")

if __name__ == '__main__':
    main()
