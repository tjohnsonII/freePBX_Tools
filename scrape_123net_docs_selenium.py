#!/usr/bin/env python3
"""
123NET Internal Documentation Scraper (Selenium Version)
Uses Selenium to scrape documentation from secure.123.net with existing browser session
Saves content to 123net_internal_docs folder for offline reference
"""

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
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime

class Colors:
    """ANSI color codes"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'

class SeleniumDocScraper:
    """Scraper for 123NET internal documentation using Selenium"""
    
    def __init__(self, base_url, output_dir, headless=False):
        self.base_url = base_url
        self.output_dir = output_dir
        self.visited_urls = set()
        self.downloaded_files = []
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Setup Chrome driver
        print(f"{Colors.CYAN}Initializing Chrome browser...{Colors.RESET}")
        
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        
        # Use existing user profile to preserve authentication
        # This will open Chrome with your existing session
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)
            print(f"{Colors.GREEN}✓ Browser initialized{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Failed to initialize browser: {e}{Colors.RESET}")
            print(f"{Colors.YELLOW}Please install Chrome and chromedriver{Colors.RESET}")
            sys.exit(1)
    
    def wait_for_auth(self):
        """Wait for user to complete authentication"""
        print(f"\n{Colors.YELLOW}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠  AUTHENTICATION REQUIRED{Colors.RESET}")
        print(f"{Colors.YELLOW}{'═' * 80}{Colors.RESET}")
        print(f"\n{Colors.CYAN}Please complete the following steps:{Colors.RESET}")
        print(f"  1. Log in to 123NET in the browser window")
        print(f"  2. Complete MFA if prompted")
        print(f"  3. Wait for the admin/VPBX page to load")
        print(f"\n{Colors.CYAN}The scraper will automatically detect when you're logged in...{Colors.RESET}")
        print(f"{Colors.YELLOW}(Timeout: 5 minutes | Press Ctrl+C to cancel){Colors.RESET}\n")
        
        authenticated = False
        timeout = 300  # 5 minutes
        start_time = time.time()
        last_url = ""
        
        while not authenticated and (time.time() - start_time) < timeout:
            try:
                # Check if we're on the main admin page (not login page)
                current_url = self.driver.current_url
                
                # Show URL changes to give user feedback
                if current_url != last_url:
                    print(f"{Colors.BLUE}  Current URL: {current_url}{Colors.RESET}")
                    last_url = current_url
                
                # Check multiple indicators of successful authentication
                page_source = self.driver.page_source.lower()
                
                # Not on login page anymore AND on admin/vpbx page
                is_authenticated = (
                    'login' not in current_url.lower() and
                    ('vpbx' in current_url or 'admin' in current_url) and
                    (
                        'logout' in page_source or
                        'sign out' in page_source or
                        'admin' in page_source or
                        'dashboard' in page_source
                    )
                )
                
                if is_authenticated:
                    authenticated = True
                    print(f"\n{Colors.GREEN}{'═' * 80}{Colors.RESET}")
                    print(f"{Colors.GREEN}{Colors.BOLD}✓ Authentication successful!{Colors.RESET}")
                    print(f"{Colors.GREEN}{'═' * 80}{Colors.RESET}\n")
                    # Give user a moment to see the success message
                    time.sleep(2)
                    break
                
                time.sleep(3)
                
            except Exception as e:
                print(f"{Colors.RED}  Error checking auth status: {e}{Colors.RESET}")
                time.sleep(3)
        
        if not authenticated:
            print(f"\n{Colors.RED}{'═' * 80}{Colors.RESET}")
            print(f"{Colors.RED}✗ Authentication timeout - 5 minutes elapsed{Colors.RESET}")
            print(f"{Colors.RED}{'═' * 80}{Colors.RESET}\n")
            return False
        
        return True
    
    def get_page_content(self, url):
        """Navigate to URL and get page content"""
        try:
            print(f"{Colors.BLUE}→ Fetching: {url}{Colors.RESET}")
            self.driver.get(url)
            
            # Wait for page to load - look for body content
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                print(f"{Colors.YELLOW}⚠ Page load timeout{Colors.RESET}")
            
            # Additional wait for dynamic content
            time.sleep(3)
            
            # Get page source
            html = self.driver.page_source
            
            # Check for authentication issues
            if 'unauthorized' in html.lower() or 'login' in self.driver.current_url.lower():
                print(f"{Colors.YELLOW}⚠ Authentication required{Colors.RESET}")
                return None
            
            # Check if page has meaningful content
            if len(html.strip()) < 100:
                print(f"{Colors.YELLOW}⚠ Page appears empty{Colors.RESET}")
            
            return html
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error: {e}{Colors.RESET}")
            return None
    
    def sanitize_filename(self, name):
        """Sanitize filename for safe filesystem storage"""
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.strip('. ')
        return name[:200]
    
    def save_content(self, url, html, title=""):
        """Save page content to files"""
        
        # Generate filename
        if title:
            filename = self.sanitize_filename(title)
        else:
            path_parts = urlparse(url).path.strip('/').split('/')
            filename = self.sanitize_filename('_'.join(path_parts[-2:]))
        
        if not filename:
            filename = "index"
        
        # Save HTML
        html_file = os.path.join(self.output_dir, filename + ".html")
        
        # Avoid overwriting
        base, ext = os.path.splitext(html_file)
        counter = 1
        while os.path.exists(html_file):
            html_file = f"{base}_{counter}{ext}"
            counter += 1
        
        try:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"{Colors.GREEN}  ✓ Saved HTML: {os.path.basename(html_file)}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}  ✗ Error saving HTML: {e}{Colors.RESET}")
            return
        
        # Extract and save text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove scripts and styles
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator='\n', strip=True)
        
        text_file = html_file.replace('.html', '.txt')
        try:
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Source: {url}\n")
                f.write(f"Scraped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                f.write(text)
            print(f"{Colors.GREEN}  ✓ Saved text: {os.path.basename(text_file)}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}  ✗ Error saving text: {e}{Colors.RESET}")
        
        self.downloaded_files.append({
            'url': url,
            'html_file': html_file,
            'text_file': text_file,
            'timestamp': datetime.now().isoformat()
        })
    
    def extract_links(self, html, current_url):
        """Extract all links from page"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not href or not isinstance(href, str):
                continue
                
            absolute_url = urljoin(current_url, href)
            
            # Only follow same-domain links
            if urlparse(absolute_url).netloc == urlparse(self.base_url).netloc:
                # Skip common trap URLs
                if not any(x in href.lower() for x in ['logout', 'login', 'javascript:', '#']):
                    links.append({
                        'url': absolute_url,
                        'text': link.get_text(strip=True)
                    })
        
        return links
    
    def scrape_page(self, url, depth=0, max_depth=2):
        """Recursively scrape a page"""
        
        if depth > max_depth:
            return
        
        if url in self.visited_urls:
            return
        
        self.visited_urls.add(url)
        
        indent = "  " * depth
        print(f"{indent}{Colors.CYAN}→{Colors.RESET} Scraping: {url}")
        
        # Get page content
        html = self.get_page_content(url)
        if not html:
            return
        
        # Get title
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.find('title')
        title_text = title.get_text(strip=True) if title else ""
        
        # Save content
        self.save_content(url, html, title_text)
        
        # Extract and follow links if not too deep
        if depth < max_depth:
            links = self.extract_links(html, url)
            
            # Filter for relevant admin/docs links
            relevant_links = [
                l for l in links 
                if any(x in l['url'].lower() for x in ['vpbx', 'admin', 'docs', 'help', 'cgi-bin'])
            ]
            
            print(f"{indent}  Found {len(relevant_links)} relevant links")
            
            for link in relevant_links[:10]:  # Limit to 10 links per page
                self.scrape_page(link['url'], depth + 1, max_depth)
    
    def generate_index(self):
        """Generate index of downloaded files"""
        
        index_file = os.path.join(self.output_dir, "_INDEX.md")
        
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write("# 123NET Internal Documentation\n\n")
                f.write(f"**Scraped:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Total Files:** {len(self.downloaded_files)}\n\n")
                f.write("---\n\n")
                f.write("## Downloaded Files\n\n")
                
                for item in self.downloaded_files:
                    filename = os.path.basename(item['html_file'])
                    f.write(f"- [{filename}](./{filename}) - {item['url']}\n")
            
            print(f"\n{Colors.GREEN}✓ Generated index: {index_file}{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error generating index: {e}{Colors.RESET}")
    
    def scrape_all(self, max_depth=2):
        """Main scraping workflow"""
        
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}📚 123NET Documentation Scraper (Selenium){Colors.RESET}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        
        print(f"{Colors.CYAN}🎯 Target:{Colors.RESET} {self.base_url}")
        print(f"{Colors.CYAN}📁 Output:{Colors.RESET} {self.output_dir}")
        print(f"{Colors.CYAN}🔍 Max Depth:{Colors.RESET} {max_depth}\n")
        
        # Navigate to base URL
        try:
            print(f"{Colors.BLUE}Navigating to {self.base_url}...{Colors.RESET}")
            self.driver.get(self.base_url)
            
            print(f"{Colors.CYAN}Waiting for page to load (10 seconds)...{Colors.RESET}")
            time.sleep(10)  # Give page and redirects time to complete
            
            current_url = self.driver.current_url
            print(f"{Colors.BLUE}Current URL: {current_url}{Colors.RESET}")
            
            # Always give user the authentication prompt since MFA may be required
            print(f"\n{Colors.YELLOW}{'═' * 80}{Colors.RESET}")
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠  PLEASE AUTHENTICATE IF PROMPTED{Colors.RESET}")
            print(f"{Colors.YELLOW}{'═' * 80}{Colors.RESET}")
            print(f"\n{Colors.CYAN}If you see a login page or MFA prompt:{Colors.RESET}")
            print(f"  1. Enter your credentials")
            print(f"  2. Complete MFA")
            print(f"  3. The scraper will detect when you're logged in")
            print(f"\n{Colors.CYAN}Waiting 30 seconds for you to authenticate...{Colors.RESET}\n")
            
            # Give user 30 seconds to start authentication
            time.sleep(30)
            
            # Now check if we need to wait longer
            current_url = self.driver.current_url
            if 'login' in current_url.lower() or 'auth' in current_url.lower():
                print(f"{Colors.YELLOW}Still on login page - continuing to wait...{Colors.RESET}")
                if not self.wait_for_auth():
                    print(f"{Colors.RED}✗ Failed to authenticate{Colors.RESET}")
                    return False
            else:
                print(f"{Colors.GREEN}✓ Authentication complete or not required{Colors.RESET}\n")
                time.sleep(2)  # Brief pause
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error accessing site: {e}{Colors.RESET}")
            return False
        
        print(f"{Colors.CYAN}{'─' * 80}{Colors.RESET}\n")
        print(f"{Colors.BOLD}Starting to scrape pages...{Colors.RESET}\n")
        
        # Start scraping
        self.scrape_page(self.base_url, depth=0, max_depth=max_depth)
        
        # Generate index
        print(f"\n{Colors.BOLD}Generating index file...{Colors.RESET}")
        self.generate_index()
        
        # Summary
        print(f"\n{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Scraping complete!{Colors.RESET}")
        print(f"\n{Colors.CYAN}📊 Summary:{Colors.RESET}")
        print(f"  • Pages visited: {len(self.visited_urls)}")
        print(f"  • Files saved: {len(self.downloaded_files)}")
        print(f"  • Output directory: {self.output_dir}")
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}\n")
        
        print(f"{Colors.YELLOW}Browser will close in 5 seconds...{Colors.RESET}")
        time.sleep(5)
        
        return True
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Scrape 123NET internal documentation using Selenium',
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
        '--headless',
        action='store_true',
        help='Run browser in headless mode (no GUI)'
    )
    
    args = parser.parse_args()
    
    scraper = None
    try:
        # Create scraper
        scraper = SeleniumDocScraper(
            base_url=args.url,
            output_dir=args.output,
            headless=args.headless
        )
        
        # Run scraper
        success = scraper.scrape_all(max_depth=args.depth)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Interrupted by user{Colors.RESET}")
        sys.exit(1)
    
    finally:
        if scraper:
            scraper.close()

if __name__ == '__main__':
    main()
