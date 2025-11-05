#!/usr/bin/env python3
# 123NET FreePBX Tools - Version Policy Checker (Python 3.6 safe)

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Optional, Dict, Any, List, Tuple

# ANSI Color codes for professional output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header():
    """Print professional header banner"""
    print(Colors.GREEN + Colors.BOLD + """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║           ✅  FreePBX Version Policy Compliance Check         ║
║                                                               ║
║              Verify System Version Requirements               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """ + Colors.ENDC)

DEFAULT_POLICY = "/usr/local/123net/freepbx-tools/version_policy.json"

def sh(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return out.decode("utf-8", "ignore").strip()
    except Exception:
        return ""

def detect_freepbx_version() -> Optional[str]:
    # Typical: fwconsole --version -> "... 16.0.40.13"
    out = sh(["fwconsole", "--version"])
    if out:
        toks = out.split()
        if toks:
            return toks[-1]
    return None

def detect_asterisk_version() -> Optional[str]:
    # Prefer detailed runtime banner
    out = sh(["asterisk", "-rx", "core show version"])
    m = re.search(r"Asterisk\s+([0-9]+(?:\.[0-9]+)*)", out or "")
    if m:
        return m.group(1)
    # Fallback
    out = sh(["asterisk", "-V"])
    m = re.search(r"Asterisk\s+([0-9]+(?:\.[0-9]+)*)", out or "")
    return m.group(1) if m else None

def major_of(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    m = re.match(r"([0-9]+)", s)
    return int(m.group(1)) if m else None

def load_policy(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)

def save_policy(path: str, policy: Dict[str, Any]) -> None:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        json.dump(policy, f, indent=2, sort_keys=True)

def normalize_allowed_majors(v: Any) -> List[int]:
    out = []
    if isinstance(v, list):
        for item in v:
            try:
                out.append(int(item))
            except Exception:
                pass
    return out

def normalize_allowed_ranges(v: Any) -> List[Tuple[int, int]]:
    ranges = []
    if isinstance(v, list):
        for pair in v:
            if (isinstance(pair, list) or isinstance(pair, tuple)) and len(pair) == 2:
                try:
                    lo = int(pair[0]); hi = int(pair[1])
                    if lo <= hi:
                        ranges.append((lo, hi))
                except Exception:
                    pass
    return ranges

def major_allowed(major: Optional[int], comp_policy: Dict[str, Any]) -> bool:
    if major is None:
        return False
    # Support either:
    #  - "allowed_majors": [16, 18]
    #  - "allowed_ranges": [[16,18], [20,20]]
    majors = normalize_allowed_majors(comp_policy.get("allowed_majors"))
    if majors and major in majors:
        return True
    ranges = normalize_allowed_ranges(comp_policy.get("allowed_ranges"))
    for lo, hi in ranges:
        if lo <= major <= hi:
            return True
    # Also support simple "min_major"/"max_major" if present
    try:
        min_val = comp_policy.get("min_major")
        mn = int(min_val) if min_val is not None else None
        max_val = comp_policy.get("max_major")
        mx = int(max_val) if max_val is not None else None
        if mn is not None and mx is not None and mn <= major <= mx:
            return True
        if mn is not None and mx is None and major >= mn:
            return True
        if mx is not None and mn is None and major <= mx:
            return True
    except Exception:
        pass
    return False

def banner_line():
    print("=" * 66)

def run(policy_path: str, quiet: bool, autolearn: bool) -> int:
    # Detect versions
    fpbx_ver = detect_freepbx_version()
    ast_ver  = detect_asterisk_version()
    fpbx_maj = major_of(fpbx_ver)
    ast_maj  = major_of(ast_ver)

    # Load or autolearn policy
    policy = {}  # type: Dict[str, Any]
    if os.path.isfile(policy_path):
        try:
            policy = load_policy(policy_path)
        except Exception:
            policy = {}
    elif autolearn:
        policy = {
            "FreePBX":  {"allowed_majors": [fpbx_maj] if fpbx_maj is not None else [16]},
            "Asterisk": {"allowed_majors": [ast_maj]  if ast_maj  is not None else [16, 18]},
        }
        try:
            save_policy(policy_path, policy)
        except Exception:
            # Non-fatal: continue without writing
            pass

    fpbx_policy = policy.get("FreePBX", {})
    ast_policy  = policy.get("Asterisk", {})

    fpbx_ok = major_allowed(fpbx_maj, fpbx_policy)
    ast_ok  = major_allowed(ast_maj,  ast_policy)

    if not quiet:
        print_header()
        print(Colors.CYAN + "Policy file: " + Colors.BOLD + policy_path + Colors.ENDC)
        print(Colors.CYAN + "─" * 70 + Colors.ENDC)
        print("")
        print(Colors.BOLD + "{:<12} {:<18} {}".format("Component", "Version", "Status") + Colors.ENDC)
        print(Colors.CYAN + "─" * 70 + Colors.ENDC)
        
        # FreePBX status
        fpbx_status_icon = "✓" if fpbx_ok else "✗"
        fpbx_status_color = Colors.GREEN if fpbx_ok else Colors.RED
        fpbx_status_text = "IN-POLICY" if fpbx_ok else "OUT-OF-POLICY"
        print("{:<12} {:<18} {}{}{}".format(
            Colors.BOLD + "FreePBX" + Colors.ENDC,
            Colors.CYAN + (fpbx_ver or "NOT DETECTED") + Colors.ENDC,
            fpbx_status_color + fpbx_status_icon + " " + fpbx_status_text + Colors.ENDC
        ))
        
        # Asterisk status
        ast_status_icon = "✓" if ast_ok else "✗"
        ast_status_color = Colors.GREEN if ast_ok else Colors.RED
        ast_status_text = "IN-POLICY" if ast_ok else "OUT-OF-POLICY"
        print("{:<12} {:<18} {}{}{}".format(
            Colors.BOLD + "Asterisk" + Colors.ENDC,
            Colors.CYAN + (ast_ver or "NOT DETECTED") + Colors.ENDC,
            ast_status_color + ast_status_icon + " " + ast_status_text + Colors.ENDC
        ))
        
        print(Colors.CYAN + "─" * 70 + Colors.ENDC)
        
        # Overall status
        if fpbx_ver and ast_ver and fpbx_ok and ast_ok:
            print(Colors.GREEN + Colors.BOLD + "\n✓ All versions are compliant with policy" + Colors.ENDC)
        else:
            print(Colors.YELLOW + Colors.BOLD + "\n⚠ Version policy violations detected" + Colors.ENDC)
        print("")

    # Exit code: 0 if both known and in policy; 1 otherwise (non-fatal for installer)
    if (fpbx_ver and ast_ver and fpbx_ok and ast_ok):
        return 0
    return 1

def main():
    ap = argparse.ArgumentParser(description="Check FreePBX/Asterisk versions against version_policy.json")
    ap.add_argument("--policy", default=os.environ.get("VERSION_POLICY_JSON", DEFAULT_POLICY),
                    help="Path to version_policy.json (default: %(default)s)")
    ap.add_argument("--quiet", action="store_true", help="Suppress human-readable banner")
    ap.add_argument("--no-autolearn", action="store_true",
                    help="Do not write a minimal policy file if missing")
    args = ap.parse_args()

    rc = run(args.policy, args.quiet, autolearn=(not args.no_autolearn))
    sys.exit(rc)

if __name__ == "__main__":
    main()
