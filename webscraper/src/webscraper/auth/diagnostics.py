"""Authentication diagnostics and smoke test entrypoints."""

from webscraper.ultimate_scraper_legacy import (
    build_auth_strategy_plan,
    smoke_test_edge_driver,
    self_test_auth_strategy_profile_only,
)

__all__ = [
    "build_auth_strategy_plan",
    "smoke_test_edge_driver",
    "self_test_auth_strategy_profile_only",
]
