from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from webscraper.ticket_api import db

if __name__ == "__main__":
    db.ensure_indexes(r"webscraper/output/tickets.sqlite")
    print(f"DB init complete: indexes ensured for webscraper/output/tickets.sqlite (repo root: {REPO_ROOT})")
