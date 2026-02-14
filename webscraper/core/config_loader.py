"""Configuration and environment resolution for scraper runtime."""

from dataclasses import dataclass
from typing import Optional

from webscraper.ultimate_scraper_legacy import _load_config


@dataclass(frozen=True)
class AuthContext:
    username: Optional[str] = None
    password: Optional[str] = None
    auth_check_url: Optional[str] = None
    auth_mode: Optional[str] = None


@dataclass(frozen=True)
class ScrapeOptions:
    output_dir: str
    tickets_json: Optional[str] = None
    max_tickets: Optional[int] = None
    rate_limit: float = 0.5
    resume: bool = False


__all__ = ["_load_config", "AuthContext", "ScrapeOptions"]
