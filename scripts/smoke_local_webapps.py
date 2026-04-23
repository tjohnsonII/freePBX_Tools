import json
import sys
import time
import urllib.error
import urllib.request


URLS = [
    ("backend health", "http://127.0.0.1:8002/api/health"),
    ("traceroute backend docs", "http://127.0.0.1:8001/docs"),
    ("polycom dev", "http://127.0.0.1:3002/"),
    ("deploy ui dev", "http://127.0.0.1:3003/"),
]


TRACEROUTE_PORT_CANDIDATES = list(range(3000, 3011))


def fetch(url: str, timeout: float = 3.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(2048).decode("utf-8", errors="replace")
        return resp.status, body


def main() -> int:
    deadline = time.time() + 90.0
    remaining = {name: url for name, url in URLS}

    traceroute_ok = False
    traceroute_url = None

    while (remaining or not traceroute_ok) and time.time() < deadline:
        for name in list(remaining.keys()):
            url = remaining[name]
            try:
                status, body = fetch(url)
                if name == "backend health":
                    try:
                        parsed = json.loads(body)
                        if parsed.get("ok") is not True:
                            raise RuntimeError(f"unexpected health payload: {parsed}")
                    except json.JSONDecodeError:
                        raise RuntimeError("/api/health did not return JSON")
                if status >= 200 and status < 500:
                    print(f"OK  {name}: {url} (HTTP {status})")
                    remaining.pop(name, None)
            except Exception:
                pass

        if not traceroute_ok:
            for port in TRACEROUTE_PORT_CANDIDATES:
                candidate = f"http://127.0.0.1:{port}/"
                try:
                    status, _ = fetch(candidate)
                    if 200 <= status < 500:
                        traceroute_ok = True
                        traceroute_url = candidate
                        print(f"OK  traceroute dev: {candidate} (HTTP {status})")
                        break
                except Exception:
                    continue
        time.sleep(1.0)

    if remaining or not traceroute_ok:
        print("Timed out waiting for:", file=sys.stderr)
        for name, url in remaining.items():
            print(f"- {name}: {url}", file=sys.stderr)
        if not traceroute_ok:
            print(f"- traceroute dev: http://127.0.0.1:3000-3010/", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
