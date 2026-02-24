"""Configuration and environment resolution for scraper runtime."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
from types import ModuleType
from typing import Optional


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


def load_config() -> ModuleType:
    """Load ``ultimate_scraper_config`` exactly like the legacy runtime."""
    spec = importlib.util.find_spec("webscraper.ultimate_scraper_config")
    if spec is not None:
        return importlib.import_module("webscraper.ultimate_scraper_config")

    config_path = os.path.join(os.path.dirname(__file__), "..", "ultimate_scraper_config.py")
    config_path = os.path.abspath(config_path)
    file_spec = importlib.util.spec_from_file_location("ultimate_scraper_config", config_path)
    if file_spec is None or file_spec.loader is None:
        raise RuntimeError("Could not load ultimate_scraper_config.py")
    cfg = importlib.util.module_from_spec(file_spec)
    file_spec.loader.exec_module(cfg)
    return cfg


# backward-compatible name used by legacy code
_load_config = load_config


__all__ = ["load_config", "_load_config", "AuthContext", "ScrapeOptions"]
