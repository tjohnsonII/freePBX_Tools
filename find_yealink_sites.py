#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
extract_site_info(filepath):
    Extract site information from a Details_*.txt file.
main():
    Orchestrate extraction of Yealink sites and output results.
"""
"""
Find all sites/companies with Yealink phones from scraped VPBX data
"""
import os
import re
import json
from collections import defaultdict

def extract_site_info(filepath):
    """Extract site ID and relevant info from a Details file"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Extract site ID from URL
        site_id_match = re.search(r'id=(\d+)', content)
        site_id = site_id_match.group(1) if site_id_match else None
        
        # Check for Yealink
        has_yealink = 'yealink' in content.lower()
        
        if not has_yealink:
            return None
        
        # Extract Yealink phone models
        yealink_models = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'yealink' in line.lower():
                # Look at surrounding lines for model info
                context = '\n'.join(lines[max(0, i-2):min(len(lines), i+3)])
                # Common Yealink models
                models = re.findall(r'(SIP-T\d+[A-Z]*|W\d+P|CP\d+|\d+h Dect)', context, re.IGNORECASE)
                yealink_models.extend(models)
        
        # Extract company name/description
        company = "Unknown"
        company_match = re.search(r'Company:\s*(.+)', content)
        if company_match:
            company = company_match.group(1).strip()
        
        # Try to extract from Notes or Description
        if company == "Unknown":
            desc_match = re.search(r'(?:Description|Notes|Name):\s*(.+)', content, re.IGNORECASE)
            if desc_match:
                company = desc_match.group(1).strip()
        
        return {
            'site_id': site_id,
            'company': company,
            'yealink_models': list(set(yealink_models)),
            'file': os.path.basename(filepath)
        }
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return None

def main():
    data_dir = 'test_scrape_output/vpbx_tables_all'
    
    print("=" * 80)
    print("Yealink Phone Sites Report")
    print("=" * 80)
    print()
    
    # Find all Details files with Yealink
    yealink_sites = []
    
    files = [f for f in os.listdir(data_dir) if f.startswith('Details_') and f.endswith('.txt')]
    print(f"Scanning {len(files)} files...")
    
    for filename in files:
        filepath = os.path.join(data_dir, filename)
        site_info = extract_site_info(filepath)
        if site_info:
            yealink_sites.append(site_info)
    
    # Deduplicate by site_id
    sites_dict = {}
    for site in yealink_sites:
        site_id = site['site_id']
        if site_id not in sites_dict:
            sites_dict[site_id] = site
        else:
            # Merge models
            sites_dict[site_id]['yealink_models'].extend(site['yealink_models'])
            sites_dict[site_id]['yealink_models'] = list(set(sites_dict[site_id]['yealink_models']))
    
    # Sort by site_id
    sorted_sites = sorted(sites_dict.values(), key=lambda x: int(x['site_id']) if x['site_id'] and x['site_id'].isdigit() else 9999)
    
    print(f"\n✅ Found {len(sorted_sites)} unique sites with Yealink phones\n")
    print("=" * 80)
    
    # Group by models
    model_count = defaultdict(int)
    for site in sorted_sites:
        for model in site['yealink_models']:
            model_count[model] += 1
    
    print("📊 Yealink Model Distribution:")
    print("-" * 80)
    for model, count in sorted(model_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  {model:30s} : {count:3d} sites")
    print()
    print("=" * 80)
    print()
    
    # Print detailed site list
    print("📋 Sites with Yealink Phones:")
    print("=" * 80)
    print(f"{'Site ID':<10} {'Company/Description':<40} {'Models':<30}")
    print("-" * 80)
    
    for site in sorted_sites:
        site_id = site['site_id'] or 'N/A'
        company = (site['company'][:37] + '...') if len(site['company']) > 40 else site['company']
        models = ', '.join(site['yealink_models'][:3]) if site['yealink_models'] else 'Unknown'
        if len(site['yealink_models']) > 3:
            models += f" +{len(site['yealink_models'])-3}"
        
        print(f"{site_id:<10} {company:<40} {models:<30}")
    
    print("=" * 80)
    print(f"\nTotal: {len(sorted_sites)} sites with Yealink phones")
    
    # Save to JSON
    output_file = 'yealink_sites_report.json'
    with open(output_file, 'w') as f:
        json.dump(sorted_sites, f, indent=2)
    print(f"\n💾 Full report saved to: {output_file}")
    
    # Save to CSV
    csv_file = 'yealink_sites_report.csv'
    with open(csv_file, 'w') as f:
        f.write("Site ID,Company,Yealink Models\n")
        for site in sorted_sites:
            models = '; '.join(site['yealink_models'])
            f.write(f'"{site["site_id"]}","{site["company"]}","{models}"\n')
    print(f"💾 CSV report saved to: {csv_file}")

if __name__ == '__main__':
    main()
