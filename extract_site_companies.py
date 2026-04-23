#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
extract_site_companies():
    Extract mapping of sites to companies from a CSV or data source and print or save the results.
"""
"""
Extract site-to-company mapping from main admin page
"""
import re

def extract_site_companies():
    """Extract site ID to company name mappings"""
    try:
        with open('test_scrape_output/admin_vpbx.cgi.txt', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        site_companies = {}
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Look for Details links with site IDs
            match = re.search(r'id=(\d+)', line)
            if match and 'Details' in line:
                site_id = match.group(1)
                
                # Company name is usually a few lines before the Details link
                # Look back up to 5 lines
                company = "Unknown"
                for j in range(1, 6):
                    if i - j >= 0:
                        prev_line = lines[i-j].strip()
                        # Skip empty lines and common navigation text
                        if prev_line and prev_line not in ['Edit', 'Add', 'Details', 'Delete', '']:
                            # Filter out obvious non-company text
                            if not re.match(r'^(https?://|Site|ID:|Type:)', prev_line):
                                company = prev_line
                                break
                
                site_companies[site_id] = company
        
        return site_companies
    
    except Exception as e:
        print(f"Error: {e}")
        return {}

if __name__ == '__main__':
    mappings = extract_site_companies()
    print(f"Found {len(mappings)} site-to-company mappings")
    
    # Show first 20
    for i, (site_id, company) in enumerate(list(mappings.items())[:20]):
        print(f"Site {site_id}: {company}")
    
    # Save to file
    with open('site_company_mapping.txt', 'w') as f:
        for site_id, company in sorted(mappings.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9999):
            f.write(f"{site_id}\t{company}\n")
    
    print(f"\n💾 Mappings saved to site_company_mapping.txt")
