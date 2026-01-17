import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


def main() -> int:
    parser = argparse.ArgumentParser(description="Call /api/diagnostics/summary with optional credential prompting")
    parser.add_argument("--server", default=env("FREEPBX_DIAG_SERVER", "69.39.69.102"))
    parser.add_argument("--username", default=env("FREEPBX_USER", "123net"))
    parser.add_argument("--timeout-seconds", type=float, default=float(env("FREEPBX_DIAG_TIMEOUT_SECONDS", "20") or 20))
    parser.add_argument("--no-prompt", action="store_true", help="Do not prompt; rely only on env vars/args")
    args = parser.parse_args()

    password = env("FREEPBX_PASSWORD", "")
    root_password = env("FREEPBX_ROOT_PASSWORD", "")

    if not args.no_prompt:
        if not password:
            password = getpass.getpass("FREEPBX_PASSWORD (SSH user password, blank to skip): ")
        if not root_password:
            root_password = getpass.getpass("FREEPBX_ROOT_PASSWORD (for su root, blank to skip): ")

    uri = "http://127.0.0.1:8002/api/diagnostics/summary"

    body = {
        "server": args.server,
        "username": args.username,
        "timeout_seconds": args.timeout_seconds,
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
    print(f"server={args.server} username={args.username} timeout_seconds={args.timeout_seconds}")

    try:
        with urllib.request.urlopen(req, timeout=args.timeout_seconds + 10.0) as resp:
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
