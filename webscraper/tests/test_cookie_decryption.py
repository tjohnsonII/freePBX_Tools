from __future__ import annotations

import json
import sys
from pathlib import Path

from webscraper.auth.chrome_cookie_export import export_cookies

REQUIRED_KEYS = {"name", "value", "domain", "path", "secure", "expires"}


def main() -> int:
    print("Running cookie export verification...")
    try:
        output_path = Path(export_cookies())
        print(f"PASS: export_cookies returned path: {output_path}")
    except Exception as exc:
        print(f"FAIL: export_cookies raised an exception: {exc}")
        return 1

    if not output_path.exists():
        print(f"FAIL: exported file does not exist: {output_path}")
        return 1
    print("PASS: exported file exists")

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: unable to parse JSON output: {exc}")
        return 1

    if not isinstance(payload, list):
        print("FAIL: JSON root is not a list")
        return 1
    print("PASS: JSON root is a list")

    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            print(f"FAIL: item {idx} is not an object")
            return 1
        missing = REQUIRED_KEYS - set(item.keys())
        if missing:
            print(f"FAIL: item {idx} missing keys: {sorted(missing)}")
            return 1

    print("PASS: all cookie objects contain required keys")
    print("PASS: cookie decryption/export verification completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
