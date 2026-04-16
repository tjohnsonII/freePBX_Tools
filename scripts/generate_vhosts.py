#!/usr/bin/env python3
"""Generate Apache vhost configs for all freePBX-tools web apps.

Workflow
--------
Phase 1 — HTTP proxy (pre-certbot):
    python3 scripts/generate_vhosts.py --phase http
    sudo a2ensite <hostname>.conf   (for each new host)
    sudo apachectl configtest && sudo systemctl reload apache2
    sudo certbot --apache -d <hostname>   (repeat per hostname)

Phase 2 — After certbot has issued all certs:
    python3 scripts/generate_vhosts.py --phase ssl
    sudo apachectl configtest && sudo systemctl reload apache2

Other flags:
    --dry-run       Print configs to stdout; write nothing to disk
    --only foo bar  Generate only the named app keys
    --check         Run apachectl configtest after writing
    --enable        Run a2ensite after writing (requires sudo context)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# App map — single source of truth
# Format: key -> (hostname, backend_port, log_prefix)
# ---------------------------------------------------------------------------
APPS: dict[str, tuple[str, int, str]] = {
    "manager":      ("manager.123hostedtools.com",      3004, "manager"),
    "manager-api":  ("manager-api.123hostedtools.com",  8787, "manager-api"),
    "tickets":      ("tickets.123hostedtools.com",       3005, "tickets"),
    "ticket-api":   ("ticket-api.123hostedtools.com",   8788, "ticket-api"),
    "deploy-api":   ("deploy-api.123hostedtools.com",   8002, "deploy-api"),
    "web-manager":  ("web-manager.123hostedtools.com",  5000, "web-manager"),
    "homelab":      ("homelab.123hostedtools.com",       3011, "homelab"),
    "traceroute":   ("traceroute.123hostedtools.com",   3006, "traceroute"),
    "polycom":      ("polycom.123hostedtools.com",       3002, "polycom"),
}

SITES_DIR = Path("/etc/apache2/sites-available")
CERT_BASE = Path("/etc/letsencrypt/live")


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------

def _http_proxy_vhost(hostname: str, port: int, log_prefix: str) -> str:
    """Phase 1: HTTP vhost that proxies to the backend (needed for certbot)."""
    return textwrap.dedent(f"""\
        <VirtualHost *:80>
            ServerName {hostname}

            ProxyRequests Off
            ProxyPreserveHost On
            ProxyAddHeaders On

            ProxyPass / http://127.0.0.1:{port}/
            ProxyPassReverse / http://127.0.0.1:{port}/

            ErrorLog ${{APACHE_LOG_DIR}}/{log_prefix}-error.log
            CustomLog ${{APACHE_LOG_DIR}}/{log_prefix}-access.log combined
        </VirtualHost>
    """)


def _http_redirect_vhost(hostname: str, log_prefix: str) -> str:
    """Phase 2: HTTP vhost that redirects to HTTPS (final state)."""
    return textwrap.dedent(f"""\
        <VirtualHost *:80>
            ServerName {hostname}
            Redirect permanent / https://{hostname}/

            ErrorLog ${{APACHE_LOG_DIR}}/{log_prefix}-http-error.log
            CustomLog ${{APACHE_LOG_DIR}}/{log_prefix}-http-access.log combined
        </VirtualHost>
    """)


def _ssl_proxy_vhost(hostname: str, port: int, log_prefix: str) -> str:
    """Phase 2: HTTPS vhost that reverse-proxies to the backend."""
    cert_dir = CERT_BASE / hostname
    return textwrap.dedent(f"""\
        <IfModule mod_ssl.c>
        <VirtualHost *:443>
            ServerName {hostname}

            SSLEngine on
            SSLCertificateFile {cert_dir}/fullchain.pem
            SSLCertificateKeyFile {cert_dir}/privkey.pem
            Include /etc/letsencrypt/options-ssl-apache.conf

            ProxyRequests Off
            ProxyPreserveHost On
            ProxyAddHeaders On

            RequestHeader unset Forwarded
            RequestHeader set X-Forwarded-Proto "https"
            RequestHeader set X-Forwarded-Port "443"

            ProxyPass / http://127.0.0.1:{port}/
            ProxyPassReverse / http://127.0.0.1:{port}/

            ErrorLog ${{APACHE_LOG_DIR}}/{log_prefix}-error.log
            CustomLog ${{APACHE_LOG_DIR}}/{log_prefix}-access.log combined
        </VirtualHost>
        </IfModule>
    """)


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def _conf_path(hostname: str, suffix: str = "") -> Path:
    name = f"{hostname}{suffix}.conf"
    return SITES_DIR / name


def write_config(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"\n{'='*60}")
        print(f"# {path}")
        print('='*60)
        print(content)
        return
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path}")


def generate_http_phase(apps: dict[str, tuple[str, int, str]], *, dry_run: bool) -> list[Path]:
    """Write HTTP proxy vhosts (for use before certbot runs)."""
    paths: list[Path] = []
    for key, (hostname, port, log_prefix) in apps.items():
        content = _http_proxy_vhost(hostname, port, log_prefix)
        path = _conf_path(hostname)
        write_config(path, content, dry_run=dry_run)
        paths.append(path)
    return paths


def generate_ssl_phase(apps: dict[str, tuple[str, int, str]], *, dry_run: bool) -> list[Path]:
    """Write HTTP-redirect + HTTPS proxy vhosts (after certbot has run)."""
    paths: list[Path] = []
    for key, (hostname, port, log_prefix) in apps.items():
        # Overwrite HTTP vhost with redirect-only
        http_content = _http_redirect_vhost(hostname, log_prefix)
        http_path = _conf_path(hostname)
        write_config(http_path, http_content, dry_run=dry_run)
        paths.append(http_path)

        # Write HTTPS proxy vhost (matches certbot's -le-ssl.conf naming)
        ssl_content = _ssl_proxy_vhost(hostname, port, log_prefix)
        ssl_path = _conf_path(hostname, "-le-ssl")
        write_config(ssl_path, ssl_content, dry_run=dry_run)
        paths.append(ssl_path)
    return paths


# ---------------------------------------------------------------------------
# Apache helpers
# ---------------------------------------------------------------------------

def enable_sites(paths: list[Path]) -> None:
    for path in paths:
        name = path.name
        print(f"  a2ensite {name}")
        subprocess.run(["sudo", "a2ensite", name], check=True)


def configtest() -> bool:
    result = subprocess.run(["sudo", "apachectl", "configtest"])
    return result.returncode == 0


def print_certbot_commands(apps: dict[str, tuple[str, int, str]]) -> None:
    print("\nRun certbot for each hostname (one at a time):")
    for hostname, _, _ in apps.values():
        print(f"  sudo certbot --apache -d {hostname}")
    print("\nThen re-run this script with --phase ssl to finalize configs.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        choices=["http", "ssl"],
        required=True,
        help="http = pre-certbot HTTP proxy vhosts; ssl = post-certbot redirect+HTTPS vhosts",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="KEY",
        help=f"Generate only these app keys. Available: {', '.join(APPS)}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated configs to stdout; do not write any files",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Run a2ensite for each generated conf (requires sudo)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run apachectl configtest after writing files",
    )
    args = parser.parse_args(argv)

    # Filter app map
    if args.only:
        unknown = [k for k in args.only if k not in APPS]
        if unknown:
            print(f"[error] Unknown app keys: {unknown}", file=sys.stderr)
            print(f"        Valid keys: {list(APPS.keys())}", file=sys.stderr)
            return 1
        apps = {k: APPS[k] for k in args.only}
    else:
        apps = APPS

    if not args.dry_run and not SITES_DIR.exists():
        print(f"[error] {SITES_DIR} does not exist. Are you on the webserver?", file=sys.stderr)
        return 1

    print(f"[generate_vhosts] phase={args.phase} apps={list(apps)} dry_run={args.dry_run}")

    if args.phase == "http":
        paths = generate_http_phase(apps, dry_run=args.dry_run)
        if not args.dry_run:
            print("\nNext steps:")
            print("  1. Enable the sites:")
            for p in paths:
                print(f"       sudo a2ensite {p.name}")
            print("  2. sudo a2enmod proxy proxy_http headers rewrite ssl")
            print("  3. sudo apachectl configtest && sudo systemctl reload apache2")
            print_certbot_commands(apps)

    elif args.phase == "ssl":
        # Warn about missing certs
        missing = []
        for hostname, _, _ in apps.values():
            cert = CERT_BASE / hostname / "fullchain.pem"
            if not cert.exists():
                missing.append(hostname)
        if missing and not args.dry_run:
            print("[warn] The following hostnames do not have certs yet:")
            for h in missing:
                print(f"       {h}")
            print("       Run certbot first, or use --dry-run to preview configs.")
            if len(missing) == len(apps):
                return 1

        paths = generate_ssl_phase(apps, dry_run=args.dry_run)

    if args.enable and not args.dry_run:
        enable_sites(paths)

    if args.check and not args.dry_run:
        ok = configtest()
        if not ok:
            print("[error] apachectl configtest failed", file=sys.stderr)
            return 1
        print("[ok] apachectl configtest passed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
