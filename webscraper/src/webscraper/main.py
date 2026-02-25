import argparse

from webscraper.scraping.runner import run_scrape
from webscraper.ticket_api.app import run_api  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", default="incremental")
    args = parser.parse_args()

    run_scrape(mode=args.mode, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
