# Comprehensive VPBX Scraping Guide

## Overview

The scraper now supports **comprehensive mode** which scrapes not just the main detail pages, but also all sub-pages for each VPBX entry.

## What Gets Scraped

### Standard Mode (default)
- Main VPBX table
- Detail pages only

### Comprehensive Mode (--comprehensive)
For each of the 556 entries, scrapes:
1. **Main detail page** (vpbx.cgi?command=vpbx_detail&id=X)
2. **Site Notes** (button on detail page)
3. **Site Specific Config** (button on detail page)
4. **Edit page** (link from detail page)
5. **View Config** (button on Edit page)
6. **Bulk Attribute Edit** (button on Edit page)

**Total pages**: ~3,336 (556 entries × 6 pages each)

## Usage

### Test on 2 Entries First
```bash
python test_comprehensive_scrape.py
```

This will:
- Scrape only 2 entries (for testing)
- Save to: `freepbx-tools/bin/123net_internal_docs/vpbx_test_comprehensive/`
- Create folders: `entry_6/`, `entry_7/` (or similar)
- Each folder contains: `detail_main.html`, `site_notes.html`, `edit_main.html`, etc.

### Run Full Comprehensive Scrape (All 556 Entries)
```bash
python webscraper/legacy/run_comprehensive_scrape.py
```

This will:
- Prompt for confirmation (takes 2-3 hours)
- Scrape all 556 entries with all sub-pages
- Save to: `freepbx-tools/bin/123net_internal_docs/vpbx_comprehensive/`
- Create 556 folders: `entry_6/`, `entry_7/`, ..., `entry_645/`

### Manual Usage
```bash
# Test on 2 entries
python webscraper/legacy/scrape_vpbx_tables.py --comprehensive --max-details 2 --output test_output

# Run on all entries
python webscraper/legacy/scrape_vpbx_tables.py --comprehensive --output full_output

# Skip detail pages entirely (table only)
python webscraper/legacy/scrape_vpbx_tables.py --no-details
```

## Output Structure

### Comprehensive Mode
```
vpbx_comprehensive/
├── table_data.csv              # Main table data
├── table_data.json             # Main table data (JSON)
├── entry_6/                    # First entry
│   ├── detail_main.html
│   ├── detail_main.txt
│   ├── site_notes.html
│   ├── site_notes.txt
│   ├── site_specific_config.html
│   ├── site_specific_config.txt
│   ├── edit_main.html
│   ├── edit_main.txt
│   ├── view_config.html
│   ├── view_config.txt
│   ├── bulk_attribute_edit.html
│   └── bulk_attribute_edit.txt
├── entry_7/                    # Second entry
│   └── (same files as above)
└── ... (554 more entry folders)
```

### Standard Mode (Original)
```
vpbx_tables/
├── table_data.csv
├── table_data.json
├── Details_1.html
├── Details_1.txt
├── Details_2.html
├── Details_2.txt
└── ... (all detail pages in flat structure)
```

## Command-Line Options

```
--url URL                   Base URL (default: 123NET VPBX interface)
--output DIR                Output directory
--max-details N             Limit to first N detail pages
--no-details                Skip detail pages (table only)
--comprehensive             Enable comprehensive sub-page scraping
```

## Timing Estimates

| Mode | Entries | Pages | Time |
|------|---------|-------|------|
| Table only | 556 | 6 | ~2 min |
| Standard | 556 | 556 | ~30 min |
| Comprehensive (2 test) | 2 | 12 | ~1 min |
| Comprehensive (all) | 556 | 3,336 | 2-3 hours |

## Error Handling

The scraper will:
- Skip buttons/pages that don't exist (with warning)
- Continue on errors (logs warning, moves to next)
- Save whatever it can retrieve

Common warnings:
- `⚠ Site Notes button not found` - Page doesn't have this button
- `⚠ Error clicking Edit: ...` - Edit link may not exist
- `⚠ View Config not found` - Sub-page not available

## Viewing Results

Each entry folder contains:
- `.html` files - Raw HTML for browser viewing
- `.txt` files - Clean text extraction with metadata header

Example `.txt` file header:
```
Source: https://secure.123.net/cgi-bin/web_interface/admin/vpbx.cgi?command=vpbx_detail&id=6
Page: site_notes
================================================================================

[Page content here]
```

## Tips

1. **Test first**: Always run `test_comprehensive_scrape.py` to verify it works
2. **Monitor progress**: Script shows progress like `[55/556] Details`
3. **Resume capability**: If interrupted, already-scraped URLs are tracked
4. **Disk space**: Comprehensive mode requires ~500MB-1GB storage
5. **Browser visible**: Chrome will be visible - don't close it manually

## Troubleshooting

**Script hangs**: Browser may need manual intervention (captcha, timeout)
**Missing pages**: Some entries may not have all sub-pages available
**Slow performance**: Network speed dependent; 2-3 sec per page is normal
**Authentication expired**: Restart and authenticate within 30-second window
