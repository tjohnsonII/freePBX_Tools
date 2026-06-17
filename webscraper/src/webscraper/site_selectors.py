# Host-specific selector and detection hints for ticket discovery

HOST_CONFIG = {
    "noc-tickets.123.net": {
        "link_keywords": [
            "ticket", "view_all", "noc", "queue", "case", "incident", "search", "history"
        ],
        "header_synonyms": {
            "ticket_id": ["ticket id", "id", "caseid", "incident id"],
            "subject": ["subject", "title", "summary"],
            "status": ["status", "state"],
            "opened": ["opened", "created", "date", "created date"],
            "customer": ["customer", "account", "client"],
        },
    },
    "10.123.203.1": {
        "link_keywords": [
            "ticket", "support", "case", "incident", "log", "events"
        ],
        "header_synonyms": {
            "ticket_id": ["id", "event id", "case id"],
            "subject": ["subject", "event", "message"],
            "status": ["status", "severity", "state"],
            "opened": ["time", "timestamp", "date"],
            "customer": ["device", "customer", "account"],
        },
    },
    "secure.123.net": {
        "link_keywords": [
            "customers.cgi", "askme.cgi", "ticket", "case", "incident", "support", "search"
        ],
        "header_synonyms": {
            "ticket_id": ["id", "ticket", "case id"],
            "subject": ["subject", "title"],
            "status": ["status", "state"],
            "opened": ["opened", "created", "date"],
            "customer": ["customer", "company", "handle"],
        },
    },
}

DEFAULT_LINK_KEYWORDS = ["ticket", "view_all", "case", "incident", "customers.cgi", "noc", "support", "search"]

def get_link_keywords(host: str):
    return HOST_CONFIG.get(host, {}).get("link_keywords", DEFAULT_LINK_KEYWORDS)

def get_header_synonyms(host: str):
    return HOST_CONFIG.get(host, {}).get("header_synonyms", {})
