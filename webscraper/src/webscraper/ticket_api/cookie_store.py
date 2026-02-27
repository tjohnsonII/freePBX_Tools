from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from webscraper.paths import var_dir
from webscraper.ticket_api.auth import CookieNormalized

COOKIE_STORE_PATH = var_dir() / "auth" / "imported_cookies.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        temp_name = tmp.name
    Path(temp_name).replace(path)


def save_imported_cookies(cookies: list[CookieNormalized], metadata: dict[str, Any]) -> None:
    _atomic_write_json(
        COOKIE_STORE_PATH,
        {
            "metadata": metadata,
            "cookies": [cookie.model_dump(exclude_none=True) for cookie in cookies],
        },
    )


def load_imported_cookies() -> list[CookieNormalized]:
    if not COOKIE_STORE_PATH.exists():
        return []
    try:
        payload = json.loads(COOKIE_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("cookies") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    parsed: list[CookieNormalized] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            parsed.append(CookieNormalized(**row))
        except Exception:
            continue
    return parsed


def load_cookie_metadata() -> dict[str, Any]:
    if not COOKIE_STORE_PATH.exists():
        return {}
    try:
        payload = json.loads(COOKIE_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}


def clear_imported_cookies() -> None:
    if COOKIE_STORE_PATH.exists():
        COOKIE_STORE_PATH.unlink()
