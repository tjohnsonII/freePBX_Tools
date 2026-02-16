#!/usr/bin/env python3
"""Print a Windows-safe curl.exe command for POST /api/scrape."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a curl.exe command for /api/scrape.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8787", help="API base URL")
    parser.add_argument("--handle", required=True, help="Handle to scrape")
    parser.add_argument("--mode", choices=["latest", "full"], default="latest")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    payload = json.dumps({"handle": args.handle, "mode": args.mode, "limit": args.limit}, separators=(",", ":"))
    escaped_payload = payload.replace('"', '\\"')
    print(
        f'curl.exe --silent --show-error -X POST "{args.api_base}/api/scrape" '
        f'-H "Content-Type: application/json" -d "{escaped_payload}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
