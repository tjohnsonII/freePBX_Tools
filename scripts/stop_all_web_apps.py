from __future__ import annotations

from pathlib import Path

from lib.dev_runtime import repo_root, stop_all_known_services


def main() -> int:
    root = repo_root(Path(__file__))
    stop_all_known_services(root, fallback_ports=[8787, 3004])
    print("[success] stop routine completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
