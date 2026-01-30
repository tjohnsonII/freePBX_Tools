#!/usr/bin/env python3
"""Webscraper entrypoint helper.

Prefer module execution (python -m webscraper.<module>). This wrapper keeps a
single root-level entrypoint while forwarding to package modules or legacy
scripts under webscraper/legacy.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

COMMANDS = {
    "ultimate_scraper": {
        "type": "module",
        "target": "webscraper.ultimate_scraper",
        "description": "Run the Selenium-based scraper.",
    },
    "run_discovery": {
        "type": "module",
        "target": "webscraper.run_discovery",
        "description": "Run the ticket discovery crawler.",
    },
    "_smoke_test": {
        "type": "module",
        "target": "webscraper._smoke_test",
        "description": "Run the webscraper smoke test.",
    },
    "ticket_scraper": {
        "type": "script",
        "target": "webscraper/legacy/ticket_scraper.py",
        "description": "Legacy ticket scraper.",
    },
    "ticket_scraper_session": {
        "type": "script",
        "target": "webscraper/legacy/ticket_scraper_session.py",
        "description": "Legacy session-based ticket scraper.",
    },
    "scrape_vpbx_tables": {
        "type": "script",
        "target": "webscraper/legacy/scrape_vpbx_tables.py",
        "description": "Legacy VPBX table scraping.",
    },
    "scrape_vpbx_tables_comprehensive": {
        "type": "script",
        "target": "webscraper/legacy/scrape_vpbx_tables_comprehensive.py",
        "description": "Legacy comprehensive VPBX table scraping.",
    },
    "scrape_123net_docs": {
        "type": "script",
        "target": "webscraper/legacy/scrape_123net_docs.py",
        "description": "Legacy 123net docs scraper.",
    },
    "scrape_123net_docs_selenium": {
        "type": "script",
        "target": "webscraper/legacy/scrape_123net_docs_selenium.py",
        "description": "Legacy Selenium-based docs scraper.",
    },
    "batch_ticket_scrape": {
        "type": "script",
        "target": "webscraper/legacy/batch_ticket_scrape.py",
        "description": "Legacy batch ticket scrape helper.",
    },
    "run_comprehensive_scrape": {
        "type": "script",
        "target": "webscraper/legacy/run_comprehensive_scrape.py",
        "description": "Legacy comprehensive scrape runner.",
    },
    "convert_cookies": {
        "type": "script",
        "target": "webscraper/legacy/convert_cookies.py",
        "description": "Legacy cookie conversion helper.",
    },
    "selenium_to_kb": {
        "type": "script",
        "target": "webscraper/legacy/selenium_to_kb.py",
        "description": "Legacy Selenium results parser.",
    },
    "extract_browser_cookies": {
        "type": "script",
        "target": "webscraper/legacy/extract_browser_cookies.py",
        "description": "Legacy browser cookie extractor.",
    },
}


def _print_help() -> None:
    print("Webscraper entrypoint (repo root).")
    print("Usage: python scraper.py <command> [args]")
    print("\nPrefer: python -m webscraper.<module> [args]")
    print("\nCommands:")
    for name, info in sorted(COMMANDS.items()):
        print(f"  {name:<32} {info['description']}")
    print("\nExamples:")
    print("  python -m webscraper.ultimate_scraper --help")
    print("  python scraper.py ticket_scraper --help")


def _run_module(module: str, args: list[str]) -> None:
    sys.argv = [f"-m {module}"] + args
    runpy.run_module(module, run_name="__main__")


def _run_script(script_path: Path, args: list[str]) -> None:
    sys.argv = [str(script_path)] + args
    runpy.run_path(str(script_path), run_name="__main__")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        _print_help()
        return 0

    command = sys.argv[1]
    config = COMMANDS.get(command)
    if not config:
        print(f"Unknown command: {command}\n")
        _print_help()
        return 2

    args = sys.argv[2:]
    if config["type"] == "module":
        _run_module(config["target"], args)
        return 0

    script_path = Path(__file__).resolve().parent / config["target"]
    if not script_path.exists():
        print(f"Legacy script not found: {script_path}")
        return 1
    _run_script(script_path, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
