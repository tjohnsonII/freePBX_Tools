"""Path/output helpers for scraper output/debug artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def ensure_output_dir(path: str) -> str:
    resolved = os.path.abspath(path)
    os.makedirs(resolved, exist_ok=True)
    return resolved


def runtime_edge_profile_dir(output_dir: str) -> str:
    return os.path.join(ensure_output_dir(output_dir), "edge_tmp_profile")


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_run_metadata(output_dir: str, metadata: dict) -> str:
    out_dir = ensure_output_dir(output_dir)
    metadata_path = os.path.join(out_dir, "run_metadata.json")
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return metadata_path


# backwards-compatible names
_write_text = write_text
_write_run_metadata = write_run_metadata

__all__ = [
    "ensure_output_dir",
    "runtime_edge_profile_dir",
    "write_text",
    "write_run_metadata",
    "_write_text",
    "_write_run_metadata",
]
