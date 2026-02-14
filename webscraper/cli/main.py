"""CLI entrypoint for the webscraper ultimate scraper."""

from __future__ import annotations

from webscraper import ultimate_scraper_legacy as legacy


def main() -> int:
    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
