import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    uri = "http://127.0.0.1:8002/api/health"
    print(f"GET {uri}")
    req = urllib.request.Request(uri, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
                print(json.dumps(parsed, indent=2, sort_keys=True))
            except json.JSONDecodeError:
                print(raw)
        return 0
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"Request failed: HTTP {e.code} {e.reason}", file=sys.stderr)
        if details:
            print(details, file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
