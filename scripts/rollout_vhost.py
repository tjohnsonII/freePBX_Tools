#!/usr/bin/env python3
"""Guided per-app Apache vhost rollout.

Walks through every step for one or more apps in the correct order:

  1. Preview HTTP vhost (dry-run)
  2. Write HTTP vhost + configtest
  3. Enable site + reload Apache
  4. DNS check (manual confirmation)
  5. certbot (skipped if cert already exists)
  6. Preview SSL vhost (dry-run)
  7. Write SSL vhost + configtest
  8. Reload Apache
  9. External curl smoke test

Usage
-----
    # Guided rollout for one pair
    sudo python3 scripts/rollout_vhost.py --apps manager manager-api

    # Skip prompts (CI / re-run after partial failure)
    sudo python3 scripts/rollout_vhost.py --apps manager --yes

    # Only regenerate SSL configs (certs already exist)
    sudo python3 scripts/rollout_vhost.py --apps manager --start-at ssl

Available app keys
------------------
    manager, manager-api, tickets, ticket-api,
    deploy-api, web-manager, homelab, traceroute, polycom
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Re-use the app map and generators from generate_vhosts.py
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_vhosts import (  # noqa: E402
    APPS,
    CERT_BASE,
    SITES_DIR,
    generate_http_phase,
    generate_ssl_phase,
)

STAGES = ["http", "enable", "dns", "certbot", "ssl", "reload", "smoke"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def header(title: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def step(label: str) -> None:
    print(f"\n[step] {label}")


def ok(msg: str) -> None:
    print(f"[ok]   {msg}")


def warn(msg: str) -> None:
    print(f"[warn] {msg}", file=sys.stderr)


def die(msg: str) -> None:
    print(f"[fail] {msg}", file=sys.stderr)
    sys.exit(1)


def confirm(prompt: str, *, auto: bool) -> bool:
    """Return True to continue, False to skip this app."""
    if auto:
        print(f"  {prompt} [auto-yes]")
        return True
    answer = input(f"  {prompt} [y/n/q] ").strip().lower()
    if answer == "q":
        print("Quit.")
        sys.exit(0)
    return answer in ("y", "yes", "")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def cert_exists(hostname: str) -> bool:
    return (CERT_BASE / hostname / "fullchain.pem").exists()


def conf_path(hostname: str, suffix: str = "") -> Path:
    return SITES_DIR / f"{hostname}{suffix}.conf"


# ---------------------------------------------------------------------------
# Individual rollout stages
# ---------------------------------------------------------------------------

def stage_http(apps: dict, *, auto: bool) -> None:
    header("Stage: HTTP proxy vhosts (pre-certbot)")
    print("  Generating HTTP proxy vhosts (dry-run preview):\n")
    generate_http_phase(apps, dry_run=True)

    if not confirm("Write these HTTP vhosts to disk?", auto=auto):
        die("Aborted at HTTP write.")

    generate_http_phase(apps, dry_run=False)

    step("apachectl configtest")
    result = run(["sudo", "apachectl", "configtest"], check=False)
    if result.returncode != 0:
        die("configtest failed after writing HTTP vhosts. Fix before continuing.")
    ok("configtest passed")


def stage_enable(apps: dict, *, auto: bool) -> None:
    header("Stage: Enable sites")
    for hostname, _, _ in apps.values():
        fname = conf_path(hostname).name
        step(f"a2ensite {fname}")
        run(["sudo", "a2ensite", fname])

    step("apachectl -S (verify hostname ownership)")
    run(["sudo", "apachectl", "-S"], check=False)

    if not confirm("Reload Apache now?", auto=auto):
        die("Aborted at enable/reload.")

    run(["sudo", "systemctl", "reload", "apache2"])
    ok("Apache reloaded")


def stage_dns(apps: dict, *, auto: bool) -> None:
    header("Stage: DNS verification")
    print("  Verify these names resolve publicly to this server before certbot runs.")
    print("  Certbot's HTTP-01 challenge will fail if DNS is wrong.\n")

    for hostname, port, _ in apps.values():
        print(f"  {hostname}  →  port {port}")
        step(f"DNS check: host {hostname}")
        result = run(["host", hostname], check=False)
        if result.returncode != 0:
            warn(f"DNS lookup failed for {hostname}. Certbot may fail.")

    if not confirm("DNS looks correct — continue to certbot?", auto=auto):
        die("Aborted at DNS check.")


def stage_certbot(apps: dict, *, auto: bool) -> None:
    header("Stage: certbot SSL issuance")
    for hostname, _, _ in apps.values():
        if cert_exists(hostname):
            ok(f"Cert already exists for {hostname} — skipping certbot")
            continue

        step(f"certbot --apache -d {hostname}")
        if not confirm(f"Issue cert for {hostname}?", auto=auto):
            warn(f"Skipped certbot for {hostname}")
            continue

        result = run(["sudo", "certbot", "--apache", "-d", hostname], check=False)
        if result.returncode != 0:
            die(f"certbot failed for {hostname}. Fix DNS/firewall and retry.")
        ok(f"Cert issued for {hostname}")


def stage_ssl(apps: dict, *, auto: bool) -> None:
    header("Stage: SSL proxy vhosts (final state)")

    missing_certs = [h for h, _, _ in apps.values() if not cert_exists(h)]
    if missing_certs:
        warn("These hostnames have no cert yet — SSL vhosts will be written")
        warn("but Apache will not load them until certs exist:")
        for h in missing_certs:
            warn(f"  {h}")
        if not confirm("Continue anyway?", auto=auto):
            die("Aborted at SSL write — run certbot first.")

    print("  Generating SSL vhosts (dry-run preview):\n")
    generate_ssl_phase(apps, dry_run=True)

    if not confirm("Write these SSL vhosts to disk?", auto=auto):
        die("Aborted at SSL write.")

    generate_ssl_phase(apps, dry_run=False)

    # Enable any -le-ssl.conf files that aren't enabled yet
    for hostname, _, _ in apps.values():
        ssl_fname = conf_path(hostname, "-le-ssl").name
        ssl_path = SITES_DIR / ssl_fname
        if ssl_path.exists():
            enabled = Path("/etc/apache2/sites-enabled") / ssl_fname
            if not enabled.exists():
                step(f"a2ensite {ssl_fname}")
                run(["sudo", "a2ensite", ssl_fname])

    step("apachectl configtest")
    result = run(["sudo", "apachectl", "configtest"], check=False)
    if result.returncode != 0:
        die("configtest failed after writing SSL vhosts.")
    ok("configtest passed")


def stage_reload(auto: bool) -> None:
    header("Stage: Reload Apache")
    if not confirm("Reload Apache to activate SSL vhosts?", auto=auto):
        die("Aborted at final reload.")
    run(["sudo", "systemctl", "reload", "apache2"])
    ok("Apache reloaded")


def stage_smoke(apps: dict) -> None:
    header("Stage: Smoke test (external curl)")
    all_ok = True
    for hostname, _, _ in apps.values():
        for scheme in ("http", "https"):
            url = f"{scheme}://{hostname}/"
            step(f"curl -sIL {url}")
            result = subprocess.run(
                ["curl", "-sIL", "--max-time", "10", url],
                capture_output=False,
                check=False,
            )
            if result.returncode != 0:
                warn(f"curl failed for {url}")
                all_ok = False
            time.sleep(0.5)

    print()
    if all_ok:
        ok("All smoke tests passed")
    else:
        warn("Some smoke tests failed — check Apache logs:")
        for hostname, _, log_prefix in apps.values():
            print(f"  sudo tail -n 30 /var/log/apache2/{log_prefix}-error.log")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STAGE_ORDER = ["http", "enable", "dns", "certbot", "ssl", "reload", "smoke"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apps",
        nargs="+",
        required=True,
        metavar="KEY",
        help=f"App keys to roll out. Available: {', '.join(APPS)}",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Auto-confirm all prompts (non-interactive / re-run mode)",
    )
    parser.add_argument(
        "--start-at",
        choices=STAGE_ORDER,
        default="http",
        metavar="STAGE",
        help=f"Skip earlier stages. Stages: {', '.join(STAGE_ORDER)}",
    )
    parser.add_argument(
        "--stop-after",
        choices=STAGE_ORDER,
        default=None,
        metavar="STAGE",
        help="Stop after this stage (useful for stepwise runs)",
    )
    args = parser.parse_args(argv)

    # Validate app keys
    unknown = [k for k in args.apps if k not in APPS]
    if unknown:
        parser.error(f"Unknown app keys: {unknown}. Valid: {list(APPS.keys())}")

    apps = {k: APPS[k] for k in args.apps}
    auto = args.yes

    start_idx = STAGE_ORDER.index(args.start_at)
    stop_idx = STAGE_ORDER.index(args.stop_after) if args.stop_after else len(STAGE_ORDER) - 1
    active_stages = STAGE_ORDER[start_idx : stop_idx + 1]

    if not SITES_DIR.exists():
        parser.error(f"{SITES_DIR} does not exist — run this on the webserver, not Windows.")

    print(f"\n[rollout] apps={list(apps.keys())}  stages={active_stages}  auto={auto}")
    print(f"          hostnames: {[h for h, _, _ in apps.values()]}")

    for stage in active_stages:
        if stage == "http":
            stage_http(apps, auto=auto)
        elif stage == "enable":
            stage_enable(apps, auto=auto)
        elif stage == "dns":
            stage_dns(apps, auto=auto)
        elif stage == "certbot":
            stage_certbot(apps, auto=auto)
        elif stage == "ssl":
            stage_ssl(apps, auto=auto)
        elif stage == "reload":
            stage_reload(auto=auto)
        elif stage == "smoke":
            stage_smoke(apps)

    header("Rollout complete")
    print(f"  Apps: {list(apps.keys())}")
    print(f"  Add remaining apps one pair at a time with --apps <key1> <key2>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
