#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_paging_fax_analyzer.py
------------------------------
Specialized analyzer for paging systems, overhead speakers, and fax configurations in FreePBX.
Provides detailed analysis of these specific communication features.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).

VARIABLE MAP (Key Script Variables)
-----------------------------------
Colors         : ANSI color codes for CLI output
ASTERISK_DB    : Name of the Asterisk database
DEFAULT_SOCK   : Default MySQL socket path
args           : Parsed command-line arguments
db_socket      : MySQL socket path (if used)
db_user        : MySQL username
db_password    : MySQL password (if used)
output_file    : Path to output report file
paging_data    : Parsed data for paging/overhead systems
fax_data       : Parsed data for fax configurations
summary_stats  : Dictionary of computed summary statistics

Key Function Arguments:
-----------------------
sql            : SQL query string
component      : Paging or fax component name
row            : Row of data from DB
args           : Parsed command-line arguments

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    print_header              : Print professional header banner
    run_mysql_query           : Run a MySQL query using the CLI
    analyze_paging_systems    : Analyze paging/overhead speaker systems
    analyze_fax_config        : Analyze fax configuration and usage
    print_summary             : Print summary statistics to terminal
    write_report              : Write analysis report to file
    main                     : CLI entry point, parses args and runs analysis
"""

import argparse, json, os, subprocess, sys, time, re
from collections import defaultdict

# ANSI Color codes
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def print_header():
    """Print professional header banner"""
    print(Colors.MAGENTA + Colors.BOLD + """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║        📢  FreePBX Paging, Overhead & Fax Analyzer            ║
║                                                               ║
║          Specialized Communication Systems Analysis           ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """ + Colors.ENDC)

ASTERISK_DB = "asterisk"
DEFAULT_SOCK = "/var/lib/mysql/mysql.sock"

# ---------------------------
# mysql helpers (3.6 friendly)
# ---------------------------

def run_mysql(sql, socket=None, user="root", password=None, db=ASTERISK_DB):
    """Run a SQL statement via mysql CLI and return stdout as text."""
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = ["mysql", "-BN"]
    if user:
        cmd += ["--user", str(user)]
    if socket:
        cmd += ["--socket", str(socket)]
    if db:
        cmd += [str(db)]
    cmd += ["-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        return ""
    return p.stdout

def run_command(cmd):
    """Run a shell command and return stdout."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, shell=True)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), 1

def rows_as_dicts(sql, cols, **kw):
    """Run a SELECT that returns exactly len(cols) columns -> list[dict]."""
    out = run_mysql(sql, **kw).rstrip("\n")
    if not out:
        return []
    dicts = []
    for line in out.split("\n"):
        parts = line.split("\t")
        parts = (parts + [""] * len(cols))[:len(cols)]
        dicts.append(dict(zip(cols, parts)))
    return dicts

def get_tables(**kw):
    return set(run_mysql("SHOW TABLES;", **kw).split())

def has_table(t, **kw): 
    return t in get_tables(**kw)

def get_columns(table, **kw):
    lines = run_mysql(f"DESCRIBE `{table}`;", **kw).splitlines()
    return set([ln.split("\t",1)[0] for ln in lines if ln.strip()])

def did_col(tbl, **kw):
    """Return the DID column name — 'did' (newer FreePBX) or 'extension' (older)."""
    return "did" if "did" in get_columns(tbl, **kw) else "extension"

# ---------------------------
# Paging Analysis Functions
# ---------------------------

def analyze_paging_pro(**kw):
    """Analyze Paging Pro module configuration."""
    config = {"enabled": False, "groups": [], "settings": {}}
    
    # Check if Paging Pro tables exist
    paging_tables = ["paging_config", "paging_groups", "pagingpro"]
    available_tables = [t for t in paging_tables if has_table(t, **kw)]
    
    if not available_tables:
        return config
    
    config["enabled"] = True
    config["available_tables"] = available_tables
    
    # Analyze paging groups
    if has_table("paging_config", **kw):
        groups = rows_as_dicts("""
            SELECT extension, description, 
                   COALESCE(enabled, '1') as enabled,
                   COALESCE(announcement, '') as announcement,
                   COALESCE(force_page, '0') as force_page,
                   COALESCE(duplex, '0') as duplex
            FROM paging_config 
            ORDER BY extension;
        """, ["extension", "description", "enabled", "announcement", "force_page", "duplex"], **kw)
        
        config["groups"] = groups
        config["total_groups"] = len(groups)
        config["enabled_groups"] = len([g for g in groups if g["enabled"] == "1"])
        config["duplex_groups"] = len([g for g in groups if g["duplex"] == "1"])
    
    # Analyze paging group members/devices
    if has_table("paging_groups", **kw):
        members = rows_as_dicts("""
            SELECT grp, device FROM paging_groups ORDER BY grp, device;
        """, ["grp", "device"], **kw)
        
        # Group members by paging group
        members_by_group = defaultdict(list)
        for member in members:
            members_by_group[member["grp"]].append(member["device"])
        
        config["members_by_group"] = dict(members_by_group)
        config["total_member_assignments"] = len(members)
    
    # Check for advanced paging settings
    if has_table("pagingpro", **kw):
        pro_settings = rows_as_dicts("""
            SELECT keyword, value FROM pagingpro;
        """, ["keyword", "value"], **kw)
        config["pro_settings"] = {s["keyword"]: s["value"] for s in pro_settings}
    
    return config

def analyze_overhead_paging(**kw):
    """Analyze overhead paging/intercom configurations."""
    config = {"speakers": [], "zones": [], "settings": {}}
    
    # Check for overhead paging in various possible configurations
    
    # Look for SIP devices that might be overhead speakers
    if has_table("sip", **kw):
        # Common overhead speaker patterns
        overhead_patterns = ["overhead", "speaker", "page", "intercom", "zone"]
        
        speakers = rows_as_dicts("""
            SELECT name, host, context, 
                   COALESCE(description, '') as description,
                   COALESCE(accountcode, '') as accountcode
            FROM sip 
            WHERE name REGEXP 'overhead|speaker|page|intercom|zone' 
               OR description REGEXP 'overhead|speaker|page|intercom|zone'
            ORDER BY name;
        """, ["name", "host", "context", "description", "accountcode"], **kw)
        
        config["sip_speakers"] = speakers
    
    # Check PJSIP endpoints for speakers
    if has_table("ps_endpoints", **kw):
        pjsip_speakers = rows_as_dicts("""
            SELECT id, transport, context,
                   COALESCE(callerid, '') as callerid
            FROM ps_endpoints 
            WHERE id REGEXP 'overhead|speaker|page|intercom|zone'
               OR callerid REGEXP 'overhead|speaker|page|intercom|zone'
            ORDER BY id;
        """, ["id", "transport", "context", "callerid"], **kw)
        
        config["pjsip_speakers"] = pjsip_speakers
    
    # Look for multicast paging configurations
    if has_table("sip", **kw):
        multicast_devices = rows_as_dicts("""
            SELECT name, host, context, type
            FROM sip 
            WHERE host LIKE '224.%' OR host LIKE '239.%'
            ORDER BY name;
        """, ["name", "host", "context", "type"], **kw)
        
        config["multicast_devices"] = multicast_devices
    
    # Check for specific overhead paging modules
    overhead_tables = ["overhead", "overhead_config", "intercom", "intercom_config"]
    for table in overhead_tables:
        if has_table(table, **kw):
            try:
                cols = get_columns(table, **kw)
                # Get first few columns for basic info
                basic_cols = list(cols)[:5]
                data = rows_as_dicts(f"SELECT * FROM {table} LIMIT 10;", basic_cols, **kw)
                config[f"{table}_data"] = data
            except:
                pass
    
    return config

def analyze_fax_configuration(**kw):
    """Comprehensive fax configuration analysis."""
    config = {"enabled": False, "engine": "unknown", "users": [], "settings": {}}
    
    # Check fax module status
    fax_tables = ["fax_details", "fax_users", "fax_incoming", "fax_outgoing", "fax", "fax_config"]
    available_fax_tables = [t for t in fax_tables if has_table(t, **kw)]
    
    if not available_fax_tables:
        return config
    
    config["enabled"] = True
    config["available_tables"] = available_fax_tables
    
    # Analyze fax engine settings
    if has_table("fax_details", **kw):
        fax_settings = rows_as_dicts("""
            SELECT keyword, value FROM fax_details ORDER BY keyword;
        """, ["keyword", "value"], **kw)
        
        config["settings"] = {s["keyword"]: s["value"] for s in fax_settings}
        
        # Determine fax engine
        if "faxengine" in config["settings"]:
            config["engine"] = config["settings"]["faxengine"]
        elif "res_fax_spandsp" in config["settings"]:
            config["engine"] = "spandsp"
        elif "res_fax_digium" in config["settings"]:
            config["engine"] = "digium"
    
    # Analyze fax users
    if has_table("fax_users", **kw):
        fax_users = rows_as_dicts("""
            SELECT user, 
                   COALESCE(ringlength, '0') as ringlength,
                   COALESCE(legacy_email, '') as legacy_email,
                   COALESCE(attachformat, 'pdf') as attachformat
            FROM fax_users ORDER BY user;
        """, ["user", "ringlength", "legacy_email", "attachformat"], **kw)
        
        config["users"] = fax_users
        config["total_users"] = len(fax_users)
        config["users_with_email"] = len([u for u in fax_users if u["legacy_email"]])
    
    # Analyze incoming fax routes
    if has_table("fax_incoming", **kw):
        incoming_fax = rows_as_dicts("""
            SELECT extension, 
                   COALESCE(cidnum, '') as cidnum,
                   COALESCE(destination, '') as destination,
                   COALESCE(faxemail, '') as faxemail,
                   COALESCE(faxexten, '') as faxexten
            FROM fax_incoming ORDER BY extension;
        """, ["extension", "cidnum", "destination", "faxemail", "faxexten"], **kw)
        
        config["incoming_routes"] = incoming_fax
        config["total_incoming_routes"] = len(incoming_fax)
    
    # Check for outbound fax configurations
    if has_table("fax_outgoing", **kw):
        outgoing_fax = rows_as_dicts("""
            SELECT pattern, 
                   COALESCE(destination, '') as destination,
                   COALESCE(faxheader, '') as faxheader
            FROM fax_outgoing ORDER BY pattern;
        """, ["pattern", "destination", "faxheader"], **kw)
        
        config["outgoing_routes"] = outgoing_fax
    
    # Check fax detection settings
    config["fax_detection"] = {}
    if "faxdetect" in config["settings"]:
        config["fax_detection"]["method"] = config["settings"]["faxdetect"]
    if "faxdetect_timeout" in config["settings"]:
        config["fax_detection"]["timeout"] = config["settings"]["faxdetect_timeout"]
    
    return config

_FAX_NAME_RE = re.compile(r'fax|facsimile', re.IGNORECASE)

def _extract_dest_extension(dest):
    """Best-effort extraction of a destination extension number from a raw
    FreePBX destination string (e.g. 'from-did-direct,205,1' -> '205').
    Only resolves the direct-to-extension case — a DID routed through an
    IVR/ring group/queue isn't a single physical device, so it's out of
    scope for this check."""
    if not dest:
        return None
    parts = dest.split(",")
    if len(parts) < 2:
        return None
    context, ext = parts[0], parts[1].strip()
    if context in ("from-did-direct", "ext-local", "from-internal") and ext:
        return ext
    return None

def _get_native_fax_extensions(**kw):
    """Extensions FreePBX's own Fax module is actively handling."""
    exts = set()
    if has_table("fax_users", **kw):
        rows = rows_as_dicts("SELECT user FROM fax_users;", ["user"], **kw)
        exts.update(r["user"] for r in rows if r.get("user"))
    if has_table("fax_incoming", **kw):
        rows = rows_as_dicts("SELECT extension FROM fax_incoming;", ["extension"], **kw)
        exts.update(r["extension"] for r in rows if r.get("extension"))
    return exts

def analyze_fax_routing_by_did(**kw):
    """Classify each fax-relevant DID's handling path in the order a
    technician would actually check it:
      1. native_fax      — FreePBX's own Fax module is configured for the
                            destination extension.
      2. likely_ata_fax   — not on the native Fax module, but the
                            destination extension's name says "fax"/
                            "facsimile" — almost certainly a physical fax
                            machine behind an ATA registered as that
                            extension (the PBX can't tell a phone from a
                            fax machine on the wire; this is a naming
                            signal only).
      3. check_aggregate  — the DID itself is labeled as fax, but nothing
                            in FreePBX's own config explains how it's
                            handled (no destination extension resolved, or
                            the extension it resolves to doesn't look
                            fax-related either) — the external fax
                            aggregate/FTP service is the next place to
                            check for this DID.

    A DID only appears here at all if either its own label or its
    destination extension's name mentions fax — otherwise this would just
    list every ordinary voice DID under "check_aggregate", which isn't
    useful to anyone troubleshooting a fax problem.
    """
    result = {"native_fax": [], "likely_ata_fax": [], "check_aggregate": []}

    tbl = "incoming" if has_table("incoming", **kw) else ("inbound_routes" if has_table("inbound_routes", **kw) else None)
    if not tbl or not has_table("users", **kw):
        return result

    dc = did_col(tbl, **kw)
    dids = rows_as_dicts(
        f"SELECT {dc}, description, destination FROM {tbl};",
        ["did", "description", "destination"], **kw
    )

    native_fax_exts = _get_native_fax_extensions(**kw)

    for row in dids:
        did = row["did"]
        did_label = row.get("description", "") or ""
        dest = row.get("destination", "") or ""
        ext = _extract_dest_extension(dest)

        ext_name = ""
        if ext:
            r = rows_as_dicts(f"SELECT name FROM users WHERE extension='{ext}';", ["name"], **kw)
            ext_name = r[0]["name"] if r else ""

        did_says_fax = bool(_FAX_NAME_RE.search(did_label))
        ext_says_fax = bool(ext_name and _FAX_NAME_RE.search(ext_name))
        if not (did_says_fax or ext_says_fax):
            continue

        entry = {"did": did, "did_label": did_label, "extension": ext or "", "extension_name": ext_name}

        if ext and ext in native_fax_exts:
            result["native_fax"].append(entry)
        elif ext_says_fax:
            result["likely_ata_fax"].append(entry)
        else:
            result["check_aggregate"].append(entry)

    return result

def get_asterisk_fax_modules():
    """Check which Asterisk fax modules are loaded."""
    modules = {}
    
    stdout, stderr, rc = run_command("asterisk -rx 'module show like fax'")
    if rc == 0:
        for line in stdout.split('\n'):
            if 'res_fax' in line or 'app_fax' in line:
                parts = line.split()
                if len(parts) >= 2:
                    module_name = parts[0]
                    status = "loaded" if "Loaded" in line else "not_loaded"
                    modules[module_name] = status
    
    return modules

def analyze_dial_plan_features(**kw):
    """Analyze dialplan for paging and fax features."""
    features = {"paging_codes": [], "fax_codes": [], "intercom_codes": []}
    
    # Look for feature codes in the dialplan
    if has_table("featurecodes", **kw):
        feature_codes = rows_as_dicts("""
            SELECT modulename, featurename, defaultcode, 
                   COALESCE(customcode, defaultcode) as current_code,
                   COALESCE(enabled, '1') as enabled
            FROM featurecodes 
            WHERE modulename IN ('paging', 'fax', 'intercom', 'pagingpro')
               OR featurename LIKE '%pag%'
               OR featurename LIKE '%fax%'
               OR featurename LIKE '%intercom%'
            ORDER BY modulename, featurename;
        """, ["modulename", "featurename", "defaultcode", "current_code", "enabled"], **kw)
        
        for code in feature_codes:
            if "pag" in code["modulename"].lower() or "pag" in code["featurename"].lower():
                features["paging_codes"].append(code)
            elif "fax" in code["modulename"].lower() or "fax" in code["featurename"].lower():
                features["fax_codes"].append(code)
            elif "intercom" in code["modulename"].lower() or "intercom" in code["featurename"].lower():
                features["intercom_codes"].append(code)
    
    return features

def main():
    parser = argparse.ArgumentParser(description="Analyze FreePBX paging, overhead speakers, and fax configurations")
    parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
    parser.add_argument("--db-user", default="root", help="MySQL user")
    parser.add_argument("--db-password", help="MySQL password")
    parser.add_argument("--output", "-o", help="Output file (JSON format)")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    
    args = parser.parse_args()
    
    print_header()
    
    kw = {
        "socket": args.socket,
        "user": args.db_user,
        "password": args.db_password
    }
    
    print(Colors.YELLOW + "� Analyzing paging, overhead & fax systems..." + Colors.ENDC)
    
    # Gather all analysis data
    try:
        hostname = os.uname().nodename  # type: ignore
    except AttributeError:
        hostname = os.environ.get('HOSTNAME', 'unknown')
    
    analysis = {
        "meta": {
            "hostname": hostname,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        },
        "paging_pro": analyze_paging_pro(**kw),
        "overhead_paging": analyze_overhead_paging(**kw),
        "fax_config": analyze_fax_configuration(**kw),
        "fax_routing_by_did": analyze_fax_routing_by_did(**kw),
        "asterisk_fax_modules": get_asterisk_fax_modules(),
        "dialplan_features": analyze_dial_plan_features(**kw)
    }
    
    if args.format == "json":
        output = json.dumps(analysis, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"✅ Analysis saved to {args.output}")
        else:
            print(output)
    else:
        print_analysis_report(analysis)
        
        if args.output:
            with open(args.output, 'w') as f:
                import sys
                old_stdout = sys.stdout
                sys.stdout = f
                print_analysis_report(analysis)
                sys.stdout = old_stdout
            print(f"✅ Analysis saved to {args.output}")

def print_analysis_report(analysis):
    """Print detailed text analysis report with dramatic styling."""
    meta = analysis["meta"]
    
    # Dramatic main header
    print("\n" + Colors.MAGENTA + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "║" + " 📋 Paging, Overhead & Fax Analysis Report".center(78) + "║" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    print(Colors.MAGENTA + "║ " + Colors.BOLD + "Host:      " + Colors.ENDC + Colors.GREEN + meta['hostname'].ljust(64) + Colors.MAGENTA + " ║" + Colors.ENDC)
    print(Colors.MAGENTA + "║ " + Colors.BOLD + "Generated: " + Colors.ENDC + meta['generated_at'].ljust(64) + Colors.MAGENTA + " ║" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Paging Pro Analysis with dramatic box
    paging = analysis["paging_pro"]
    print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "║" + " 📢 PAGING PRO CONFIGURATION".center(78) + "║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    
    if paging["enabled"]:
        status_line = Colors.GREEN + "✅ Module Status: " + Colors.BOLD + "ENABLED".ljust(58)
        print(Colors.GREEN + "║  " + Colors.ENDC + status_line + Colors.GREEN + " ║" + Colors.ENDC)
        print(Colors.GREEN + "╠" + "─" * 78 + "╣" + Colors.ENDC)
        print(Colors.GREEN + "║  " + Colors.BOLD + "Total Groups:        " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(paging.get('total_groups', 0)).ljust(54) + Colors.GREEN + " ║" + Colors.ENDC)
        print(Colors.GREEN + "║  " + Colors.GREEN + "● " + Colors.BOLD + "Active Groups:      " + Colors.ENDC + 
              Colors.GREEN + Colors.BOLD + str(paging.get('enabled_groups', 0)).ljust(54) + Colors.GREEN + " ║" + Colors.ENDC)
        print(Colors.GREEN + "║  " + Colors.CYAN + "● " + Colors.BOLD + "Duplex Groups:      " + Colors.ENDC + 
              Colors.CYAN + Colors.BOLD + str(paging.get('duplex_groups', 0)).ljust(54) + Colors.GREEN + " ║" + Colors.ENDC)
        print(Colors.GREEN + "║  " + Colors.YELLOW + "● " + Colors.BOLD + "Member Assignments: " + Colors.ENDC + 
              Colors.YELLOW + Colors.BOLD + str(paging.get('total_member_assignments', 0)).ljust(54) + Colors.GREEN + " ║" + Colors.ENDC)
        
        if paging.get("groups"):
            print(Colors.GREEN + "╠" + "─" * 78 + "╣" + Colors.ENDC)
            print(Colors.GREEN + "║  " + Colors.BOLD + "📋 Paging Groups:" + Colors.ENDC + " " * 59 + Colors.GREEN + "║" + Colors.ENDC)
            for group in paging["groups"][:8]:  # Show first 8
                status_icon = Colors.GREEN + "✓" + Colors.ENDC if group["enabled"] == "1" else Colors.RED + "✗" + Colors.ENDC
                duplex_badge = Colors.CYAN + " [Duplex]" + Colors.ENDC if group["duplex"] == "1" else ""
                ext_desc = (Colors.WHITE + Colors.BOLD + group['extension'].ljust(6) + Colors.ENDC + 
                           group['description'][:40] + duplex_badge)[:65]
                print(Colors.GREEN + "║    " + Colors.ENDC + status_icon + " " + ext_desc.ljust(72) + Colors.GREEN + " ║" + Colors.ENDC)
                
                # Show members
                members = paging.get("members_by_group", {}).get(group["extension"], [])
                if members:
                    member_str = ', '.join(members[:6])
                    if len(members) > 6:
                        member_str += f" +{len(members)-6} more"
                    print(Colors.GREEN + "║" + Colors.ENDC + "        " + Colors.CYAN + "Members: " + Colors.ENDC + 
                          member_str[:60].ljust(60) + Colors.GREEN + " ║" + Colors.ENDC)
    else:
        print(Colors.GREEN + "║  " + Colors.ENDC + Colors.RED + Colors.BOLD + "❌ Module Status: NOT CONFIGURED".ljust(75) + Colors.GREEN + " ║" + Colors.ENDC)
    
    print(Colors.GREEN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Overhead Paging Analysis
    overhead = analysis["overhead_paging"]
    print("\n" + Colors.BLUE + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.BLUE + Colors.BOLD + "║" + " 📻 OVERHEAD PAGING/SPEAKERS".center(78) + "║" + Colors.ENDC)
    print(Colors.BLUE + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    
    sip_speakers = overhead.get("sip_speakers", [])
    pjsip_speakers = overhead.get("pjsip_speakers", [])
    multicast = overhead.get("multicast_devices", [])
    
    total_devices = len(sip_speakers) + len(pjsip_speakers) + len(multicast)
    
    if total_devices > 0:
        print(Colors.BLUE + "║  " + Colors.BOLD + "Total Devices:    " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(total_devices).ljust(57) + Colors.BLUE + " ║" + Colors.ENDC)
        print(Colors.BLUE + "╠" + "─" * 78 + "╣" + Colors.ENDC)
        
        if sip_speakers:
            print(Colors.BLUE + "║  " + Colors.GREEN + "● " + Colors.BOLD + "SIP Overhead Speakers: " + Colors.ENDC + 
                  Colors.GREEN + Colors.BOLD + str(len(sip_speakers)).ljust(52) + Colors.BLUE + " ║" + Colors.ENDC)
            for speaker in sip_speakers[:5]:
                speaker_line = (Colors.CYAN + Colors.BOLD + speaker['name'][:15].ljust(15) + Colors.ENDC + 
                              " " + speaker['description'][:30].ljust(30) + 
                              Colors.YELLOW + " (" + speaker['host'][:15] + ")" + Colors.ENDC)[:68]
                print(Colors.BLUE + "║      " + Colors.ENDC + speaker_line.ljust(70) + Colors.BLUE + " ║" + Colors.ENDC)
        
        if pjsip_speakers:
            if sip_speakers:
                print(Colors.BLUE + "║" + " " * 78 + "║" + Colors.ENDC)
            print(Colors.BLUE + "║  " + Colors.GREEN + "● " + Colors.BOLD + "PJSIP Overhead Speakers: " + Colors.ENDC + 
                  Colors.GREEN + Colors.BOLD + str(len(pjsip_speakers)).ljust(50) + Colors.BLUE + " ║" + Colors.ENDC)
            for speaker in pjsip_speakers[:5]:
                speaker_line = (Colors.CYAN + Colors.BOLD + speaker['id'][:15].ljust(15) + Colors.ENDC + 
                              " " + speaker['callerid'][:50])[:68]
                print(Colors.BLUE + "║      " + Colors.ENDC + speaker_line.ljust(70) + Colors.BLUE + " ║" + Colors.ENDC)
        
        if multicast:
            if sip_speakers or pjsip_speakers:
                print(Colors.BLUE + "║" + " " * 78 + "║" + Colors.ENDC)
            print(Colors.BLUE + "║  " + Colors.GREEN + "● " + Colors.BOLD + "Multicast Devices: " + Colors.ENDC + 
                  Colors.GREEN + Colors.BOLD + str(len(multicast)).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
            for device in multicast[:5]:
                device_line = (Colors.CYAN + Colors.BOLD + device['name'][:20].ljust(20) + Colors.ENDC + 
                             " " + Colors.YELLOW + device['host'][:30] + Colors.ENDC + 
                             Colors.MAGENTA + " [multicast]" + Colors.ENDC)[:68]
                print(Colors.BLUE + "║      " + Colors.ENDC + device_line.ljust(70) + Colors.BLUE + " ║" + Colors.ENDC)
    else:
        print(Colors.BLUE + "║  " + Colors.ENDC + Colors.RED + Colors.BOLD + "❌ No overhead paging devices detected".ljust(75) + Colors.BLUE + " ║" + Colors.ENDC)
    
    print(Colors.BLUE + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Fax Configuration Analysis
    fax = analysis["fax_config"]
    print("\n" + Colors.YELLOW + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.YELLOW + Colors.BOLD + "║" + " 📠 FAX CONFIGURATION".center(78) + "║" + Colors.ENDC)
    print(Colors.YELLOW + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    
    if fax["enabled"]:
        status_line = Colors.GREEN + "✅ Module Status: " + Colors.BOLD + "ENABLED".ljust(58)
        print(Colors.YELLOW + "║  " + Colors.ENDC + status_line + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "╠" + "─" * 78 + "╣" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Fax Engine:       " + Colors.ENDC + 
              Colors.CYAN + Colors.BOLD + fax['engine'].upper().ljust(57) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Total Fax Users:  " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(fax.get('total_users', 0)).ljust(57) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.GREEN + "✓ " + Colors.BOLD + "With Email:      " + Colors.ENDC + 
              Colors.GREEN + Colors.BOLD + str(fax.get('users_with_email', 0)).ljust(57) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Incoming Routes:  " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(fax.get('total_incoming_routes', 0)).ljust(57) + Colors.YELLOW + " ║" + Colors.ENDC)
        
        # Asterisk fax modules
        ast_fax = analysis["asterisk_fax_modules"]
        if ast_fax:
            print(Colors.YELLOW + "╠" + "─" * 78 + "╣" + Colors.ENDC)
            print(Colors.YELLOW + "║  " + Colors.BOLD + "🔧 Asterisk Fax Modules:" + Colors.ENDC + " " * 52 + Colors.YELLOW + "║" + Colors.ENDC)
            for module, status in ast_fax.items():
                status_icon = Colors.GREEN + "✓" + Colors.ENDC if status == "loaded" else Colors.RED + "✗" + Colors.ENDC
                module_line = (status_icon + " " + Colors.CYAN + module[:65] + Colors.ENDC).ljust(72)
                print(Colors.YELLOW + "║      " + Colors.ENDC + module_line + Colors.YELLOW + " ║" + Colors.ENDC)
    else:
        print(Colors.YELLOW + "║  " + Colors.ENDC + Colors.RED + Colors.BOLD + "❌ Module Status: NOT CONFIGURED".ljust(75) + Colors.YELLOW + " ║" + Colors.ENDC)
    
    print(Colors.YELLOW + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)

    # Fax Routing By DID — where each fax-relevant DID is actually handled:
    # FreePBX's native Fax module, an ATA-connected extension (name-based
    # signal only), or neither — in which case the external fax aggregate
    # service is the next place to check.
    routing = analysis.get("fax_routing_by_did", {})
    native = routing.get("native_fax", [])
    ata = routing.get("likely_ata_fax", [])
    aggregate = routing.get("check_aggregate", [])
    total_fax_dids = len(native) + len(ata) + len(aggregate)

    print("\n" + Colors.MAGENTA + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "║" + " 📠 FAX ROUTING BY DID".center(78) + "║" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)

    if total_fax_dids == 0:
        line = 'No DIDs or extensions with "fax" in their name/label found.'
        print(Colors.MAGENTA + "║  " + Colors.ENDC + Colors.YELLOW + line.ljust(75) + Colors.MAGENTA + " ║" + Colors.ENDC)
    else:
        def _tier(title, entries, note, icon):
            count_line = f"{title}: {len(entries)}"
            print(Colors.MAGENTA + "║  " + Colors.ENDC + icon + " " + Colors.BOLD +
                  count_line.ljust(74) + Colors.ENDC + Colors.MAGENTA + " ║" + Colors.ENDC)
            for e in entries[:10]:
                detail = (f"  {e['did']} ({e['did_label'] or 'no label'}) -> "
                          f"ext {e['extension'] or '?'} ({e['extension_name'] or 'no name'})")
                print(Colors.MAGENTA + "║  " + Colors.ENDC + detail[:76].ljust(76) + Colors.MAGENTA + " ║" + Colors.ENDC)
            if len(entries) > 10:
                more = f"  ... +{len(entries) - 10} more"
                print(Colors.MAGENTA + "║  " + Colors.ENDC + more.ljust(76) + Colors.MAGENTA + " ║" + Colors.ENDC)
            if entries:
                print(Colors.MAGENTA + "║  " + Colors.ENDC + Colors.YELLOW +
                      ("  " + note)[:76].ljust(76) + Colors.ENDC + Colors.MAGENTA + " ║" + Colors.ENDC)
                print(Colors.MAGENTA + "║" + " " * 78 + "║" + Colors.ENDC)

        _tier("Native FreePBX Fax module", native,
              "Handled by FreePBX's Fax module -- check fax_users/fax_incoming.",
              Colors.GREEN + "✓" + Colors.ENDC)
        _tier("Likely ATA-connected fax (name-based)", ata,
              "No native Fax module -- verify the ATA is registered and working.",
              Colors.CYAN + "●" + Colors.ENDC)
        _tier("No FreePBX handling found", aggregate,
              "Check the external fax aggregate/FTP service for this site next.",
              Colors.RED + "✗" + Colors.ENDC)

    print(Colors.MAGENTA + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)

    # Dialplan Features with dramatic table
    features = analysis["dialplan_features"]
    print("\n" + Colors.CYAN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "║" + " ☎️  DIALPLAN FEATURE CODES".center(78) + "║" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    
    all_codes = features["paging_codes"] + features["fax_codes"] + features["intercom_codes"]
    if all_codes:
        # Header
        header = (Colors.CYAN + "║ " + Colors.ENDC + Colors.BOLD + 
                 "St".ljust(4) + "Code".ljust(8) + "Feature Name".ljust(32) + "Module".ljust(30) + Colors.ENDC +
                 Colors.CYAN + " ║" + Colors.ENDC)
        print(header)
        print(Colors.CYAN + "╠" + "─" * 78 + "╣" + Colors.ENDC)
        
        for code in all_codes:
            status_icon = Colors.GREEN + "●" + Colors.ENDC if code["enabled"] == "1" else Colors.RED + "●" + Colors.ENDC
            code_line = (Colors.CYAN + "║ " + Colors.ENDC + 
                        status_icon + " " +
                        Colors.YELLOW + Colors.BOLD + code['current_code'][:6].ljust(8) + Colors.ENDC + 
                        Colors.WHITE + code['featurename'][:30].ljust(32) + Colors.ENDC +
                        Colors.BLUE + code['modulename'][:28].ljust(28) + Colors.ENDC +
                        Colors.CYAN + " ║" + Colors.ENDC)
            print(code_line)
    else:
        print(Colors.CYAN + "║ " + Colors.ENDC + Colors.RED + "❌ No paging/fax/intercom feature codes found".ljust(75) + 
              Colors.CYAN + " ║" + Colors.ENDC)
    
    print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Completion banner
    print("\n" + Colors.MAGENTA + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "║" + " ✅ Specialized Analysis Complete".center(78) + "║" + Colors.ENDC)
    print(Colors.MAGENTA + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC + "\n")

if __name__ == "__main__":
    main()