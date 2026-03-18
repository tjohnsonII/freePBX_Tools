"""Compatibility re-export of :mod:`webscraper.utils.io`.

New code should import directly from ``webscraper.utils.io``.  This shim
exists so that any older code using ``from webscraper.utils.io_utils import …``
continues to work without changes.
"""
from __future__ import annotations

from webscraper.utils.io import canonical_json_bytes, make_run_id, safe_write_json, utc_now_iso

__all__ = ["canonical_json_bytes", "make_run_id", "safe_write_json", "utc_now_iso"]
