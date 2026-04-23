from pathlib import Path
import sys

from webscraper.paths import tickets_db_path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from webscraper.ticket_api import db

if __name__ == "__main__":
    target = str(tickets_db_path())
    db.ensure_indexes(target)
    print(f"DB init complete: indexes ensured for {target} (repo root: {REPO_ROOT})")
