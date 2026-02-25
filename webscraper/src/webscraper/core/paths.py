"""Path/output helpers for scraper output/debug artifacts."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from webscraper.utils.io import safe_write_json


def ensure_output_dir(path: str) -> str:
    resolved = os.path.abspath(path)
    os.makedirs(resolved, exist_ok=True)
    return resolved


def runtime_edge_profile_dir(output_dir: str) -> str:
    return os.path.join(ensure_output_dir(output_dir), "edge_tmp_profile")


def scrape_run_root(output_root: str, run_id: str) -> str:
    return ensure_output_dir(os.path.join(output_root, run_id))


def scrape_batch_dir(output_root: str, run_id: str, batch_num: int, job_id: str) -> str:
    return ensure_output_dir(os.path.join(scrape_run_root(output_root, run_id), f"batch_{batch_num:03d}", job_id))


def scrape_tmp_profile_dir(output_root: str, run_id: str) -> str:
    return ensure_output_dir(os.path.join(output_root, "tmp_profiles", run_id, "edge_tmp_profile"))


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_run_metadata(output_dir: str, metadata: dict) -> str:
    out_dir = ensure_output_dir(output_dir)
    metadata_path = os.path.join(out_dir, "run_metadata.json")
    payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **metadata}
    safe_write_json(metadata_path, payload)
    return metadata_path


_write_text = write_text
_write_run_metadata = write_run_metadata
