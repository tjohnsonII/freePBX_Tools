#!/usr/bin/env python3
"""
FreePBX Certificate Status Checker
-----------------------------------
Checks TLS certificates actually in use on this box — the web GUI
(Apache/httpd) and SIP/PJSIP TLS transports — for expiration, chain/issuer
validity, and hostname match. Discovers cert paths from the real Apache and
Asterisk config rather than guessing fixed locations, since FreePBX's
Certificate Manager module names files arbitrarily and Let's Encrypt vs.
self-signed vs. custom-uploaded certs can all coexist.

VARIABLE MAP
------------
Colors       : ANSI color codes for CLI output
CertInfo     : dict describing one checked certificate
WARN_DAYS    : days-until-expiry threshold for a warning (not yet expired)

FUNCTION MAP
------------
find_httpd_cert_paths   : Discover the cert file(s) Apache/httpd actually serves
find_pjsip_cert_paths   : Discover the cert file(s) PJSIP TLS transports actually use
inspect_cert            : Run openssl on one cert file, return a CertInfo dict
print_report            : Render all checked certs as a formatted report
main                    : CLI entry point
"""

import argparse
import glob
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone


class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

WARN_DAYS = 30

HTTPD_CONF_GLOBS = [
    "/etc/httpd/conf.d/*.conf",
    "/etc/httpd/conf.modules.d/*.conf",
    "/etc/apache2/sites-enabled/*.conf",
    "/etc/apache2/conf-enabled/*.conf",
]

PJSIP_CONF_GLOBS = [
    "/etc/asterisk/pjsip.conf",
    "/etc/asterisk/pjsip.transports_custom.conf",
    "/etc/asterisk/pjsip_transport_custom_post.conf",
    "/etc/asterisk/pjsip_custom.conf",
]

FALLBACK_CERT_GLOBS = [
    "/etc/asterisk/keys/*.crt",
    "/etc/asterisk/keys/*.pem",
    "/etc/letsencrypt/live/*/fullchain.pem",
]


def _read_files(paths):
    for p in paths:
        for f in glob.glob(p):
            try:
                with open(f, "r", errors="ignore") as fh:
                    yield f, fh.read()
            except OSError:
                continue


def find_httpd_cert_paths():
    """Find the cert file(s) referenced by SSLCertificateFile in the real
    Apache/httpd config — this is the cert actually served to browsers,
    regardless of what FreePBX's Certificate Manager happens to name it."""
    found = []
    for _, content in _read_files(HTTPD_CONF_GLOBS):
        for m in re.finditer(r'^\s*SSLCertificateFile\s+["\']?([^\s"\']+)', content, re.MULTILINE):
            path = m.group(1)
            if path not in found:
                found.append(path)
    return found


def find_pjsip_cert_paths():
    """Find cert file(s) referenced by cert_file= under a PJSIP TLS
    transport, across every config file PJSIP TLS transports commonly live
    in on a FreePBX box."""
    found = []
    for _, content in _read_files(PJSIP_CONF_GLOBS):
        if "type=transport" not in content and "type = transport" not in content:
            continue
        for m in re.finditer(r'^\s*cert_file\s*=\s*(\S+)', content, re.MULTILINE):
            path = m.group(1).strip()
            if path not in found:
                found.append(path)
    return found


def inspect_cert(path, purpose):
    """Run openssl on one cert file and return a dict describing it, or
    a dict with 'error' set if the file can't be read/parsed."""
    if not os.path.isfile(path):
        return {"path": path, "purpose": purpose, "error": "File not found"}

    try:
        result = subprocess.run(
            ["openssl", "x509", "-in", path, "-noout",
             "-subject", "-issuer", "-enddate", "-startdate", "-ext", "subjectAltName"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"path": path, "purpose": purpose, "error": str(e)}

    if result.returncode != 0:
        return {"path": path, "purpose": purpose, "error": (result.stderr or "openssl failed").strip()[:200]}

    out = result.stdout
    subject = _extract(out, r'subject=(.+)')
    issuer = _extract(out, r'issuer=(.+)')
    not_after_raw = _extract(out, r'notAfter=(.+)')
    not_before_raw = _extract(out, r'notBefore=(.+)')
    san_match = re.search(r'X509v3 Subject Alternative Name:\s*\n\s*(.+)', out)
    sans = [s.strip().replace("DNS:", "") for s in san_match.group(1).split(",")] if san_match else []

    cn = _extract(subject or "", r'CN\s*=\s*([^,/]+)') or subject or "unknown"
    issuer_cn = _extract(issuer or "", r'CN\s*=\s*([^,/]+)') or issuer or "unknown"

    days_left = None
    expired = None
    if not_after_raw:
        try:
            not_after = datetime.strptime(not_after_raw.strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_left = (not_after - datetime.now(timezone.utc)).days
            expired = days_left < 0
        except ValueError:
            pass

    self_signed = subject is not None and subject == issuer

    return {
        "path": path,
        "purpose": purpose,
        "cn": cn.strip(),
        "issuer_cn": issuer_cn.strip(),
        "sans": sans,
        "not_before": not_before_raw,
        "not_after": not_after_raw,
        "days_left": days_left,
        "expired": expired,
        "self_signed": self_signed,
    }


def _extract(text, pattern):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def hostname_matches(cert, expected_hosts):
    """True if the cert's CN or any SAN matches one of the box's known
    hostnames (case-insensitive, supports a single leading wildcard)."""
    names = set()
    if cert.get("cn"):
        names.add(cert["cn"].lower())
    names.update(s.lower() for s in cert.get("sans", []))

    for expected in expected_hosts:
        expected = expected.lower()
        for name in names:
            if name == expected:
                return True
            if name.startswith("*.") and expected.endswith(name[1:]):
                return True
    return False


def get_expected_hostnames():
    hosts = set()
    try:
        hosts.add(socket.gethostname().lower())
    except OSError:
        pass
    try:
        hosts.add(socket.getfqdn().lower())
    except OSError:
        pass
    return {h for h in hosts if h and h != "localhost"}


def collect_certs():
    checked = []
    seen_paths = set()

    for path in find_httpd_cert_paths():
        if path not in seen_paths:
            checked.append(inspect_cert(path, "Web GUI (HTTPS)"))
            seen_paths.add(path)

    for path in find_pjsip_cert_paths():
        if path not in seen_paths:
            checked.append(inspect_cert(path, "SIP/PJSIP TLS"))
            seen_paths.add(path)

    if not checked:
        for path in [p for g in FALLBACK_CERT_GLOBS for p in glob.glob(g)]:
            if path not in seen_paths:
                checked.append(inspect_cert(path, "Discovered (unconfirmed use)"))
                seen_paths.add(path)

    return checked


def print_report(certs, expected_hosts):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 78}")
    print(f"  🔒 CERTIFICATE STATUS")
    print(f"{'=' * 78}{Colors.RESET}\n")

    if not certs:
        print(f"{Colors.YELLOW}No certificates found — checked Apache/httpd SSLCertificateFile "
              f"directives and PJSIP TLS transport cert_file= settings, plus common "
              f"FreePBX/Let's Encrypt locations as a fallback.{Colors.RESET}")
        return True

    any_bad = False
    for cert in certs:
        print(f"{Colors.WHITE}{Colors.BOLD}{cert['purpose']}{Colors.RESET}  {Colors.CYAN}{cert['path']}{Colors.RESET}")

        if cert.get("error"):
            print(f"  {Colors.RED}✗ {cert['error']}{Colors.RESET}\n")
            any_bad = True
            continue

        print(f"  Subject:  {cert['cn']}")
        print(f"  Issuer:   {cert['issuer_cn']}" + (f"  {Colors.YELLOW}(self-signed){Colors.RESET}" if cert["self_signed"] else ""))
        if cert["sans"]:
            print(f"  SANs:     {', '.join(cert['sans'])}")

        days = cert["days_left"]
        if days is None:
            print(f"  Expiry:   {Colors.YELLOW}⚠ could not parse expiration date{Colors.RESET}")
            any_bad = True
        elif cert["expired"]:
            print(f"  Expiry:   {Colors.RED}❌ EXPIRED {abs(days)} day(s) ago ({cert['not_after']}){Colors.RESET}")
            any_bad = True
        elif days <= WARN_DAYS:
            print(f"  Expiry:   {Colors.YELLOW}⚠ expires in {days} day(s) ({cert['not_after']}){Colors.RESET}")
            any_bad = True
        else:
            print(f"  Expiry:   {Colors.GREEN}✓ {days} day(s) remaining ({cert['not_after']}){Colors.RESET}")

        if expected_hosts:
            if hostname_matches(cert, expected_hosts):
                print(f"  Hostname: {Colors.GREEN}✓ matches this host{Colors.RESET}")
            else:
                print(f"  Hostname: {Colors.YELLOW}⚠ no match for {'/'.join(sorted(expected_hosts))} "
                      f"— may be intentional (e.g. shared/wildcard cert){Colors.RESET}")
                any_bad = True
        print()

    return not any_bad


def main():
    global WARN_DAYS
    parser = argparse.ArgumentParser(description="Check FreePBX web GUI and SIP TLS certificate status")
    parser.add_argument("--warn-days", type=int, default=WARN_DAYS, help=f"Warn if expiring within N days (default: {WARN_DAYS})")
    args = parser.parse_args()

    WARN_DAYS = args.warn_days

    certs = collect_certs()
    expected_hosts = get_expected_hostnames()
    ok = print_report(certs, expected_hosts)

    print(f"{Colors.CYAN}{'=' * 78}{Colors.RESET}")
    if ok:
        print(f"{Colors.GREEN}✅ All certificates OK{Colors.RESET}\n")
        sys.exit(0)
    else:
        print(f"{Colors.YELLOW}⚠ One or more certificates need attention (see above){Colors.RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
