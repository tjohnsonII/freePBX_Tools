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

class DocScraper:
    def extract_tickets_for_customers(self, customer_handles, output_json="all_tickets.json"):
        """
        For each customer handle, submit a search and extract ticket data.
        Save all tickets as a list of dicts to output_json.
        """
        all_tickets = []
        for handle in customer_handles:
            print(f"{Colors.YELLOW}→ Searching for customer: {handle}{Colors.RESET}")
            post_data = {"customer": handle, "option_fe": "retrieve"}
            tickets = self.extract_ticket_table(post_data=post_data)
            if tickets:
                for t in tickets:
                    t["customer_handle"] = handle
                all_tickets.extend(tickets)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(all_tickets, f, indent=2)
        print(f"{Colors.GREEN}✓ Saved all tickets for {len(customer_handles)} customers to {output_json}{Colors.RESET}")
    def load_netscape_cookies(self, cookie_file):
        """
        Load Netscape-format cookies from a file and set them in the session.
        """
        if not os.path.exists(cookie_file):
            print(f"{Colors.RED}Cookie file not found: {cookie_file}{Colors.RESET}")
            return
        cookies = {}
        with open(cookie_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    name = parts[5]
                    value = parts[6]
                    cookies[name] = value
        self.session.cookies.update(cookies)
        print(f"{Colors.GREEN}✓ Loaded {len(cookies)} cookies from {cookie_file}{Colors.RESET}")
    def save_post_html(self, html, filename="customers_raw.html"):
        """
        Save the full HTML response from the POST request for inspection.
        """
        filepath = os.path.join(self.output_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"{Colors.CYAN}↓ Saved POST HTML: {filepath}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Error saving POST HTML: {e}{Colors.RESET}")
    def post_customers(self, post_data=None):
        """
        Send a POST request to /cgi-bin/web_interface/admin/customers.cgi with browser headers.
        Returns response object or None on error.
        """
        url = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": "Basic dGpvaG5zb246R3JlZW5iaXJkNjQq",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "_ga_65BVXK7F61=GS2.2.s1763664211$o1$g1$t1763664245$j26$l0$h0; handl_landing_page=https%3A%2F%2Fwww.123.net%2F; _gid=GA1.2.1536540736.1764015953; handl_original_ref=https%3A%2F%2Fwww.123.net%2F; handl_ip=2607%3Af790%3Affff%3Aff6e%3Ac4ac%3A24e3%3Ae4d1%3A15a8; handl_url=https%3A%2F%2Fwww.123.net%2F; _ga=GA1.1.1788329368.1763664211; _ga_4070Q1HLDS=GS2.1.s1764031466$o3$g0$t1764031468$j58$l0$h0; noc-tickets=eyJleHBpcmVzIjoxNzY0MDM3MDM4LCJzZXNzaW9uX2lkIjoiYjRiYTU4OTYtYzk1OS0xMWYwLThjNjItYmQyOTg4MGI5YWEyIn0---571a7294229a5f405a1900e3453b5a9a89ee5c356c2e093d2fcb45536dffd710",
            "Host": "secure.123.net",
            "Origin": "https://secure.123.net",
            "Referer": "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        if post_data is None:
            post_data = {"test": "value"}  # Replace with actual POST data as needed
        try:
            response = self.session.post(url, headers=headers, data=post_data, timeout=15)
            response.raise_for_status()
            print(f"{Colors.GREEN}✓ POST succeeded: {response.status_code}{Colors.RESET}")
            print(response.text[:1000])  # Print first 1000 chars for preview
            return response
        except requests.exceptions.RequestException as e:
            print(f"{Colors.RED}✗ POST error: {e}{Colors.RESET}")
            return None

    def extract_ticket_table(self, post_data=None, output_json="tickets.json"):
        """
        Send POST, parse ticket table by header text, and save ticket info as JSON.
        """
        response = self.post_customers(post_data=post_data)
        if not response:
            print(f"{Colors.RED}No response from POST; cannot extract tickets.{Colors.RESET}")
            return None
        # Save full HTML for inspection
        self.save_post_html(response.text)
        soup = BeautifulSoup(response.text, "html.parser")
        # Find the table with Ticket ID header
        table = None
        for t in soup.find_all("table"):
            header = t.find("tr")
            if header and any(th.get_text(strip=True) == "Ticket ID" for th in header.find_all("th")):
                table = t
                break
        if not table:
            print(f"{Colors.RED}No ticket table found in response.{Colors.RESET}")
            return None
        tickets = []
        rows = table.find_all("tr")
        for row in rows[1:]:  # Skip header row
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            link_tag = cells[0].find("a")
            ticket_id = link_tag.text.strip() if link_tag else cells[0].text.strip()
            ticket_url = link_tag["href"] if link_tag else None
            subject = cells[1].text.strip()
            status = cells[2].text.strip()
            priority = cells[3].text.strip()
            created_on = cells[4].text.strip()
            tickets.append({
                "ticket_id": ticket_id,
                "ticket_url": ticket_url,
                "subject": subject,
                "status": status,
                "priority": priority,
                "created_on": created_on
            })
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=2)
        print(f"{Colors.GREEN}✓ Extracted {len(tickets)} tickets to {output_json}{Colors.RESET}")
        return tickets

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
        # Load cookies if cookie file exists
        cookie_file = os.path.join(os.getcwd(), 'cookies.txt')
        if os.path.exists(cookie_file):
            self.load_netscape_cookies(cookie_file)

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

    # Duplicate generate_index and scrape_all removed

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
    parser.add_argument(
        '--post',
        action='store_true',
        help='Send POST request to customers.cgi with browser headers'
    )
    parser.add_argument(
        '--batch',
        type=str,
        help='Path to file with customer handles (one per line) for batch ticket extraction'
    )
    args = parser.parse_args()
    # Create scraper
    scraper = DocScraper(
        base_url=args.url,
        output_dir=args.output,
        use_ntlm=not args.no_ntlm
    )
    if args.batch:
        # Read customer handles from file
        with open(args.batch, 'r', encoding='utf-8') as f:
            handles = [line.strip() for line in f if line.strip()]
        scraper.extract_tickets_for_customers(handles, output_json="all_tickets.json")
        sys.exit(0)
    if args.post:
        # Example POST data; replace with actual form fields as needed
        post_data = {"test": "value"}
        scraper.extract_ticket_table(post_data=post_data)
        sys.exit(0)
    # Run scraper
    success = scraper.scrape_all(max_depth=args.depth)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
