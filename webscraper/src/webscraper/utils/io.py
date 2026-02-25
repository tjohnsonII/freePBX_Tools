from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def make_run_id(
    *,
    handle: str | None,
    mode: str,
    browser: str,
    base_url: str,
    started_utc: str,
    extra: dict | None = None,
) -> str:
    started_dt = datetime.strptime(started_utc, "%Y-%m-%dT%H:%M:%SZ")
    stamp = started_dt.strftime("%Y%m%d_%H%M%S")
    payload = {
        "base_url": base_url,
        "browser": (browser or "").lower(),
        "extra": extra or {},
        "handle": handle if handle is not None else "ALL",
        "mode": mode,
        "started_utc": started_utc,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:12]
    return f"{stamp}_{digest}"


def safe_write_json(path: str | Path, data: Any) -> None:
    final_path = Path(path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = f"{final_path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    tmp_path = final_path.parent / tmp_name
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise
