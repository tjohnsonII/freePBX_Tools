from __future__ import annotations

import sys
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "webscraper-manager" / "src"
if src.exists() and str(src) not in sys.path:
    sys.path.insert(0, str(src))

from webscraper_manager.cli import main

if __name__ == "__main__":
    main()
