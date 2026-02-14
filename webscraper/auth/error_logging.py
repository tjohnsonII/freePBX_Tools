from __future__ import annotations

import os
import traceback
from typing import Optional


def _safe_name(value: Optional[str]) -> str:
    return (value or "").strip() or "unknown"


def log_exception(context: str, exc: Exception, out_dir: Optional[str], filename: str) -> Optional[str]:
    """Print a short exception line and persist full traceback for diagnostics."""
    target_root = os.path.abspath(out_dir or os.getcwd())
    debug_dir = os.path.join(target_root, "debug")
    os.makedirs(debug_dir, exist_ok=True)

    safe_filename = _safe_name(filename)
    if not safe_filename.endswith(".txt"):
        safe_filename = f"{safe_filename}.txt"
    trace_path = os.path.join(debug_dir, safe_filename)

    trace = traceback.format_exc()
    if not trace or trace == "NoneType: None\n":
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    with open(trace_path, "w", encoding="utf-8") as handle:
        handle.write(trace)

    print(f"[AUTH] {context}:{type(exc).__name__}: {exc}")
    print(f"[AUTH] traceback saved: {trace_path}")
    return trace_path

