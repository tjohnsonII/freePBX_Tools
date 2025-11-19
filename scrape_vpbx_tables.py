#!/usr/bin/env python3
"""
123NET VPBX Table Scraper
-------------------------
This script automates the extraction of table data and detail pages from the 123NET VPBX admin interface.
It uses Selenium to control a browser, extract tables, follow links, and save results as CSV/JSON.
"""

# =====================================
# Variable Map Legend (Key Variables)
# =====================================
#
# VPBXTableScraper class:
#   self.base_url (str): Base URL for the VPBX admin interface
#   self.output_dir (str): Output directory for scraped data
#   self.visited_urls (set): Set of URLs already visited for detail scraping
#   self.table_data (list[dict]): All extracted table row data
#   self.detail_pages (list[dict]): Metadata for each scraped detail page
#   self.driver (webdriver.Chrome): Selenium WebDriver instance
#
# Table extraction:
#   headers (list[str]): Column headers for each table
#   rows (list[dict]): Row data for each table
#   links_in_row (list[dict]): Links found in each table row
#
# Pagination:
#   next_button: Selenium element for the Next button
#   page_num (int): Current page number in pagination
#
# Detail scraping:
#   detail_url (str): URL of the detail page being scraped
#   saved_files (dict): File paths for saved HTML/text of each sub-page
#   edit_url (str): URL of the Edit page for an entry
#   edit_sub_pages (list[tuple]): Sub-pages to scrape from Edit page
#
# Output:
#   filepath (str): Path to output CSV/JSON file
#   all_keys (list[str]): All unique column names for CSV output
# =====================================

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import os
import sys
import re
import time
import csv
import json
from urllib.parse import urljoin, urlparse
from datetime import datetime

class Colors:
    """
    ANSI color codes for colored terminal output.
    Used to highlight status messages and errors.
    """
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'

class VPBXTableScraper:
    """
    Main scraper class for extracting table data and detail pages from 123NET VPBX admin.
    Handles browser setup, table parsing, pagination, link following, and output.
    """
    
    def __init__(self, base_url, output_dir):
        # Store base URL and output directory
        self.base_url = base_url
        self.output_dir = output_dir
        self.visited_urls = set()  # Track visited detail pages
        self.table_data = []       # All extracted table rows
        self.detail_pages = []     # Metadata for each scraped detail page

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

        # Setup Selenium Chrome driver with anti-detection options
        print(f"{Colors.CYAN}Initializing Chrome browser...{Colors.RESET}")
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)
            print(f"{Colors.GREEN}✓ Browser initialized{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Failed to initialize browser: {e}{Colors.RESET}")
            sys.exit(1)
    
    def extract_table_data(self):
        """
        Extract all tables from the current page using BeautifulSoup.
        Returns a list of table data dicts (headers, rows, links).
        """
        print(f"\n{Colors.BLUE}Extracting table data...{Colors.RESET}")
        
        html = self.driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        tables = soup.find_all('table')
        print(f"{Colors.CYAN}Found {len(tables)} table(s){Colors.RESET}")
        
        all_table_data = []
        
        for table_idx, table in enumerate(tables, 1):
            print(f"\n{Colors.YELLOW}Processing Table {table_idx}...{Colors.RESET}")
            
            # Extract headers
            headers = []
            header_row = table.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    header_text = th.get_text(strip=True)
                    headers.append(header_text)
            
            if not headers:
                print(f"{Colors.YELLOW}  No headers found, skipping{Colors.RESET}")
                continue
            
            print(f"{Colors.CYAN}  Headers: {', '.join(headers)}{Colors.RESET}")
            
            # Extract rows
            rows = []
            for row in table.find_all('tr')[1:]:  # Skip header row
                cells = row.find_all('td')
                if not cells:
                    continue
                
                row_data = {}
                links_in_row = []
                
                for idx, cell in enumerate(cells):
                    # Get cell text
                    cell_text = cell.get_text(strip=True)
                    
                    # Get header name for this column
                    header = headers[idx] if idx < len(headers) else f"Column_{idx}"
                    row_data[header] = cell_text
                    
                    # Extract links from this cell
                    for link in cell.find_all('a', href=True):
                        href = link.get('href', '')
                        if href and isinstance(href, str):
                            absolute_url = urljoin(self.driver.current_url, href)
                            link_text = link.get_text(strip=True)
                            links_in_row.append({
                                'column': header,
                                'text': link_text,
                                'url': absolute_url
                            })
                
                if row_data:
                    row_data['_links'] = links_in_row
                    rows.append(row_data)
            
            print(f"{Colors.GREEN}  ✓ Extracted {len(rows)} rows{Colors.RESET}")
            
            table_info = {
                'table_number': table_idx,
                'headers': headers,
                'rows': rows,
                'total_rows': len(rows)
            }
            
            all_table_data.append(table_info)
            self.table_data.extend(rows)
        
        return all_table_data
    
    def extract_all_pages(self):
        """
        Extract table data from all paginated pages by clicking 'Next' until the end.
        Returns a list of all table data from all pages.
        """
        print(f"\n{Colors.BOLD}Handling pagination...{Colors.RESET}")
        
        all_table_data = []
        page_num = 1
        
        while True:
            try:
                print(f"\n{Colors.CYAN}Extracting page {page_num}...{Colors.RESET}")
                # Extract current page
                page_data = self.extract_table_data()
                all_table_data.extend(page_data)
                # Look for "Next" button at the bottom of the page
                # Find the "Next" button by ID (most reliable)
                next_button = None
                try:
                    next_button = self.driver.find_element(By.ID, "vpbx_list_next")
                    print(f"{Colors.BLUE}  Found Next button by ID{Colors.RESET}")
                except NoSuchElementException:
                    print(f"{Colors.YELLOW}  Next button not found by ID, trying other methods...{Colors.RESET}")
                # If not found by ID, try by link text
                if not next_button:
                    next_links = self.driver.find_elements(By.LINK_TEXT, "Next")
                    if not next_links:
                        next_links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Next")
                    if next_links:
                        next_button = next_links[0]
                        print(f"{Colors.BLUE}  Found Next button by link text{Colors.RESET}")
                if next_button:
                    # Check if the Next button is disabled
                    classes = next_button.get_attribute("class") or ""
                    if "ui-state-disabled" in classes or "disabled" in classes.lower():
                        print(f"{Colors.YELLOW}  'Next' button is disabled - reached last page{Colors.RESET}")
                        break
                    print(f"{Colors.BLUE}  → Clicking 'Next' button...{Colors.RESET}")
                    # Use JavaScript to click to avoid "element click intercepted" errors
                    try:
                        self.driver.execute_script("arguments[0].click();", next_button)
                    except Exception as click_error:
                        print(f"{Colors.YELLOW}  JavaScript click failed, trying regular click: {click_error}{Colors.RESET}")
                        # Scroll to the element and try regular click as fallback
                        self.driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        next_button.click()
                    print(f"{Colors.CYAN}  Waiting for next page to load...{Colors.RESET}")
                    time.sleep(3)  # Wait for page to load
                    page_num += 1
                else:
                    print(f"{Colors.YELLOW}  No 'Next' button found - single page or end of pagination{Colors.RESET}")
                    break
            except Exception as e:
                print(f"{Colors.YELLOW}  Pagination ended: {e}{Colors.RESET}")
                break
        
        print(f"\n{Colors.GREEN}✓ Extracted {page_num} page(s) total{Colors.RESET}")
        return all_table_data
    
    def save_table_as_csv(self, table_data, filename="table_data.csv"):
        """
        Save all extracted table data to a CSV file in the output directory.
        """
        if not self.table_data:
            print(f"{Colors.YELLOW}No table data to save{Colors.RESET}")
            return
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Get all unique keys (column names)
        all_keys = set()
        for row in self.table_data:
            all_keys.update(k for k in row.keys() if k != '_links')
        
        all_keys = sorted(all_keys)
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.table_data)
            
            print(f"{Colors.GREEN}✓ Saved CSV: {filepath}{Colors.RESET}")
            print(f"{Colors.CYAN}  Rows: {len(self.table_data)}, Columns: {len(all_keys)}{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error saving CSV: {e}{Colors.RESET}")
    
    def save_table_as_json(self, table_data, filename="table_data.json"):
        """
        Save all extracted table data to a JSON file (with metadata and links).
        """
        filepath = os.path.join(self.output_dir, filename)
        
        export_data = {
            'scraped_at': datetime.now().isoformat(),
            'source_url': self.driver.current_url,
            'tables': table_data,
            'total_rows': sum(t['total_rows'] for t in table_data)
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
            
            print(f"{Colors.GREEN}✓ Saved JSON: {filepath}{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error saving JSON: {e}{Colors.RESET}")
    
    def extract_links_from_table(self, table_data):
        """
        Extract all links from the table data for later detail page scraping.
        Returns a flat list of link dicts.
        """
        all_links = []
        
        for table in table_data:
            for row in table['rows']:
                if '_links' in row:
                    all_links.extend(row['_links'])
        
        print(f"\n{Colors.CYAN}Found {len(all_links)} total links in tables{Colors.RESET}")
        
        # Show summary by column
        links_by_column = {}
        for link in all_links:
            col = link['column']
            if col not in links_by_column:
                links_by_column[col] = []
            links_by_column[col].append(link)
        
        for col, links in links_by_column.items():
            print(f"{Colors.YELLOW}  {col}: {len(links)} links{Colors.RESET}")
        
        return all_links
    
    def _save_page_content(self, output_dir, page_name, page_url):
        """
        Helper to save the current page's HTML and extracted text to files.
        Returns the HTML and text file paths.
        """
        html = self.driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Create safe filename
        safe_name = re.sub(r'[^\w\-_]', '_', page_name)
        html_file = os.path.join(output_dir, f"{safe_name}.html")
        text_file = os.path.join(output_dir, f"{safe_name}.txt")
        
        # Save HTML
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Extract and save text
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator='\n', strip=True)
        
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(f"Source: {page_url}\n")
            f.write(f"Page: {page_name}\n")
            f.write("=" * 80 + "\n\n")
            f.write(text)
        
        return html_file, text_file
    
    def scrape_detail_page_comprehensive(self, detail_url, entry_id, output_dir):
        """
        Scrape a detail page and all its sub-pages (Site Notes, Site Specific Config, Edit, etc.).
        Saves each sub-page's HTML and text to the output directory.
        Returns a dict of saved file paths.
        """
        saved_files = {}
        
        try:
            # Navigate to main detail page
            self.driver.get(detail_url)
            time.sleep(2)
            
            # Save main detail page
            html_file, text_file = self._save_page_content(output_dir, "detail_main", detail_url)
            saved_files['detail_main'] = {'html': html_file, 'text': text_file}
            print(f"{Colors.GREEN}    ✓ Main detail page{Colors.RESET}")
            
            # Define buttons to click on the detail page
            buttons_to_click = [
                ('Site Notes', 'notes_button', 'site_notes'),
                ('Site Specific Config', 'site_editor_button', 'site_specific_config'),
            ]
            
            # Click each button and save the resulting page
            for button_text, button_id, page_name in buttons_to_click:
                try:
                    # Go back to detail page
                    self.driver.get(detail_url)
                    time.sleep(1)
                    
                    # Try to find button by ID first, then by text
                    button = None
                    try:
                        button = self.driver.find_element(By.ID, button_id)
                    except NoSuchElementException:
                        try:
                            button = self.driver.find_element(By.PARTIAL_LINK_TEXT, button_text)
                        except NoSuchElementException:
                            pass
                    
                    if button:
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(2)
                        
                        current_url = self.driver.current_url
                        html_file, text_file = self._save_page_content(output_dir, page_name, current_url)
                        saved_files[page_name] = {'html': html_file, 'text': text_file}
                        print(f"{Colors.GREEN}    ✓ {button_text}{Colors.RESET}")
                    else:
                        print(f"{Colors.YELLOW}    ⚠ {button_text} button not found{Colors.RESET}")
                        
                except Exception as e:
                    print(f"{Colors.YELLOW}    ⚠ Error clicking {button_text}: {e}{Colors.RESET}")
            
            # Now handle Edit page and its sub-pages
            try:
                # Go back to detail page
                self.driver.get(detail_url)
                time.sleep(1)
                # Look for Edit link/button
                edit_button = None
                try:
                    # Try to find Edit link in the table
                    edit_links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Edit")
                    if edit_links:
                        edit_button = edit_links[0]
                    time.sleep(2)
                    edit_url = self.driver.current_url
                    # Save main Edit page
                    html_file, text_file = self._save_page_content(output_dir, "edit_main", edit_url)
                    saved_files['edit_main'] = {'html': html_file, 'text': text_file}
                    print(f"{Colors.GREEN}    ✓ Edit page{Colors.RESET}")
                    # Now look for sub-buttons on Edit page: View Config, Bulk Attribute Edit
                    edit_sub_pages = [
                        ('View Config', 'view_config'),
                        ('Bulk Attribute Edit', 'bulk_attribute_edit'),
                    ]
                    for sub_button_text, page_name in edit_sub_pages:
                        try:
                            # Go back to edit page
                            self.driver.get(edit_url)
                            time.sleep(1)
                            # Find the sub-button
                            sub_button = None
                            try:
                                sub_button = self.driver.find_element(By.PARTIAL_LINK_TEXT, sub_button_text)
                            except NoSuchElementException:
                                # Try as button by text
                                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                                for btn in buttons:
                                    if sub_button_text.lower() in btn.text.lower():
                                        sub_button = btn
                                        break
                            if sub_button:
                                self.driver.execute_script("arguments[0].click();", sub_button)
                                time.sleep(2)
                                current_url = self.driver.current_url
                                html_file, text_file = self._save_page_content(output_dir, page_name, current_url)
                                saved_files[page_name] = {'html': html_file, 'text': text_file}
                                print(f"{Colors.GREEN}    ✓ {sub_button_text}{Colors.RESET}")
                            else:
                                print(f"{Colors.YELLOW}    ⚠ {sub_button_text} not found{Colors.RESET}")
                        except Exception as e:
                            print(f"{Colors.YELLOW}    ⚠ Error with {sub_button_text}: {e}{Colors.RESET}")
                except Exception as e:
                    print(f"{Colors.YELLOW}    ⚠ Edit button not found or error: {e}{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.YELLOW}    ⚠ Error handling Edit page and sub-pages: {e}{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.RED}    ✗ Error scraping detail page: {e}{Colors.RESET}")
        
        return saved_files
    
    def scrape_detail_pages(self, links, max_pages=None, comprehensive=False):
        """
        Follow links to scrape detail pages for each entry in the table.
        If comprehensive is True, scrape all sub-pages for each entry.
        Returns the number of pages scraped.
        """
        print(f"\n{Colors.BOLD}Scraping detail pages...{Colors.RESET}")
        
        total_to_scrape = len(links) if max_pages is None else min(len(links), max_pages)
        print(f"{Colors.CYAN}Will scrape {total_to_scrape} of {len(links)} total pages{Colors.RESET}")
        if comprehensive:
            print(f"{Colors.CYAN}Mode: Comprehensive (includes sub-pages){Colors.RESET}")
        print()
        
        scraped_count = 0
        links_to_process = links if max_pages is None else links[:max_pages]
        
        for idx, link in enumerate(links_to_process, 1):
            url = link['url']
            
            if url in self.visited_urls:
                continue
            
            self.visited_urls.add(url)
            
            # Progress indicator
            print(f"{Colors.BLUE}[{idx}/{total_to_scrape}] {link['text']}{Colors.RESET}")
            
            try:
                if comprehensive:
                    # Create a directory for this entry
                    # Extract entry ID from URL
                    match = re.search(r'id=(\d+)', url)
                    entry_id = match.group(1) if match else f"entry_{idx}"
                    
                    entry_dir = os.path.join(self.output_dir, f"entry_{entry_id}")
                    os.makedirs(entry_dir, exist_ok=True)
                    
                    # Comprehensive scrape with all sub-pages
                    saved_files = self.scrape_detail_page_comprehensive(url, entry_id, entry_dir)
                    
                    self.detail_pages.append({
                        'link': link,
                        'entry_id': entry_id,
                        'directory': entry_dir,
                        'files': saved_files
                    })
                else:
                    # Simple scrape - just the main detail page
                    self.driver.get(url)
                    time.sleep(2)
                    
                    # Save page content
                    html = self.driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Generate filename from link text or row identifier
                    safe_name = re.sub(r'[^\w\-_]', '_', link['text'])[:50]
                    if not safe_name:
                        safe_name = f"page_{idx}"
                    
                    # Make filename unique if needed
                    base_file = os.path.join(self.output_dir, safe_name)
                    html_file = f"{base_file}.html"
                    text_file = f"{base_file}.txt"
                    
                    counter = 1
                    while os.path.exists(html_file):
                        html_file = f"{base_file}_{counter}.html"
                        text_file = f"{base_file}_{counter}.txt"
                        counter += 1
                    
                    # Save HTML
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(html)
                    
                    # Extract and save text
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text(separator='\n', strip=True)
                    
                    with open(text_file, 'w', encoding='utf-8') as f:
                        f.write(f"Source: {url}\n")
                        f.write(f"Link Text: {link['text']}\n")
                        f.write(f"From Column: {link['column']}\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(text)
                    
                    print(f"{Colors.GREEN}  ✓ Saved: {os.path.basename(html_file)}{Colors.RESET}")
                    
                    self.detail_pages.append({
                        'link': link,
                        'html_file': html_file,
                        'text_file': text_file
                    })
                
                scraped_count += 1
                
                # Progress update every 50 pages
                if scraped_count % 50 == 0:
                    print(f"\n{Colors.CYAN}Progress: {scraped_count}/{total_to_scrape} pages completed{Colors.RESET}\n")
                
            except Exception as e:
                print(f"{Colors.RED}  ✗ Error: {e}{Colors.RESET}")
        
        print(f"\n{Colors.GREEN}✓ Scraped {scraped_count} detail pages{Colors.RESET}")
        return scraped_count
    
    def run(self, scrape_details=True, max_detail_pages=None, comprehensive=False):
        """
        Main workflow for the scraper:
          1. Loads the main page and waits for authentication.
          2. Attempts to show all entries if possible.
          3. Extracts all table data from all pages.
          4. Saves table data as CSV and JSON.
          5. Optionally follows and scrapes detail pages (and sub-pages).
        Returns True if successful, False otherwise.
        """
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}📊 123NET VPBX Table Scraper{Colors.RESET}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        
        print(f"{Colors.CYAN}🎯 Target:{Colors.RESET} {self.base_url}")
        print(f"{Colors.CYAN}📁 Output:{Colors.RESET} {self.output_dir}")
        if comprehensive:
            print(f"{Colors.CYAN}📋 Mode:{Colors.RESET} Comprehensive (includes sub-pages)")
        print()
        
        # Navigate and wait for authentication
        print(f"{Colors.BLUE}Navigating to page...{Colors.RESET}")
        self.driver.get(self.base_url)
        
        print(f"{Colors.CYAN}Waiting 30 seconds for page load and authentication...{Colors.RESET}")
        time.sleep(30)
        
        # Try to show all entries by finding the "Show X rows" dropdown
        print(f"\n{Colors.BLUE}Looking for pagination controls...{Colors.RESET}")
        try:
            # Look for dropdown or input to change number of rows displayed
            # Common patterns: <select> with options like "10, 25, 50, 100, All"
            selects = self.driver.find_elements(By.TAG_NAME, "select")
            for select in selects:
                options = select.find_elements(By.TAG_NAME, "option")
                for option in options:
                    option_text = option.text.strip().lower()
                    # Look for "all", "999", or large numbers
                    if option_text in ['all', '999', '1000', '500'] or option_text.isdigit() and int(option_text) > 100:
                        print(f"{Colors.GREEN}Found option to show all entries: {option.text}{Colors.RESET}")
                        option.click()
                        print(f"{Colors.CYAN}Waiting for page to reload...{Colors.RESET}")
                        time.sleep(5)
                        break
        except Exception as e:
            print(f"{Colors.YELLOW}Could not find 'show all' option: {e}{Colors.RESET}")
        
        print(f"{Colors.GREEN}✓ Ready to scrape{Colors.RESET}\n")
        print(f"{Colors.CYAN}{'─' * 80}{Colors.RESET}")
        
        # Extract table data from all pages
        table_data = self.extract_all_pages()
        
        if not table_data:
            print(f"{Colors.RED}✗ No tables found{Colors.RESET}")
            return False
        
        # Save table data
        print(f"\n{Colors.BOLD}Saving table data...{Colors.RESET}")
        self.save_table_as_csv(table_data)
        self.save_table_as_json(table_data)
        
        # Extract and follow links
        if scrape_details:
            links = self.extract_links_from_table(table_data)
            
            # Filter to only "Details" links
            detail_links = [l for l in links if 'detail' in l['text'].lower() or l['column'] == 'ADD']
            
            if detail_links:
                print(f"\n{Colors.YELLOW}Found {len(detail_links)} detail page links{Colors.RESET}")
                self.scrape_detail_pages(detail_links, max_detail_pages, comprehensive=comprehensive)
        
        # Summary
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Scraping complete!{Colors.RESET}")
        print(f"\n{Colors.CYAN}📊 Summary:{Colors.RESET}")
        print(f"  • Tables found: {len(table_data)}")
        print(f"  • Total rows: {len(self.table_data)}")
        print(f"  • Detail pages scraped: {len(self.detail_pages)}")
        print(f"  • Output directory: {self.output_dir}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        
        print(f"{Colors.YELLOW}Browser will close in 5 seconds...{Colors.RESET}")
        time.sleep(5)
        
        return True
    
    def close(self):
        """
        Close the Selenium browser instance.
        """
        if self.driver:
            self.driver.quit()

def main():
    """
    Main entry point for the VPBX table scraper CLI.
    Parses command-line arguments, initializes the scraper, and runs the workflow.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='Scrape table data from 123NET VPBX admin interface'
    )

    parser.add_argument(
        '--url',
        default='https://secure.123.net/cgi-bin/web_interface/admin/vpbx.cgi',
        help='URL to scrape (default: 123NET VPBX interface)'
    )

    parser.add_argument(
        '--output',
        default='freepbx-tools/bin/123net_internal_docs/vpbx_tables',
        help='Output directory'
    )

    parser.add_argument(
        '--max-details',
        type=int,
        default=None,
        help='Maximum detail pages to scrape (default: all pages)'
    )

    parser.add_argument(
        '--no-details',
        action='store_true',
        help='Skip scraping detail pages'
    )

    parser.add_argument(
        '--comprehensive',
        action='store_true',
        help='Scrape all sub-pages (Site Notes, Site Specific Config, Edit, View Config, Bulk Attribute Edit)'
    )

    args = parser.parse_args()

    scraper = None
    try:
        scraper = VPBXTableScraper(
            base_url=args.url,
            output_dir=args.output
        )

        success = scraper.run(
            scrape_details=not args.no_details,
            max_detail_pages=args.max_details,
            comprehensive=args.comprehensive
        )

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Interrupted by user{Colors.RESET}")
        sys.exit(1)

    finally:
        if scraper:
            scraper.close()

if __name__ == '__main__':
    main()
