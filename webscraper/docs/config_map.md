# Configuration Map

## Active runtime path

- `src/webscraper/config.py`
  - Canonical runtime environment/profile/browser resolution used by active scrape runner.

## Selector/static support

- `src/webscraper/ultimate_scraper_config.py`
  - Runtime defaults and selector lists consumed by legacy scraper runtime.
- `src/webscraper/site_selectors.py`
  - Host-specific selector hints for ticket discovery.

## Legacy/transitional config

- `src/webscraper/webscraper_config.py`
  - Legacy static `WEBSCRAPER_CONFIG` compatibility data. Not the primary runtime path.

## Compatibility notes

- `src/webscraper/core/config_loader.py` intentionally loads `ultimate_scraper_config.py` to preserve legacy behavior.
