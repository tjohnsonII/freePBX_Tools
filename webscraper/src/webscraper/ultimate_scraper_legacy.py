"""Deprecated module alias.

Real implementation lives at ``webscraper.legacy.ultimate_scraper_legacy``.
"""

import sys
from webscraper.legacy import ultimate_scraper_legacy as _legacy

sys.modules[__name__] = _legacy
