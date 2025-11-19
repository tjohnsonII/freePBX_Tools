#!/usr/bin/env python3
"""
123NET Internal Documentation Scraper
Scrapes documentation from secure.123.net using existing AD/MFA authentication
Saves content to 123net_internal_docs folder for offline reference
Detailed comments added for maintainability and onboarding.
"""

# =====================================
# Variable Map Legend (Key Variables)
# =====================================
#
# DocScraper class:
#   self.base_url (str): Base URL for the documentation site
#   self.output_dir (str): Output directory for scraped files
#   self.session (requests.Session): HTTP session for authentication and requests
#   self.visited_urls (set): Set of URLs already visited to avoid loops
#   self.downloaded_files (list): List of all saved file paths
#
# Page fetching:
#   response (requests.Response): HTTP response object for a fetched page
#
# File saving:
#   filename (str): Sanitized filename for saving output
#   filepath (str): Full path to output file
#   base, ext (str): Base and extension for filename collision avoidance
#
# Link extraction:
#   links (list[dict]): List of extracted links with url, text, and href
#   soup (BeautifulSoup): Parsed HTML for the current page
#
# Scraping logic:
#   depth (int): Current recursion depth for scraping
#   max_depth (int): Maximum allowed recursion depth
#   title_text (str): Page title for file naming
#   content_text (str): Main extracted text content from a page
# =====================================

# This script uses requests (with NTLM support) and BeautifulSoup to crawl and save internal documentation.
# It handles authentication, link extraction, recursive scraping, and robust file saving for offline use.

import requests
from requests_ntlm import HttpNtlmAuth
from bs4 import BeautifulSoup
import os
import sys
import re
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime
import getpass

class Colors:
    """
    ANSI color codes for colored terminal output.
    Used to highlight status messages and errors in the CLI.
    """
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'

class DocScraper:
    """
    Scraper for 123NET internal documentation.
    Handles authentication, crawling, link extraction, and file saving.
    """
    
    def __init__(self, base_url, output_dir, use_ntlm=True):
        # Store base URL and output directory
        self.base_url = base_url
        self.output_dir = output_dir
        self.session = requests.Session()  # HTTP session for persistent cookies/auth
        self.visited_urls = set()          # Track visited URLs to avoid loops
        self.downloaded_files = []         # List of all saved file paths
        
        # Windows NTLM authentication (uses current Windows credentials)
        if use_ntlm:
            print(f"{Colors.CYAN}Using Windows NTLM authentication...{Colors.RESET}")
            # Empty domain\\username means use current Windows credentials
            self.session.auth = HttpNtlmAuth('', '')
        else:
            print(f"{Colors.CYAN}Using existing Active Directory/MFA authentication...{Colors.RESET}")
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
    
    def get_page(self, url):
        """
        Fetch a page from the web interface using the current session.
        Returns a requests.Response object or None on error.
        """
        try:
            response = self.session.get(url, verify=True, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"{Colors.RED}✗ Error fetching {url}: {e}{Colors.RESET}")
            return None
    
    def sanitize_filename(self, name):
        """
        Sanitize filename for safe filesystem storage.
        Removes or replaces invalid characters and trims length.
        """
        # Remove or replace invalid characters
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.strip('. ')
        return name[:200]  # Limit length
    
    def extract_links(self, soup, current_url):
        """
        Extract all relevant links from a page (same domain only).
        Returns a list of dicts with url, text, and href.
        """
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(current_url, href)
            # Only follow links on the same domain
            if urlparse(absolute_url).netloc == urlparse(self.base_url).netloc:
                links.append({
                    'url': absolute_url,
                    'text': link.get_text(strip=True),
                    'href': href
                })
        return links
    
    def save_text_content(self, url, content, title=""):
        """
        Save text content to a file in the output directory.
        Filenames are based on the page title or URL.
        Avoids overwriting by adding a numeric suffix if needed.
        """
        # Create a filename from the URL or title
        if title:
            filename = self.sanitize_filename(title) + ".txt"
        else:
            path_parts = urlparse(url).path.strip('/').split('/')
            filename = self.sanitize_filename('_'.join(path_parts[-2:])) + ".txt"
        if not filename or filename == ".txt":
            filename = "index.txt"
        filepath = os.path.join(self.output_dir, filename)
        # Avoid overwriting - add number suffix if exists
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Source: {url}\n")
                f.write(f"Scraped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                f.write(content)
            print(f"{Colors.GREEN}✓{Colors.RESET} Saved: {os.path.basename(filepath)}")
            self.downloaded_files.append(filepath)
            return filepath
        except Exception as e:
            print(f"{Colors.RED}✗ Error saving {filepath}: {e}{Colors.RESET}")
            return None
    
    def save_html_content(self, url, html, title=""):
        """
        Save HTML content to a file in the output directory.
        Filenames are based on the page title or URL.
        Avoids overwriting by adding a numeric suffix if needed.
        """
        if title:
            filename = self.sanitize_filename(title) + ".html"
        else:
            path_parts = urlparse(url).path.strip('/').split('/')
            filename = self.sanitize_filename('_'.join(path_parts[-2:])) + ".html"
        if not filename or filename == ".html":
            filename = "index.html"
        filepath = os.path.join(self.output_dir, filename)
        # Avoid overwriting
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"{Colors.CYAN}↓{Colors.RESET} Saved HTML: {os.path.basename(filepath)}")
            self.downloaded_files.append(filepath)
            return filepath
        except Exception as e:
            print(f"{Colors.RED}✗ Error saving {filepath}: {e}{Colors.RESET}")
            return None
    
    def scrape_page(self, url, depth=0, max_depth=2):
        """
        Recursively scrape a page and its links up to max_depth.
        Saves both HTML and extracted text content for each page.
        Only follows links on the same domain and relevant to admin/docs.
        """
        if depth > max_depth:
            return
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)
        indent = "  " * depth
        print(f"{indent}{Colors.CYAN}→{Colors.RESET} Scraping: {url}")
        response = self.get_page(url)
        if not response:
            return
        soup = BeautifulSoup(response.text, 'html.parser')
        # Extract title
        title = soup.find('title')
        title_text = title.get_text(strip=True) if title else ""
        # Save HTML
        self.save_html_content(url, response.text, title_text)
        # Extract main content (try common content containers)
        content_selectors = [
            'main',
            'article',
            '.content',
            '#content',
            '.main-content',
            'body'
        ]
        content_text = ""
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                content_text = content.get_text(separator='\n', strip=True)
                break
        if not content_text:
            content_text = soup.get_text(separator='\n', strip=True)
        # Save text content
        if content_text:
            self.save_text_content(url, content_text, title_text)
        # Extract and follow links (only if not too deep)
        if depth < max_depth:
            links = self.extract_links(soup, url)
            for link in links:
                # Skip external links, javascript, anchors
                if (link['url'].startswith('http') and 
                    'javascript:' not in link['url'] and
                    '#' not in link['href']):
                    # Only follow relevant admin/vpbx/docs/help links
                    if any(x in link['url'] for x in ['vpbx', 'admin', 'docs', 'help']):
                        self.scrape_page(link['url'], depth + 1, max_depth)
    
    def generate_index(self):
        """
        Generate an index file (_INDEX.md) listing all downloaded content.
        Includes summary and links to each file.
        """
        index_file = os.path.join(self.output_dir, "_INDEX.md")
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write("# 123NET Internal Documentation\n\n")
                f.write(f"**Scraped:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Total Files:** {len(self.downloaded_files)}\n\n")
                f.write("---\n\n")
                f.write("## Downloaded Files\n\n")
                for filepath in sorted(self.downloaded_files):
                    filename = os.path.basename(filepath)
                    f.write(f"- [{filename}](./{filename})\n")
            print(f"\n{Colors.GREEN}✓ Generated index: {index_file}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Error generating index: {e}{Colors.RESET}")
    
    def scrape_all(self, max_depth=2):
        """
        Main scraping workflow. Starts at base_url, recurses to max_depth, and generates index.
        Prints summary at the end.
        """
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}📚 123NET Documentation Scraper{Colors.RESET}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        print(f"{Colors.CYAN}🎯 Target:{Colors.RESET} {self.base_url}")
        print(f"{Colors.CYAN}📁 Output:{Colors.RESET} {self.output_dir}")
        print(f"{Colors.CYAN}🔍 Max Depth:{Colors.RESET} {max_depth}\n")
        print(f"\n{Colors.CYAN}{'─' * 80}{Colors.RESET}\n")
        # Start scraping
        self.scrape_page(self.base_url, depth=0, max_depth=max_depth)
        # Generate index
        self.generate_index()
        # Summary
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Scraping complete!{Colors.RESET}")
        print(f"\n{Colors.CYAN}📊 Summary:{Colors.RESET}")
        print(f"  • Pages visited: {len(self.visited_urls)}")
        print(f"  • Files saved: {len(self.downloaded_files)}")
        print(f"  • Output directory: {self.output_dir}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        return True

def main():
    """
    Main entry point for the 123NET documentation scraper CLI.
    Parses command-line arguments, initializes the scraper, and runs the workflow.
    """
    import argparse
    parser = argparse.ArgumentParser(
        description='Scrape 123NET internal documentation',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--url',
        default='https://secure.123.net/cgi-bin/web_interface/admin/vpbx.cgi',
        help='URL to scrape (default: 123NET VPBX interface)'
    )
    parser.add_argument(
        '--output',
        default='freepbx-tools/bin/123net_internal_docs/scraped',
        help='Output directory (default: 123net_internal_docs/scraped)'
    )
    parser.add_argument(
        '--depth',
        type=int,
        default=2,
        help='Maximum crawl depth (default: 2)'
    )
    parser.add_argument(
        '--no-ntlm',
        action='store_true',
        help='Disable Windows NTLM authentication'
    )
    args = parser.parse_args()
    # Create scraper
    scraper = DocScraper(
        base_url=args.url,
        output_dir=args.output,
        use_ntlm=not args.no_ntlm
    )
    # Run scraper
    success = scraper.scrape_all(max_depth=args.depth)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
