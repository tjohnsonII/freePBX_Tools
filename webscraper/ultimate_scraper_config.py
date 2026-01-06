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

# Preferred E:\ installs for browser and driver (override via env if needed)
CHROME_BINARY_PATH = None  # e.g., "E:\\DevTools\\Chromium\\chrome.exe"
CHROMEDRIVER_PATH = None   # e.g., "E:\\DevTools\\WebDriver\\chromedriver.exe"
CHROME_BINARY_PATH = CHROME_BINARY_PATH or (
    __import__('os').environ.get('CHROME_PATH')
)
CHROMEDRIVER_PATH = CHROMEDRIVER_PATH or (
    __import__('os').environ.get('CHROMEDRIVER_PATH')
)

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

# Ticket table and link selectors
TICKET_TABLE_SELECTORS = [
    "table#tickets",
    "table.ticket-table",
    "table[data-table='tickets']",
    "table.dataTable",
]

TICKET_LINK_SELECTORS = [
    "a.ticket-link",
    "a[href*='noc-tickets.123.net/ticket/']",
    "a[href*='ticket']",
    "a[href*='TroubleTicket']",
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

# Waits and timing
DEFAULT_WAIT_SECONDS = 20
SHORT_WAIT_SECONDS = 6

# Whether to click the first dropdown item after typing the handle
CLICK_FIRST_DROPDOWN_ITEM = True

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
# Webscraper configuration file
# Fill in your actual scraping parameters, selectors, credentials, and output settings
# NEVER commit this file with real credentials to git!

WEBSCRAPER_CONFIG = {
        "url_settings": {
            "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi": {
                "method": "POST",
                "headers": {
                    "Authorization": "REDACTED",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                "post_data": {
                    "customer": "REDACTED",
                    "option_fe": "retrieve"
                }
            }
        },
    "environments": {
        "default": {
            "base_urls": [
                "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"

            ],
            "output_dir": "webscraper/output/",
            "credentials": {
                "username": "REDACTED",  # If needed for login
                "password": "REDACTED"   # If needed for login
            }
        }
    },
    "selectors": {
        "main_content": ["main", "article", ".content", "#content", ".main-content", "body"],
        "table": ["table", "table#tickets", ".ticket-table"],
        "links": "a[href]"
    },
    "timeout": 15,
    "max_depth": 2,
    "retry": {
        "max_attempts": 3,
        "backoff_factor": 2
    },
    "logging": {
        "level": "INFO",
        "log_file": "webscraper.log"
    },
    "output_format": "json",  # or "csv"
    "save_html": True,
    "save_text": True,
    # Generate ticket URLs for all handles
    "handles": [
        "07Q","2H8","2V2","3CO","3YE","472","4TI","52H","5TT","6ME","6U1","84Z","87I","88V","894","8WV","994","A9F","AAM","AAO","AAU","ABG","ABJ","ACG","AEG","AGC","AHE","AIX","AIZ","AKI","ALH","ALZ","ANG","APR","APS","APW","APY","ASK","ASX","ASY","ATH","ATO","ATQ","ATS","ATV","AUT","AVE","AWE","BAM","BAO","BAQ","BAT","BAW","BBM","BDB","BED","BEG","BEN","BF7","BFC","BFD","BFE","BHF","BHK","BIQ","BIS","BLC","BLE","BLI","BLP","BPL","BRP","BSC","BSD","BSU","BTG","BWN","CAI","CAO","CAS","CBB","CBD","CBP","CDW","CEQ","CF9","CFM","CIM","CIX","CLS","CMB","CML","CMO","CMP","CNB","COX","COY","CPU","CQO","CRB","CSU","CT9","CTK","CTR","CU8","CUP","CVC","CYM","D2U","DAK","DAM","DAS","DAW","DBI","DBL","DBP","DBQ","DC6","DCN","DCU","DCX","DHC","DHE","DI1","DIL","DIM","DIP","DIU","DIV","DIY","DJD","DML","DPO","DPS","DRE","DRR","DSU","DTD","DTG","EAF","EBC","ECE","ECI","ED2","EDA","EDE","EE5","EEB","EIH","EL2","ELA","EM3","EMC","EMP","EO5","EPR","ESM","ETB","ETC","EWA","FAM","FAN","FCG","FCP","FCS","FDH","FFC","FFP","FH1","FI8","FIE","FII","FMJ","FMT","FOK","FPU","FR5","FRF","FRJ","FSP","FUA","FWA","FWE","FWS","G12","GA2","GAP","GAY","GBA","GBF","GFA","GFP","GGC","GHT","GL0","GLG","GPD","GPS","GR5","GRL","GRM","GRR","GRU","GTJ","GUS","GVM","HAJ","HAP","HBU","HC0","HCK","HCL","HCQ","HCT","HCU","HCV","HCY","HDB","HEB","HFA","HFB","HFM","HFO","HFS","HG8","HHG","HHL","HME","HP6","HP9","HPB","HPI","HTO","HTW","HVS","I11","I36","ICQ","IFC","IGD","IIE","IIQ","ILL","INS","IPE","IPO","IPX","ISC","IST","IWI","IWL","JAK","JAT","JBG","JCC","JD4","JDC","JGA","JHE","JIA","JIC","JIG","JL5","JLI","JLO","JLW","JPD","JPR","JQ9","JRA","JSB","JSC","JSD","JW1","KAD","KC4","KCE","KGA","KGR","KKT","KOR","KPM","KSC","KSI","KSV","KUS","LAU","LB4","LCC","LCE","LCK","LCO","LE5","LEA","LFB","LFC","LFR","LGO","LGR","LLS","LLT","LMH","LMI","LML","LMM","LNO","LOL","LOO","LOP","LRE","LSD","LSP","LST","LTA","LTB","LTE","MA0","MAM","MAO","MAP","MBP","MCY","MD4","MDB","MDM","MEJ","MFA","MFB","MHQ","MHR","MJM","MLC","MLD","MLL","MMK","MOD","MPE","MPN","MPR","MPV","MPY","MRC","MSY","MTW","MTZ","MUP","MVF","MW7","MWE","NAD","NBF","NCU","NFS","NGD","NH6","NI3","NMO","NSK","NTR","O3H","O5U","O7W","ODI","OFS","OIB","OMA","OOT","OPT","OTO","OTP","OUN","OVA","PAJ","PBM","PCZ","PDA","PDE","PEK","PFB","PFD","PFS","PH5","PHD","PHF","PIG","PK1","PLA","PMG","PMO","PO3","POP","PRB","PRN","PSN","PSP","PSU","PSX","PT8","PTA","PTG","PZZ","QWD","RAF","RCN","REE","RFS","RHT","RI6","RLF","RMF","RMS","RNI","ROR","ROU","RPD","RRO","RT6","RTA","RTH","RVS","S3H","SAD","SCS","SDB","SDC","SE7","SFF","SFH","SFK","SFR","SG3","SGC","SIV","SKC","SLG","SLJ","SMF","SMG","SMK","SMQ","SPK","SPP","SPV","SRE","STV","SUH","SUN","SWP","SXI","T7O","TAF","TAM","TAO","TB5","TEI","TF1","TGD","TH6","THC","THG","TIL","TKT","TMS","TNA","TOC","TPA","TPB","TSZ","TTN","TTU","TUA","TVL","TWB","U91","UA5","UAA","UAB","UAI","UCW","UFI","UHR","ULI","UM0","UP8","UVM","VCB","VDJ","VE1","VEI","VEX","VFD","VHB","VM7","VON","VRA","VSA","W5D","WBE","WCJ","WCN","WCP","WCR","WEE","WEN","WER","WIA","WIC","WLP","WMR","WMS","WOI","WS7","WSF","WSG","WWL","WWO","WZG","X29","XGP","YA4","YA5","YA6","YA8","YAA","YAB","YAC","YAI","YCM","YHO","YPS","YSD","YYL","ZC0","ZCU","ZKX","ZPO"
    ],
    "urls": [
        *(f"https://portal.123.net/admin/new_tickets.cgi/ticket/{handle}" for handle in [
            "07Q","2H8","2V2","3CO","3YE","472","4TI","52H","5TT","6ME","6U1","84Z","87I","88V","894","8WV","994","A9F","AAM","AAO","AAU","ABG","ABJ","ACG","AEG","AGC","AHE","AIX","AIZ","AKI","ALH","ALZ","ANG","APR","APS","APW","APY","ASK","ASX","ASY","ATH","ATO","ATQ","ATS","ATV","AUT","AVE","AWE","BAM","BAO","BAQ","BAT","BAW","BBM","BDB","BED","BEG","BEN","BF7","BFC","BFD","BFE","BHF","BHK","BIQ","BIS","BLC","BLE","BLI","BLP","BPL","BRP","BSC","BSD","BSU","BTG","BWN","CAI","CAO","CAS","CBB","CBD","CBP","CDW","CEQ","CF9","CFM","CIM","CIX","CLS","CMB","CML","CMO","CMP","CNB","COX","COY","CPU","CQO","CRB","CSU","CT9","CTK","CTR","CU8","CUP","CVC","CYM","D2U","DAK","DAM","DAS","DAW","DBI","DBL","DBP","DBQ","DC6","DCN","DCU","DCX","DHC","DHE","DI1","DIL","DIM","DIP","DIU","DIV","DIY","DJD","DML","DPO","DPS","DRE","DRR","DSU","DTD","DTG","EAF","EBC","ECE","ECI","ED2","EDA","EDE","EE5","EEB","EIH","EL2","ELA","EM3","EMC","EMP","EO5","EPR","ESM","ETB","ETC","EWA","FAM","FAN","FCG","FCP","FCS","FDH","FFC","FFP","FH1","FI8","FIE","FII","FMJ","FMT","FOK","FPU","FR5","FRF","FRJ","FSP","FUA","FWA","FWE","FWS","G12","GA2","GAP","GAY","GBA","GBF","GFA","GFP","GGC","GHT","GL0","GLG","GPD","GPS","GR5","GRL","GRM","GRR","GRU","GTJ","GUS","GVM","HAJ","HAP","HBU","HC0","HCK","HCL","HCQ","HCT","HCU","HCV","HCY","HDB","HEB","HFA","HFB","HFM","HFO","HFS","HG8","HHG","HHL","HME","HP6","HP9","HPB","HPI","HTO","HTW","HVS","I11","I36","ICQ","IFC","IGD","IIE","IIQ","ILL","INS","IPE","IPO","IPX","ISC","IST","IWI","IWL","JAK","JAT","JBG","JCC","JD4","JDC","JGA","JHE","JIA","JIC","JIG","JL5","JLI","JLO","JLW","JPD","JPR","JQ9","JRA","JSB","JSC","JSD","JW1","KAD","KC4","KCE","KGA","KGR","KKT","KOR","KPM","KSC","KSI","KSV","KUS","LAU","LB4","LCC","LCE","LCK","LCO","LE5","LEA","LFB","LFC","LFR","LGO","LGR","LLS","LLT","LMH","LMI","LML","LMM","LNO","LOL","LOO","LOP","LRE","LSD","LSP","LST","LTA","LTB","LTE","MA0","MAM","MAO","MAP","MBP","MCY","MD4","MDB","MDM","MEJ","MFA","MFB","MHQ","MHR","MJM","MLC","MLD","MLL","MMK","MOD","MPE","MPN","MPR","MPV","MPY","MRC","MSY","MTW","MTZ","MUP","MVF","MW7","MWE","NAD","NBF","NCU","NFS","NGD","NH6","NI3","NMO","NSK","NTR","O3H","O5U","O7W","ODI","OFS","OIB","OMA","OOT","OPT","OTO","OTP","OUN","OVA","PAJ","PBM","PCZ","PDA","PDE","PEK","PFB","PFD","PFS","PH5","PHD","PHF","PIG","PK1","PLA","PMG","PMO","PO3","POP","PRB","PRN","PSN","PSP","PSU","PSX","PT8","PTA","PTG","PZZ","QWD","RAF","RCN","REE","RFS","RHT","RI6","RLF","RMF","RMS","RNI","ROR","ROU","RPD","RRO","RT6","RTA","RTH","RVS","S3H","SAD","SCS","SDB","SDC","SE7","SFF","SFH","SFK","SFR","SG3","SGC","SIV","SKC","SLG","SLJ","SMF","SMG","SMK","SMQ","SPK","SPP","SPV","SRE","STV","SUH","SUN","SWP","SXI","T7O","TAF","TAM","TAO","TB5","TEI","TF1","TGD","TH6","THC","THG","TIL","TKT","TMS","TNA","TOC","TPA","TPB","TSZ","TTN","TTU","TUA","TVL","TWB","U91","UA5","UAA","UAB","UAI","UCW","UFI","UHR","ULI","UM0","UP8","UVM","VCB","VDJ","VE1","VEI","VEX","VFD","VHB","VM7","VON","VRA","VSA","W5D","WBE","WCJ","WCN","WCP","WCR","WEE","WEN","WER","WIA","WIC","WLP","WMR","WMS","WOI","WS7","WSF","WSG","WWL","WWO","WZG","X29","XGP","YA4","YA5","YA6","YA8","YAA","YAB","YAC","YAI","YCM","YHO","YPS","YSD","YYL","ZC0","ZCU","ZKX","ZPO"
        ])
    ]
}
