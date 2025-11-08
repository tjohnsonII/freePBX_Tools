#!/usr/bin/env python3
"""
Match Yealink sites with company information from complete_analysis.json
"""
import json

def main():
    # Load complete analysis
    with open('vpbx_ultimate_analysis/complete_analysis.json', 'r') as f:
        data = json.load(f)
    
    # Load Yealink sites report
    with open('yealink_sites_report.json', 'r') as f:
        yealink_sites = json.load(f)
    
    # Create site_id to site data mapping
    site_map = {s['site_id']: s for s in data['sites']}
    
    print("=" * 100)
    print("Companies with Yealink Phones")
    print("=" * 100)
    print()
    
    # Enhance Yealink sites with company info
    enhanced_sites = []
    for ys in yealink_sites:
        site_id = ys['site_id']
        site_data = site_map.get(site_id, {})
        
        # Get company name from notes or system_ip
        company = site_data.get('notes', '').strip()
        if not company or company == '':
            # Use IP address as fallback
            company = f"Site {site_id} ({site_data.get('system_ip', 'Unknown IP')})"
        
        enhanced = {
            'site_id': site_id,
            'company': company,
            'system_ip': site_data.get('system_ip', 'Unknown'),
            'yealink_models': ys['yealink_models'],
            'freepbx_version': site_data.get('freepbx_version', 'Unknown'),
            'asterisk_version': site_data.get('asterisk_version', 'Unknown'),
        }
        enhanced_sites.append(enhanced)
    
    # Sort by company name
    enhanced_sites.sort(key=lambda x: x['company'].lower())
    
    # Print report
    print(f"{'Site ID':<10} {'Company/Description':<50} {'IP Address':<18} {'Yealink Models':<30}")
    print("-" * 108)
    
    for site in enhanced_sites:
        site_id = site['site_id']
        company = site['company'][:47] + '...' if len(site['company']) > 50 else site['company']
        ip = site['system_ip']
        models = ', '.join(site['yealink_models'][:2])
        if len(site['yealink_models']) > 2:
            models += f" +{len(site['yealink_models'])-2}"
        
        print(f"{site_id:<10} {company:<50} {ip:<18} {models:<30}")
    
    print("=" * 108)
    print(f"\nTotal: {len(enhanced_sites)} companies with Yealink phones")
    
    # Save enhanced report
    with open('yealink_companies_full.json', 'w') as f:
        json.dump(enhanced_sites, f, indent=2)
    print(f"\n💾 Full report saved to: yealink_companies_full.json")
    
    # Save CSV
    with open('yealink_companies_full.csv', 'w', encoding='utf-8') as f:
        f.write("Site ID,Company,IP Address,Yealink Models,FreePBX Version,Asterisk Version\n")
        for site in enhanced_sites:
            models = '; '.join(site['yealink_models'])
            f.write(f'"{site["site_id"]}","{site["company"]}","{site["system_ip"]}",' +
                   f'"{models}","{site["freepbx_version"]}","{site["asterisk_version"]}"\n')
    print(f"💾 CSV report saved to: yealink_companies_full.csv")
    
    # Summary statistics
    print("\n" + "=" * 100)
    print("📊 Summary Statistics")
    print("=" * 100)
    
    # Count sites with notes
    sites_with_notes = sum(1 for s in enhanced_sites if not s['company'].startswith('Site '))
    print(f"\nSites with company names: {sites_with_notes}")
    print(f"Sites without names (using IP): {len(enhanced_sites) - sites_with_notes}")
    
    # Count by model
    from collections import Counter
    all_models = []
    for site in enhanced_sites:
        all_models.extend(site['yealink_models'])
    model_counts = Counter(all_models)
    
    print(f"\n📱 Top Yealink Models:")
    for model, count in model_counts.most_common(10):
        print(f"   {model:20s}: {count:3d} deployments")

if __name__ == '__main__':
    main()
