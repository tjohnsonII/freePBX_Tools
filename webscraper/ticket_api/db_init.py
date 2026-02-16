from webscraper.ticket_api import db

if __name__ == "__main__":
    db.ensure_indexes(r"webscraper/output/tickets.sqlite")
    print("OK db.ensure_indexes")
