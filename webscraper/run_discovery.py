import os
from webscraper.tickets_discovery import run_discovery

def main():
    # Target URLs provided by user
    urls = [
        "https://noc-tickets.123.net/view_all",
        "http://10.123.203.1/",
        "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi",
        "https://secure.123.net/cgi-bin/web_interface/admin/askme.cgi",
    ]

    # Output root for artifacts and parsed data
    out_root = os.path.join("webscraper", "ticket-discovery-output")
    os.makedirs(out_root, exist_ok=True)

    # Allowed hosts constraint keeps crawl focused
    allowed = {"noc-tickets.123.net", "10.123.203.1", "secure.123.net"}

    # Use cookies if available to access authenticated content
    cookie_path = os.path.join(os.getcwd(), "cookies.json")
    if not os.path.exists(cookie_path):
        cookie_path = None

    run_discovery(
        start_urls=urls,
        output_root=out_root,
        headless=True,
        max_depth=2,
        max_pages=200,
        allowed_hosts=allowed,
        cookie_file=cookie_path,
    )
    print("Discovery complete. See:", out_root)

if __name__ == "__main__":
    main()
