#!/usr/bin/env python3
"""
Batch Ticket Scraper
--------------------
Iterates over a list of customer handles and runs ticket_scraper.py for each,
writing per-customer SQLite databases to the output directory. Optionally builds
the unified knowledge base at the end.

Credential resolution order:
1) CLI args --username/--password
2) Env vars KB_USERNAME / KB_PASSWORD
3) webscraper.ultimate_scraper_config WEBSCRAPER_CONFIG['environments']['default']['credentials']

Notes:
- Uses subprocess.run and universal_newlines=True for Python 3.6 compatibility.
- Skips handles with existing *_tickets.db when --resume is provided.
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path


def load_handles(path: str):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Handles file not found: {path}")
    handles = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        handles.append(s)
    return handles


def resolve_credentials(args_username: str, args_password: str):
    if args_username and args_password:
        return args_username, args_password
    u = os.environ.get("KB_USERNAME")
    p = os.environ.get("KB_PASSWORD")
    if u and p:
        return u, p
    # Fallback to config if available
    try:
        import importlib
        cfg = importlib.import_module("webscraper.ultimate_scraper_config")
        creds = (
            getattr(cfg, "WEBSCRAPER_CONFIG", {})
            .get("environments", {})
            .get("default", {})
            .get("credentials", {})
        )
        u2 = creds.get("username")
        p2 = creds.get("password")
        if u2 and p2:
            return u2, p2
    except Exception:
        pass
    raise RuntimeError("Credentials not provided. Set --username/--password or KB_USERNAME/KB_PASSWORD env vars.")


def main():
    ap = argparse.ArgumentParser(description="Run ticket_scraper.py for a list of handles")
    ap.add_argument(
        "--handles-file",
        default=str(Path("webscraper") / "data" / "customer_handles.txt"),
        help="Path to file with handles (one per line)",
    )
    ap.add_argument("--output-dir", default="knowledge_base", help="Directory to write per-customer *_tickets.db")
    ap.add_argument("--username", help="Portal username (fallback: KB_USERNAME env)")
    ap.add_argument("--password", help="Portal password (fallback: KB_PASSWORD env)")
    ap.add_argument("--limit", type=int, help="Process only the first N handles")
    ap.add_argument("--resume", action="store_true", help="Skip handles with existing *_tickets.db")
    ap.add_argument("--build", action="store_true", help="Build unified KB after scraping")
    ap.add_argument("--cookie-file", default=str(Path("webscraper")/"output"/"kb-run"/"selenium_cookies.json"), help="Selenium cookies JSON for authenticated scraping")
    args = ap.parse_args()

    repo_root = Path(__file__).parent
    os.makedirs(args.output_dir, exist_ok=True)

    handles = load_handles(args.handles_file)
    if args.limit:
        handles = handles[: args.limit]
    print(f"[INFO] Loaded {len(handles)} handles from {args.handles_file}")

    username, password = resolve_credentials(args.username, args.password)
    print(f"[INFO] Using credentials from {'CLI' if args.username else ('env' if os.environ.get('KB_USERNAME') else 'config')} (values not echoed)")

    processed = 0
    skipped = 0
    failures = 0
    for h in handles:
        db_path = Path(args.output_dir) / f"{h}_tickets.db"
        if args.resume and db_path.exists():
            skipped += 1
            print(f"[SKIP] {h}: {db_path.name} already exists")
            continue
        cmd = [
            sys.executable,
            "ticket_scraper.py",
            "--customer", h,
            "--username", username,
            "--password", password,
            "--cookie-file", args.cookie_file,
            "--output", args.output_dir,
        ]
        print(f"[RUN] {h} -> {db_path}")
        try:
            res = subprocess.run(cmd, cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            if res.returncode == 0 and db_path.exists():
                processed += 1
                print(f"[OK] {h}: {db_path} (")
            else:
                failures += 1
                print(f"[FAIL] {h}: returncode={res.returncode}\n{res.stdout}")
        except Exception as e:
            failures += 1
            print(f"[ERROR] {h}: {e}")

    print(f"[SUMMARY] processed={processed} skipped={skipped} failures={failures}")

    if args.build:
        print("[BUILD] Creating unified knowledge base...")
        build_cmd = [
            sys.executable,
            "build_unified_kb.py",
            "--input-dir", args.output_dir,
            "--output-db", "unified_knowledge_base.db",
            "--stats",
        ]
        res = subprocess.run(build_cmd, cwd=str(repo_root), universal_newlines=True)
        sys.exit(res.returncode)

    return 0


if __name__ == "__main__":
    sys.exit(main())
