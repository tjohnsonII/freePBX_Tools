"""Deprecated debug entrypoint.

Moved to ``webscraper/scripts/debug/cookie_dump_pause.py``.
"""

from runpy import run_path
from pathlib import Path


def main() -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "debug" / "cookie_dump_pause.py"
    run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
