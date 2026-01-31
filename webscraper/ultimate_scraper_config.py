import os

# NOTE: On managed/domain-joined Windows machines, keep CHROME_BINARY_PATH unset
# so Chrome can be auto-detected (IT policies often vary install locations).

# Optional selector/config knobs used by ultimate_scraper.py. Leave undefined
# unless you need to override defaults. Examples below for future tuning.
#
# SEARCH_INPUT_SELECTORS = [
#     "input#customers",
#     "input[name='customer']",
#     "input[name='customer_handle']",
# ]
# DROPDOWN_CONTAINER_SELECTORS = ["ul.ui-autocomplete", "div.ui-autocomplete"]
# DROPDOWN_ITEM_SELECTORS = ["li.ui-menu-item a", "a.ui-corner-all"]
# SEARCH_BUTTON_SELECTORS = ["input[type='submit'][value*='Search']", "button[type='submit']"]
# SHOW_HIDE_TT_SELECTORS = ["a.show_hide[rel='#slideid5']"]
# XPATH_FALLBACKS = {"search_input": [], "dropdown_items": [], "search_button": []}
# MAX_VACUUM_LINKS = 200
# MAX_SCROLL_STEPS = 50
# AGGRESSIVE_SKIP_PATTERNS = ["new_ticket", "create", "delete", "logout"]
"""
Selector and behavior configuration for ultimate_scraper.py

These defaults are designed to be flexible and work across
minor DOM variations. Tune them based on saved artifacts:
- first_page.html / first_page_summary.json
- debug_dropdown_items_*.txt
- debug_post_search_*.html

Override any of these in your environment as needed.
"""

# Default runtime settings used by ultimate_scraper.py when CLI flags are omitted
DEFAULT_URL = "http://10.123.203.1"
DEFAULT_OUTPUT_DIR = "webscraper/output"
DEFAULT_HEADLESS = True
DEFAULT_HANDLES = ["KPM"]
DEFAULT_COOKIE_FILE = "webscraper/output/kb-run/selenium_cookies.json"

# Preferred browser/driver defaults (override via env if needed)
CHROME_BINARY_PATH = os.environ.get("CHROME_PATH") or None
CHROMEDRIVER_PATH = os.environ.get("CHROMEDRIVER_PATH") or None

# Search input selectors (ordered by priority)
# Tuned: prefer explicit customer handle inputs seen in summaries
SEARCH_INPUT_SELECTORS = [
    "input#search_phrase",
    "input#customers",
    "input[name='customer']",
    "input[name='customer_handle']",
    "input[type='text'][placeholder*='Customer']",
    "input[type='text'][placeholder*='Search for Stuff']",
    "input[type='text'][placeholder*='Search']",
    "input[id*='customer']",
]

# Dropdown container and item selectors
DROPDOWN_CONTAINER_SELECTORS = [
    "ul.ui-autocomplete",
    "div.ui-autocomplete",
    "ul.typeahead.dropdown-menu",
    "div.typeahead.dropdown-menu",
    "div[role='listbox']",
]

DROPDOWN_ITEM_SELECTORS = [
    "li.ui-menu-item a",
    "a.ui-corner-all",
    "li.autocomplete-item",
    "li.typeahead-item",
    "li[role='option']",
    "div[role='option']",
]

# Search button selectors
SEARCH_BUTTON_SELECTORS = [
    "#submit",
    "input[type='submit'][value*='Search']",
    "button[type='submit']",
    "button#searchButton",
    "button[name='searchButton']",
    "input[type='button'][value*='Search']",
    "input[value*='Search']",
]

# Aggressive crawl configuration
MAX_VACUUM_LINKS = 1000
MAX_SCROLL_STEPS = 200
AGGRESSIVE_SKIP_PATTERNS = [
    "new_ticket",
    "create",
    "delete",
    "logout",
    "signout",
    "remove",
    "drop",
]

# Show/Hide trouble ticket data link/button
SHOW_HIDE_TT_SELECTORS = [
    "a.show_hide[rel='#slideid5']",
    "a#showHideTroubleTicketData",
    "button#showHideTroubleTicketData",
    "a[href*='Trouble Ticket']",
]

# Pagination selectors
PAGINATION_CONTAINER_SELECTORS = [
    "ul.pagination",
    "nav.pagination",
    "div.pagination",
    "div.dataTables_paginate",
]

PAGINATION_NEXT_SELECTORS = [
    "a.page-link[rel='next']",
    "button.page-link[rel='next']",
    "a[aria-label='Next']",
    "button[aria-label='Next']",
    "a.paginate_button.next",
    "span.next a",
]

# Optional XPath fallbacks (used by the scraper if CSS fails)
XPATH_FALLBACKS = {
    "search_input": [
        "//input[@id='customers']",
        "//input[@name='customer']",
        "//input[@name='customer_handle']",
    ],
    "search_button": [
        "//input[@type='submit' and contains(@value,'Search')]",
        "//button[@type='submit']",
        "//input[contains(@value,'Search')]",
        "//button[contains(.,'Search')]",
    ],
    "dropdown_items": [
        "//ul[contains(@class,'ui-autocomplete')]//li[contains(@class,'ui-menu-item')]//a",
    ],
    "pagination_next": [
        "//a[@aria-label='Next']",
        "//a[contains(@class,'paginate_button') and contains(@class,'next')]",
    ],
}

# Aggressive ticket parsing configuration
COMMENT_CONTAINER_SELECTORS = [
    ".comments",
    ".notes",
    ".activity",
    ".history",
    ".timeline",
]
COMMENT_ITEM_SELECTORS = [
    "li",
    "div.comment",
    "tr",
]
ATTACHMENT_PATTERNS = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".zip", ".tar", ".gz", ".7z",
    "attachment", "download",
]
