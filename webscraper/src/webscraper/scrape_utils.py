"""
Central utility functions for scraping scripts
Place shared helpers here and import as needed
"""
import re
import os
import logging
from datetime import datetime
from urllib.parse import urlparse

import json

def sanitize_filename(name):
    """Sanitize filename for safe filesystem storage."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200]

def ensure_dir(path):
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)

def log_error(msg, exc=None):
    """Log error with optional exception info."""
    if exc:
        logging.error(f"{msg}: {exc}")
    else:
        logging.error(msg)

def timestamp():
    """Return current timestamp string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_domain(url):
    """Extract domain from URL."""
    return urlparse(url).netloc

def load_config(config_path):
    """Load scraper config from a JSON or Python file."""
    if config_path.endswith('.json'):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif config_path.endswith('.py'):
        import importlib.util
        spec = importlib.util.spec_from_file_location('config', config_path)
        if spec is None:
            raise ImportError(f"Could not load spec for {config_path}")
        config = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise ImportError(f"Spec loader is None for {config_path}")
        spec.loader.exec_module(config)
        return getattr(config, 'WEBSCRAPER_CONFIG', {})
    else:
        raise ValueError('Unsupported config file type')

def save_json(data, path):
    """Save data to a JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_text(data, path):
    """Save text data to a file."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(data)
