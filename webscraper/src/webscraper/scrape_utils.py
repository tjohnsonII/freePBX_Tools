"""Legacy utility compatibility wrappers.

Canonical filesystem/json helpers live in :mod:`webscraper.utils.io`.
This module is retained for backwards compatibility with old imports.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from webscraper.utils.io import safe_write_json


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200]


def ensure_dir(path: str | os.PathLike[str]) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def log_error(msg: str, exc: Exception | None = None) -> None:
    if exc:
        logging.error("%s: %s", msg, exc)
    else:
        logging.error(msg)


def timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def load_config(config_path: str):
    if config_path.endswith('.json'):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    if config_path.endswith('.py'):
        import importlib.util

        spec = importlib.util.spec_from_file_location('config', config_path)
        if spec is None:
            raise ImportError(f"Could not load spec for {config_path}")
        config = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise ImportError(f"Spec loader is None for {config_path}")
        spec.loader.exec_module(config)
        return getattr(config, 'WEBSCRAPER_CONFIG', {})
    raise ValueError('Unsupported config file type')


def save_json(data, path: str | os.PathLike[str]) -> None:
    safe_write_json(path, data)


def save_text(data: str, path: str | os.PathLike[str]) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(data, encoding='utf-8')
