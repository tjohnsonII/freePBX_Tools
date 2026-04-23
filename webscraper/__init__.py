"""Compatibility package shim for src-based webscraper layout."""

from pathlib import Path

_src_pkg = Path(__file__).resolve().parent / "src" / "webscraper"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))
