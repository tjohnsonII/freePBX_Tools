import os
from .ultimate_scraper import selenium_scrape_tickets

def main():
    out = os.path.join('webscraper', 'test-output')
    os.makedirs(out, exist_ok=True)
    selenium_scrape_tickets(
        url='https://example.com',
        output_dir=out,
        handles=['demo'],
        headless=True,
        vacuum=False,
        aggressive=False,
        cookie_file=None,
    )
    print('DONE')

if __name__ == '__main__':
    main()
