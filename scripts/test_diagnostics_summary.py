import json
import os
import sys
import urllib.error
import urllib.request


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


def main() -> int:
    server = env("FREEPBX_DIAG_SERVER", "69.39.69.102")
    username = env("FREEPBX_USER", "123net")
    password = env("FREEPBX_PASSWORD", "")
    root_password = env("FREEPBX_ROOT_PASSWORD", "")

    timeout_raw = env("FREEPBX_DIAG_TIMEOUT_SECONDS", "20")
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 20.0

    uri = "http://127.0.0.1:8002/api/diagnostics/summary"

    body = {
        "server": server,
        "username": username,
        "timeout_seconds": timeout_seconds,
    }
    if password:
        body["password"] = password
    if root_password:
        body["root_password"] = root_password

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        uri,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"POST {uri}")
    print(f"server={server} username={username} timeout_seconds={timeout_seconds}")

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds + 5.0) as resp:
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
