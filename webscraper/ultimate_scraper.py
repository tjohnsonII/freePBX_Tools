"""Thin, backward-compatible CLI wrapper."""

from __future__ import annotations

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webscraper.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
