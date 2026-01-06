# Scraper configuration file
# Copy to config.py and fill in values for production use

SCRAPER_CONFIG = {
    "environments": {
        "production": {
            "base_urls": [
                "https://secure.123.net/vpbx/",
                "https://secure.123.net/docs/"
            ],
            "output_dir": "data/analysis-output/",
            "credentials": {
                "username": "YOUR_USERNAME",
                "password": "YOUR_PASSWORD"
            }
        },
        "staging": {
            "base_urls": [
                "https://staging.123.net/vpbx/",
                "https://staging.123.net/docs/"
            ],
            "output_dir": "data/staging-output/",
            "credentials": {
                "username": "STAGING_USER",
                "password": "STAGING_PASS"
            }
        }
    },
    "selectors": {
        "main_content": ["main", "article", ".content", "#content", ".main-content", "body"],
        "table": ["table.data-table", "table#tickets", "table.tickets-table"],
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
        "log_file": "scraper.log"
    },
    "output_format": "json",  # or "csv"
    "save_html": True,
    "save_text": True
}

# NEVER commit config.py with real credentials!
