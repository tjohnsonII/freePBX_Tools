#!/usr/bin/env python3
# 123NET FreePBX Tools — version_check.py (Py3.6-safe)

from __future__ import print_function
import argparse, json, os, re, subprocess, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_POLICY = os.environ.get("VERSION_POLICY_JSON", os.path.join(SCRIPT_DIR, "version_policy.json"))

def sh(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return ""

def parse_version_from_freepbx(s):
    # typical: "fwconsole version 16.0.40.13" or "FreePBX 16.0.40.13"
    m = re.search(r'(\d+(?:\.\d+)+)', s or "")
    return m.group(1) if m else ""

def parse_version_from_asterisk(s):
    # typical: "Asterisk 16.28.0 ..." (core show version) or "Asterisk 16.28.0"
    m = re.search(r'Asterisk\s+(\d+(?:\.\d+)+)', s or "", re.I)
    if m:
        return m.group(1)
    m = re.search(r'(\d+(?:\.\d+)+)', s or "")
    return m.group(1) if m else ""

def detect_freepbx_version():
    # Try fwconsole --version, fall back to fwconsole version
    out = sh("/var/lib/asterisk/bin/fwconsole --version")
    if not out:
        out = sh("fwconsole --version")
    if not out:
        out = sh("fwconsole version")
    return parse_version_from_freepbx(out)

def detect_asterisk_version():
    out = sh("asterisk -rx 'core show version'")
    if not out:
        out = sh("asterisk -V")
    return parse_version_from_asterisk(out)

def major_of(v):
    m = re.match(r'^\s*(\d+)', v or "")
    return int(m.group(1)) if m else None

def load_policy(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def check_policy(component, version, policy):
    """Return (ok_bool, majors_list_or_None)."""
    majors = None
    if policy and isinstance(policy, dict):
        entry = policy.get(component) or {}
        majors = entry.get("allowed_majors")
        if majors is not None and not isinstance(majors, list):
            majors = None

    if not version:
        return (False, majors)

    maj = major_of(version)
    if maj is None:
        return (False, majors)

    if majors is None:
        # No explicit policy — treat as OK
        return (True, None)

    return ((maj in majors), majors)

def print_banner(results, policy_path, learned=False):
    print("=" * 66)
    print(" FreePBX / Asterisk Version Policy Check")
    if policy_path:
        print(" Policy file: {}".format(policy_path))
    elif learned:
        print(" Policy: auto-learned from current host (no file present)")
    else:
        print(" Policy: (none)")
    print("-" * 66)
    print("{:<10} {:<16} {}".format("Component", "Version", "Policy Status"))
    for comp, data in results.items():
        ver = data.get("version") or "unknown"
        ok = data.get("ok")
        status = "IN-POLICY" if ok else "OUT-OF-POLICY"
        print("{:<10} {:<16} {}".format(comp, ver, status))
    print("=" * 66)

def main(argv=None):
    p = argparse.ArgumentParser(description="Check FreePBX/Asterisk versions against version_policy.json")
    p.add_argument("--policy", default=DEFAULT_POLICY, help="Path to version_policy.json")
    p.add_argument("--quiet", action="store_true", help="No banner output; exit status only if requested")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument("--exit-nonzero-if-out", action="store_true", help="Exit 2 if any component is OUT-OF-POLICY")
    args = p.parse_args(argv)

    fpbx = detect_freepbx_version()
    ast  = detect_asterisk_version()

    policy = load_policy(args.policy)
    learned = False
    policy_path_for_banner = args.policy if policy else None

    if policy is None:
        # Auto-learn a permissive in-memory policy from current majors (do not write file)
        policy = {}
        fpbx_maj = major_of(fpbx)
        ast_maj  = major_of(ast)
        if fpbx_maj is not None:
            policy["FreePBX"] = {"allowed_majors": [fpbx_maj]}
        if ast_maj is not None:
            policy["Asterisk"] = {"allowed_majors": [ast_maj]}
        learned = True

    ok_fpbx, _ = check_policy("FreePBX", fpbx, policy)
    ok_ast,  _ = check_policy("Asterisk", ast, policy)

    results = {
        "FreePBX": {"version": fpbx, "ok": bool(ok_fpbx)},
        "Asterisk": {"version": ast, "ok": bool(ok_ast)},
    }

    if args.json:
        payload = {
            "policy_file": policy_path_for_banner,
            "auto_learned": learned,
            "results": results,
        }
        print(json.dumps(payload))
    elif not args.quiet:
        print_banner(results, policy_path_for_banner, learned=learned)

    if args.exit_nonzero_if_out and (not ok_fpbx or not ok_ast):
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
