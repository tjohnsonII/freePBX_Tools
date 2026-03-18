# Legacy Migration Map

| Old module/file | New location | Still referenced? | Replacement/status | Removal target |
|---|---|---:|---|---|
| `webscraper/ultimate_scraper_legacy.py` | `webscraper/legacy/ultimate_scraper_legacy.py` | Yes | Old path kept as shim for import compatibility. | Remove shim after all callers move. |
| legacy scripts already under `webscraper/legacy/` (`ticket_scraper.py`, `batch_ticket_scrape.py`, etc.) | unchanged | Mixed | Quarantined legacy implementations; not primary runtime path. | Evaluate per-module in future cleanup. |

Notes:
- The active runtime entrypoint remains `webscraper.ultimate_scraper` delegating to legacy runtime for behavior stability.
- Keep compatibility shims until import scans show no external usage.
