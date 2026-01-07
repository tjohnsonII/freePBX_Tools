import os
import json
import time
from typing import List, Dict, Set, Tuple, Optional


def run_discovery(
    start_urls: List[str],
    output_root: str,
    headless: bool = True,
    max_depth: int = 2,
    max_pages: int = 200,
    allowed_hosts: Optional[Set[str]] = None,
    cookie_file: Optional[str] = None,
):
    """
    Headless Selenium discovery crawler to map navigation to ticket pages and
    capture page artifacts and parsed tables. Saves outputs under
    {output_root}/{host}/ with HTML, screenshots, summaries, and extracted ticket tables.

    - Respects environment-configured Chrome/Driver via webscraper.ultimate_scraper_config
    - Injects cookies (if provided) to handle authenticated flows
    - Limits crawl by depth and page count to avoid runaway navigation
    """
    from urllib.parse import urlparse, urljoin
    from bs4 import BeautifulSoup
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    # Prepare output root
    os.makedirs(output_root, exist_ok=True)

    # Chrome options
    chrome_options = Options()
    if headless:
        # Prefer modern headless; fall back implicitly if needed
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--allow-insecure-localhost")
    chrome_options.add_argument("--start-maximized")

    # E:\-aware paths via config module
    try:
        from webscraper.ultimate_scraper_config import CHROME_BINARY_PATH, CHROMEDRIVER_PATH
    except Exception:
        CHROME_BINARY_PATH = None
        CHROMEDRIVER_PATH = None
    if CHROME_BINARY_PATH:
        chrome_options.binary_location = CHROME_BINARY_PATH

    # Build driver
    if CHROMEDRIVER_PATH:
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    try:
        try:
            driver.set_page_load_timeout(30)
        except Exception:
            pass

        # Cookie helpers
        def save_cookies(path: str) -> None:
            try:
                cookies = driver.get_cookies()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, indent=2)
            except Exception:
                pass

        def load_and_inject_cookies(path: str, base_url: str) -> bool:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                driver.get(base_url)
                for c in cookies:
                    # Keep common cookie fields
                    keep = {k: c.get(k) for k in ("name","value","path","domain","secure","httpOnly","expiry","sameSite") if c.get(k) is not None}
                    try:
                        driver.add_cookie(keep)
                    except Exception:
                        pass
                return True
            except Exception:
                return False

        # Summary helpers
        def summarize_dom(html: str) -> Dict:
            soup = BeautifulSoup(html, "html.parser")
            # Tables
            tables = []
            for t in soup.find_all("table"):
                headers = [th.get_text(strip=True) for th in t.find_all("th")]
                rows = []
                for tr in t.find_all("tr"):
                    cells = [c.get_text(strip=True) for c in tr.find_all(["td","th"])]
                    if cells:
                        rows.append(cells)
                tables.append({"headers": headers, "rows": rows})
            # Links
            links = []
            for a in soup.find_all("a", href=True):
                links.append({"text": a.get_text(strip=True), "href": a.get("href")})
            return {"tables": tables, "links": links, "title": soup.title.string if soup.title else None}

        # Host-aware header synonyms
        from webscraper.site_selectors import get_link_keywords, get_header_synonyms
        from webscraper.ticket_store import open_db, store_rows

        def is_ticket_table(tbl: Dict, synonyms: Dict) -> bool:
            headers = [h.lower() for h in tbl.get("headers", [])]
            # If any synonym appears in headers, consider it a ticket-like table
            for key, syns in synonyms.items():
                for s in syns:
                    s = s.lower()
                    if any(s in h for h in headers):
                        return True
            # Fallback generic patterns
            patterns = {"ticket", "case", "incident", "subject", "id", "status"}
            return any(any(p in h for p in patterns) for h in headers)

        def extract_table_dicts(tbl: Dict) -> List[Dict]:
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])
            out = []
            if headers:
                for r in rows:
                    d = {}
                    for i, h in enumerate(headers):
                        d[h or f"col{i}"] = r[i] if i < len(r) else None
                    out.append(d)
            else:
                # Fallback: index-based
                for r in rows:
                    d = {f"col{i}": v for i, v in enumerate(r)}
                    out.append(d)
            return out

        def save_page_artifacts(host_dir: str, prefix: str) -> Tuple[str, str, str]:
            html_path = os.path.join(host_dir, f"{prefix}.html")
            png_path = os.path.join(host_dir, f"{prefix}.png")
            json_path = os.path.join(host_dir, f"{prefix}_summary.json")
            # HTML
            html = driver.page_source
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            # Screenshot (best-effort)
            try:
                driver.get_screenshot_as_file(png_path)
            except Exception:
                pass
            # Summary
            summary = summarize_dom(html)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            return html_path, png_path, json_path

        # Crawl each start URL
        for start in start_urls:
            parsed = urlparse(start)
            base = f"{parsed.scheme}://{parsed.netloc}"
            host = parsed.netloc or parsed.path
            if allowed_hosts and host not in allowed_hosts:
                # Skip hosts not permitted
                continue

            host_dir = os.path.join(output_root, host.replace(":", "_"))
            os.makedirs(host_dir, exist_ok=True)

            # Inject cookies for this host if provided
            if cookie_file and os.path.exists(cookie_file):
                load_and_inject_cookies(cookie_file, base)

            # Navigate to start and capture artifacts
            try:
                driver.get(start)
            except Exception:
                # Allow a manual alternative when running non-headless
                pass
            # Auth heuristic: detect login/SSO pages
            try:
                from webscraper.login_heuristics import ensure_authenticated
                authed = ensure_authenticated(driver, start)
                if not authed:
                    print(f"[AUTH] {host}: authentication required; provide cookies.json for headless access.")
            except Exception:
                pass
            save_cookies(os.path.join(host_dir, "cookies.json"))
            save_page_artifacts(host_dir, "root")

            # BFS crawl with relevance prioritization
            visited: Set[str] = set()
            queue: List[Tuple[str, int]] = [(start, 0)]
            page_counter = 0
            aggregated_tickets: List[Dict] = []
            discovered_routes: List[Tuple[str, str]] = []  # (from, to)

            def link_score(text: str, href: str, keywords: List[str]) -> int:
                t = (text or "").lower()
                h = (href or "").lower()
                score = 0
                for pat in keywords:
                    if pat in t or pat in h:
                        score += 1
                return score

            while queue and page_counter < max_pages:
                url, depth = queue.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                try:
                    driver.get(url)
                    page_counter += 1
                except Exception:
                    continue

                # Artifacts per page
                prefix = f"page_{page_counter}"
                html_path, png_path, sum_path = save_page_artifacts(host_dir, prefix)
                # Parse summary for links and ticket tables
                with open(sum_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                # Extract ticket-like tables
                synonyms = get_header_synonyms(host)
                for tbl in summary.get("tables", []):
                    if is_ticket_table(tbl, synonyms):
                        data = extract_table_dicts(tbl)
                        if data:
                            aggregated_tickets.extend(data)
                            outp = os.path.join(host_dir, f"{prefix}_tickets.json")
                            with open(outp, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2)
                            # Store normalized rows into SQLite
                            try:
                                db_path = os.path.join(output_root, "tickets.db")
                                conn = open_db(db_path)
                                store_rows(conn, host, data, synonyms, page_link=url)
                                conn.close()
                            except Exception:
                                pass

                # Discover and enqueue links
                links = summary.get("links", [])
                # Sort by relevance score
                keywords = get_link_keywords(host)
                links.sort(key=lambda x: link_score(x.get("text"), x.get("href"), keywords), reverse=True)
                for lk in links:
                    href = lk.get("href")
                    if not href:
                        continue
                    nxt = urljoin(url, href)
                    # Respect host constraints
                    p2 = urlparse(nxt)
                    if allowed_hosts and p2.netloc not in allowed_hosts:
                        continue
                    if nxt.startswith(base) or (not allowed_hosts):
                        if nxt not in visited:
                            queue.append((nxt, depth + 1))
                            discovered_routes.append((url, nxt))

            # Save aggregated outputs per host
            if aggregated_tickets:
                with open(os.path.join(host_dir, "aggregated_tickets.json"), "w", encoding="utf-8") as f:
                    json.dump(aggregated_tickets, f, indent=2)
            if discovered_routes:
                with open(os.path.join(host_dir, "routes.json"), "w", encoding="utf-8") as f:
                    json.dump(discovered_routes, f, indent=2)

    finally:
        try:
            driver.quit()
        except Exception:
            pass
